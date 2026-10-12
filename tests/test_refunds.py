from secrets import token_hex
from unittest.mock import AsyncMock

import pytest
from lnbits.core.crud import create_wallet
from lnbits.core.models import Payment

from .. import tasks
from ..crud import create_hit, create_refund, get_refunds, spend_hit

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


async def test_refund_listener_checks_payment_wallet(owner, card, monkeypatch):
    hit = await create_hit(card, "peer", "agent", 1)
    await spend_hit(hit.id, 2_000)
    sibling = await create_wallet(user_id=owner[0].id)
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
    payment.wallet_id = card.wallet
    await tasks.on_invoice_paid(payment)
    assert len(await get_refunds([hit.id])) == 1
    update.assert_awaited_once()
    await tasks.on_invoice_paid(payment)
    assert len(await get_refunds([hit.id])) == 1
