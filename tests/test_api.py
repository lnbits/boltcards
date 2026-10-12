import asyncio
import json
import time
from secrets import token_hex
from unittest.mock import AsyncMock

import bolt11
import pytest
from Cryptodome.Cipher import AES
from fastapi.responses import HTMLResponse
from lnbits.core.services.users import create_user_account_no_ckeck
from lnbits.decorators import optional_user_id
from lnbits.exceptions import PaymentError

from .. import services, views
from ..crud import get_card, get_card_by_uid, get_hit
from ..nxp424 import get_sun_mac

pytestmark = pytest.mark.asyncio(loop_scope="session")
SECRETS = {"k0", "k1", "k2", "prev_k0", "prev_k1", "prev_k2", "otp"}


def tap(card, counter):
    uid = bytes.fromhex(card.uid)
    ctr = counter.to_bytes(3, "little")
    plaintext = b"\xc7" + uid + ctr + bytes(5)
    p = AES.new(bytes.fromhex(card.k1), AES.MODE_CBC, bytes(16)).encrypt(plaintext)
    return {"p": p.hex(), "c": get_sun_mac(uid, ctr, bytes.fromhex(card.k2)).hex()}


def invoice(amount_msat):
    return bolt11.encode(
        bolt11.Bolt11(
            currency="bc",
            date=int(time.time()),
            amount_msat=bolt11.MilliSatoshi(amount_msat),
            tags=bolt11.Tags(
                [
                    bolt11.Tag(bolt11.TagChar.payment_hash, token_hex(32)),
                    bolt11.Tag(bolt11.TagChar.payment_secret, token_hex(32)),
                    bolt11.Tag(bolt11.TagChar.description, "Test withdrawal"),
                ]
            ),
        ),
        private_key="01" * 32,
    )


async def read_card(card_id):
    card = await get_card(card_id)
    assert card
    return card


async def scan(client, card, counter):
    response = await client.get(
        f"/boltcards/api/v1/scan/{card.external_id}", params=tap(card, counter)
    )
    assert response.status_code == 200, response.text
    return response.json()


async def claim(client, hit, amount_msat):
    return await client.get(
        hit["callback"], params={"k1": hit["k1"], "pr": invoice(amount_msat)}
    )


async def test_card_list_requires_admin_and_preserves_payload(client, owner, card):
    _, wallet = owner
    path = "/boltcards/api/v1/cards?all_wallets=true"
    for headers, status in (({}, 401), ({"X-API-KEY": wallet.inkey}, 403)):
        response = await client.get(path, headers=headers)
        assert response.status_code == status
        assert card.k1 not in response.text
    response = await client.get(path, headers={"X-API-KEY": wallet.adminkey})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    item = next(c for c in response.json() if c["id"] == card.id)
    assert item == json.loads(card.json())
    other = await create_user_account_no_ckeck(default_exts=["boltcards"])
    response = await client.get(path, headers={"X-API-KEY": other.wallets[0].adminkey})
    assert response.status_code == 200
    assert card.k1 not in response.text


async def test_hit_list_requires_admin_and_preserves_payload(client, owner, card):
    _, wallet = owner
    withdrawal = await scan(client, card, 1)
    hit = await get_hit(withdrawal["k1"])
    assert hit
    path = "/boltcards/api/v1/hits?all_wallets=true"
    for headers, status in (({}, 401), ({"X-API-KEY": wallet.inkey}, 403)):
        response = await client.get(path, headers=headers)
        assert response.status_code == status
        assert hit.id not in response.text
    response = await client.get(path, headers={"X-API-KEY": wallet.adminkey})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == [json.loads(hit.json())]
    other = await create_user_account_no_ckeck(default_exts=["boltcards"])
    response = await client.get(path, headers={"X-API-KEY": other.wallets[0].adminkey})
    assert response.status_code == 200
    assert hit.id not in response.text


async def test_card_page_context_excludes_credentials(client, owner, card, monkeypatch):
    # Check the real page context without the global theme setup.
    class Renderer:
        def TemplateResponse(self, _name, context):  # noqa: N802
            return HTMLResponse(context["card"])

    monkeypatch.setattr(views, "boltcards_renderer", Renderer)
    client_app = client._transport.app
    client_app.dependency_overrides[optional_user_id] = lambda: owner[0].id
    response = await client.get(f"/boltcards/{card.external_id}")
    assert response.status_code == 200
    assert SECRETS.isdisjoint(json.loads(response.text))
    assert card.k1 not in response.text
    client_app.dependency_overrides[optional_user_id] = lambda: "another-user"
    response = await client.get(f"/boltcards/{card.external_id}")
    assert response.status_code == 403


@pytest.mark.parametrize("method", ["get", "post"])
async def test_auth_rejects_uid_and_default_token(client, card, method):
    before = await read_card(card.id)
    for token in (card.uid, "0" * 32):
        kwargs = {"json": {"UID": card.uid}} if method == "post" else {}
        response = await getattr(client, method)(
            "/boltcards/api/v1/auth", params={"a": token}, **kwargs
        )
        assert response.status_code == 404
        assert card.k1 not in response.text
    assert (await read_card(card.id)).otp == before.otp


@pytest.mark.parametrize("method", ["get", "post"])
async def test_otp_is_single_use_under_concurrency(client, card, method):
    kwargs = {"json": {"UID": card.uid}} if method == "post" else {}
    responses = await asyncio.gather(
        *(
            getattr(client, method)(
                "/boltcards/api/v1/auth", params={"a": card.otp}, **kwargs
            )
            for _ in range(2)
        )
    )
    assert sorted(r.status_code for r in responses) == [200, 404]
    success = next(r for r in responses if r.status_code == 200)
    assert success.headers["cache-control"] == "no-store"
    assert card.k1 in success.text


async def test_wrong_uid_does_not_consume_otp(client, card):
    response = await client.post(
        "/boltcards/api/v1/auth", params={"a": card.otp}, json={"UID": "wrong"}
    )
    assert response.status_code == 404
    assert (await read_card(card.id)).otp == card.otp


async def test_auth_rate_limit_shared_between_methods(client):
    for i in range(10):
        method = client.get if i % 2 else client.post
        kwargs = {} if i % 2 else {"json": {}}
        response = await method(
            "/boltcards/api/v1/auth", params={"a": "invalid"}, **kwargs
        )
        assert response.status_code == 404
    response = await client.get("/boltcards/api/v1/auth", params={"a": "invalid"})
    assert response.status_code == 429


async def test_replayed_sun_creates_one_hit(client, card):
    results = await asyncio.gather(scan(client, card, 1), scan(client, card, 1))
    assert sum(r.get("tag") == "withdrawRequest" for r in results) == 1
    assert sum(r.get("status") == "ERROR" for r in results) == 1
    assert (await read_card(card.id)).counter == 1


async def test_invalid_cmac_does_not_consume_counter(client, card):
    params = tap(card, 1)
    params["c"] = "00" * 8
    response = await client.get(
        f"/boltcards/api/v1/scan/{card.external_id}", params=params
    )
    assert response.json()["status"] == "ERROR"
    assert (await read_card(card.id)).counter == 0


async def test_pending_hits_cannot_exceed_daily_limit(client, card, monkeypatch):
    pay = AsyncMock()
    monkeypatch.setattr(services, "pay_invoice", pay)
    hits = [await scan(client, card, counter) for counter in (1, 2, 3)]
    responses = await asyncio.gather(*(claim(client, hit, 10_000) for hit in hits))
    assert sum(r.json()["status"] == "OK" for r in responses) == 1
    assert pay.await_count == 1
    # Equality is permitted; any additional spend is refused without burning the tap.
    remaining = next(
        hit
        for hit, r in zip(hits, responses, strict=False)
        if r.json()["status"] == "ERROR"
    )
    response = await claim(client, remaining, 5_000)
    assert response.json()["status"] == "OK"
    response = await scan(client, card, 4)
    assert response["status"] == "ERROR"
    assert (await read_card(card.id)).counter == 3


async def test_duplicate_callback_pays_once(client, card, monkeypatch):
    pay = AsyncMock()
    monkeypatch.setattr(services, "pay_invoice", pay)
    hit = await scan(client, card, 1)
    responses = await asyncio.gather(
        claim(client, hit, 5_000), claim(client, hit, 5_000)
    )
    assert sorted(r.json()["status"] for r in responses) == ["ERROR", "OK"]
    assert pay.await_count == 1


async def test_disabled_card_cannot_claim_pending_hit(client, owner, card, monkeypatch):
    pay = AsyncMock()
    monkeypatch.setattr(services, "pay_invoice", pay)
    hit = await scan(client, card, 1)
    response = await client.get(
        f"/boltcards/api/v1/cards/enable/{card.id}/false",
        headers={"X-API-KEY": owner[1].adminkey},
    )
    assert response.status_code == 200
    assert (await claim(client, hit, 1_000)).json()["status"] == "ERROR"
    await client.get(
        f"/boltcards/api/v1/cards/enable/{card.id}/true",
        headers={"X-API-KEY": owner[1].adminkey},
    )
    assert (await claim(client, hit, 1_000)).json()["status"] == "ERROR"
    pay.assert_not_awaited()


@pytest.mark.parametrize("method", ["get", "post"])
async def test_wipe_clears_keys_and_invalidates_hits(client, owner, card, method):
    hit = await scan(client, card, 1)
    kwargs = {"json": {"UID": card.uid}} if method == "post" else {}
    response = await getattr(client, method)(
        "/boltcards/api/v1/auth", params={"a": card.otp, "wipe": "true"}, **kwargs
    )
    assert response.status_code == 200
    assert card.k0 in response.text  # Physical wipe still needs the old key.
    wiped = await read_card(card.id)
    assert not wiped.enable
    assert all(not getattr(wiped, key) for key in SECRETS - {"otp"})
    assert wiped.otp != card.otp
    saved = await get_hit(hit["k1"])
    assert saved and saved.spent
    assert (await scan(client, card, 2))["status"] == "ERROR"
    assert (await claim(client, hit, 1_000)).json()["status"] == "ERROR"
    enabled = await client.get(
        f"/boltcards/api/v1/cards/enable/{card.id}/true",
        headers={"X-API-KEY": owner[1].adminkey},
    )
    assert enabled.status_code == 400


@pytest.mark.parametrize("status", ["failed", "pending", "unknown"])
async def test_payment_failure_budget_and_errors(client, card, monkeypatch, status):
    error = (
        RuntimeError("sensitive internal detail")
        if status == "unknown"
        else PaymentError("sensitive internal detail", status=status)
    )
    pay = AsyncMock(side_effect=error)
    monkeypatch.setattr(services, "pay_invoice", pay)
    hit = await scan(client, card, 1)
    response = await claim(client, hit, 10_000)
    assert response.json()["status"] == "ERROR"
    assert "sensitive internal detail" not in response.text
    saved = await get_hit(hit["k1"])
    assert saved and saved.spent
    assert saved.amount_msat == (0 if status == "failed" else 10_000)
    assert (await claim(client, hit, 1_000)).json()["status"] == "ERROR"
    assert pay.await_count == 1


async def test_fractional_sat_budget_is_exact(client, card, monkeypatch):
    monkeypatch.setattr(services, "pay_invoice", AsyncMock())
    hits = [await scan(client, card, n) for n in (1, 2)]
    assert (await claim(client, hits[0], 9_999)).json()["status"] == "OK"
    assert (await claim(client, hits[1], 5_002)).json()["status"] == "ERROR"
    assert (await claim(client, hits[1], 5_001)).json()["status"] == "OK"


async def test_uid_lookup_is_wallet_scoped(client, owner, card):
    other = await create_user_account_no_ckeck(default_exts=["boltcards"])
    wallet = other.wallets[0]
    assert await get_card_by_uid(card.uid, wallet.id) is None
    owned = await get_card_by_uid(card.uid.lower(), owner[1].id)
    assert owned and owned.id == card.id
    data = {
        "card_name": "Other card",
        "uid": card.uid.lower(),
        "k0": token_hex(16),
        "k1": token_hex(16),
        "k2": token_hex(16),
    }
    response = await client.post(
        "/boltcards/api/v1/cards", headers={"X-API-KEY": wallet.adminkey}, json=data
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Could not save card details."
    assert card.wallet not in response.text
    data["uid"] = token_hex(7)
    response = await client.post(
        "/boltcards/api/v1/cards", headers={"X-API-KEY": wallet.adminkey}, json=data
    )
    assert response.status_code == 201
    other_card_id = response.json()["id"]
    data["uid"] = card.uid
    response = await client.put(
        f"/boltcards/api/v1/cards/{other_card_id}",
        headers={"X-API-KEY": wallet.adminkey},
        json=data,
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Could not save card details."
    # An unrelated card update remains available after the rejected collision.
    data["uid"] = card.uid.lower()
    response = await client.put(
        f"/boltcards/api/v1/cards/{card.id}",
        headers={"X-API-KEY": owner[1].adminkey},
        json=data,
    )
    assert response.status_code == 200
    assert response.json()["uid"] == card.uid
