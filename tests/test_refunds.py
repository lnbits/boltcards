from secrets import token_hex
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from lnbits.core.crud import create_wallet
from lnbits.core.models import Payment

from .. import services, tasks, views_lnurl
from ..crud import create_hit, create_refund, get_card, get_hit, get_refunds, spend_hit
from .test_api import claim, invoice, scan

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_refund_list_requires_admin_key(client, owner, card):
    hit = await create_hit(card, "peer", "agent", 1)
    await spend_hit(hit.id, 1_000)
    refund = await create_refund(hit.id, 1)
    for headers, status in (({}, 401), ({"X-API-KEY": owner[1].inkey}, 403)):
        response = await client.get("/boltcards/api/v1/refunds", headers=headers)
        assert response.status_code == status
        assert hit.id not in response.text
    response = await client.get(
        "/boltcards/api/v1/refunds", headers={"X-API-KEY": owner[1].adminkey}
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()[0]["id"] == refund.id


@pytest.mark.parametrize("shared", [False, True])
async def test_refund_listener_checks_payment_wallet(owner, card, monkeypatch, shared):
    hit = await create_hit(card, "peer", "agent", 1)
    await spend_hit(hit.id, 2_000)
    sibling = await create_wallet(user_id=owner[0].id)
    source_wallet_id = "source-wallet" if shared else card.wallet
    if shared:
        monkeypatch.setattr(
            tasks,
            "get_wallet",
            AsyncMock(
                return_value=SimpleNamespace(
                    id=card.wallet, source_wallet_id=source_wallet_id
                )
            ),
        )
    update = AsyncMock()
    monkeypatch.setattr(tasks, "update_payment", update)
    payment = Payment(
        checking_id=token_hex(16),
        payment_hash=token_hex(32),
        wallet_id=sibling.id,
        amount=1_000,
        fee=0,
        bolt11="",
        status="success",
        extra={"refund": hit.id},
    )
    await tasks.on_invoice_paid(payment)
    assert await get_refunds([hit.id]) == []
    update.assert_not_awaited()
    assert "wh_status" not in payment.extra
    payment.wallet_id = source_wallet_id
    await tasks.on_invoice_paid(payment)
    assert len(await get_refunds([hit.id])) == 1
    update.assert_awaited_once()
    await tasks.on_invoice_paid(payment)
    assert len(await get_refunds([hit.id])) == 1


@pytest.mark.parametrize("claimed", [False, True])
async def test_pay_link_accepts_receive_only_and_refund_payments(
    client, card, monkeypatch, claimed
):
    pay = AsyncMock()
    monkeypatch.setattr(services, "pay_invoice", pay)
    monkeypatch.setattr(tasks, "update_payment", AsyncMock())
    payment = Payment(
        checking_id=token_hex(16),
        payment_hash=token_hex(32),
        wallet_id=card.wallet,
        amount=5_000,
        fee=0,
        bolt11=invoice(5_000),
    )
    create_invoice = AsyncMock(return_value=payment)
    monkeypatch.setattr(views_lnurl, "create_invoice", create_invoice)
    withdrawal = await scan(client, card, 1)
    metadata_path = f"/boltcards/api/v1/lnurlp/{withdrawal['k1']}"
    metadata = (await client.get(metadata_path)).json()
    assert metadata["tag"] == "payRequest"
    if claimed:
        assert (await claim(client, withdrawal, 1_000)).json()["status"] == "OK"
    before = await get_card(card.id)
    response = await client.get(metadata["callback"], params={"amount": 5_000})
    assert response.json()["pr"] == payment.bolt11
    create_invoice.assert_awaited_once()
    assert create_invoice.call_args.kwargs["wallet_id"] == card.wallet
    assert create_invoice.call_args.kwargs["amount"] == 5
    assert await get_card(card.id) == before
    payment.status = "success"
    payment.extra = create_invoice.call_args.kwargs["extra"]
    await tasks.on_invoice_paid(payment)
    refunds = await get_refunds([withdrawal["k1"]])
    assert len(refunds) == 1 and refunds[0].refund_amount == 5
    hit = await get_hit(withdrawal["k1"])
    assert hit and hit.spent is claimed
    assert pay.await_count == int(claimed)


@pytest.mark.parametrize("remaining_msat", [0, 499])
async def test_receive_link_remains_available_after_spending_allowance(
    client, card, monkeypatch, remaining_msat
):
    pay = AsyncMock()
    monkeypatch.setattr(services, "pay_invoice", pay)
    for counter, amount in ((1, 10_000), (2, 5_000 - remaining_msat)):
        withdrawal = await scan(client, card, counter)
        assert (await claim(client, withdrawal, amount)).json()["status"] == "OK"
    receive = await scan(client, card, 3)
    assert receive["tag"] == "withdrawRequest"
    assert receive["minWithdrawable"] == receive["maxWithdrawable"] == 0
    assert receive["payLink"].startswith("lnurlp://")
    metadata = await client.get(f"/boltcards/api/v1/lnurlp/{receive['k1']}")
    assert metadata.json()["tag"] == "payRequest"
    assert (await claim(client, receive, 1_000)).json()["status"] == "ERROR"
    assert pay.await_count == 2
