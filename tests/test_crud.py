import asyncio
from datetime import datetime, timedelta, timezone
from secrets import token_hex

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from ..crud import create_hit, db, get_card, get_hit, get_hits, spend_hit, update_card

pytestmark = pytest.mark.asyncio(loop_scope="session")


class IndependentWorkers:
    """Separate workers share database locks, but have no shared asyncio lock."""

    async def acquire(self):
        pass

    def release(self):
        pass


async def test_database_serializes_independent_workers(card, monkeypatch):
    monkeypatch.setattr(db, "lock", IndependentWorkers())
    results = await asyncio.gather(
        create_hit(card, "peer", "agent", 1),
        create_hit(card, "peer", "agent", 1),
        return_exceptions=True,
    )
    assert sum(isinstance(r, ValueError) for r in results) == 1
    hits = await get_hits([card.id])
    assert len(hits) == 1
    second = await create_hit(card, "peer", "agent", 2)
    claims = await asyncio.gather(
        spend_hit(hits[0].id, 10_000),
        spend_hit(second.id, 10_000),
        return_exceptions=True,
    )
    assert sum(isinstance(r, ValueError) for r in claims) == 1
    assert sum(hit.amount_msat for hit in await get_hits([card.id])) == 10_000


async def test_hit_insert_failure_rolls_back_counter(card, monkeypatch):
    execute = AsyncConnection.execute

    async def fail_insert(self, statement, *args, **kwargs):
        if "INSERT INTO boltcards.hits" in str(statement):
            raise RuntimeError("insert failed")
        return await execute(self, statement, *args, **kwargs)

    monkeypatch.setattr(AsyncConnection, "execute", fail_insert)
    with pytest.raises(RuntimeError, match="insert failed"):
        await create_hit(card, "peer", "agent", 1)
    saved = await get_card(card.id)
    assert saved and saved.counter == 0
    assert await get_hits([card.id]) == []


async def test_claim_is_counted_on_claim_day(card):
    first = await create_hit(card, "peer", "agent", 1)
    second = await create_hit(card, "peer", "agent", 2)
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    await db.execute(
        f"UPDATE boltcards.hits SET time = {db.timestamp_placeholder('time')} "
        "WHERE id = :id",
        {"id": first.id, "time": yesterday.timestamp()},
    )
    await spend_hit(first.id, 10_000)
    with pytest.raises(ValueError, match="withdrawal limit"):
        await spend_hit(second.id, 6_000)
    saved = await get_hit(first.id)
    assert saved and saved.claimed_at
    assert saved.claimed_at.date() == datetime.now(timezone.utc).date()


async def test_hit_keeps_scan_amount_bound(card):
    hit = await create_hit(card, "peer", "agent", 1)
    await db.execute(
        "UPDATE boltcards.cards SET tx_limit = 100, daily_limit = 100 WHERE id = :id",
        {"id": card.id},
    )
    with pytest.raises(ValueError, match="withdrawal limit"):
        await spend_hit(hit.id, 11_000)
    saved = await get_hit(hit.id)
    assert saved and not saved.spent


async def test_spend_hit_returns_claim_state(card):
    hit = await create_hit(card, "peer", "agent", 1)
    claimed, claimed_card = await spend_hit(hit.id, 1_001)
    assert claimed_card.id == card.id
    assert claimed.spent
    assert claimed.amount == 2
    assert claimed.amount_msat == 1_001
    assert claimed.claimed_at
    saved = await get_hit(hit.id)
    assert saved and saved.claimed_at
    assert (claimed.spent, claimed.amount, claimed.amount_msat) == (
        saved.spent,
        saved.amount,
        saved.amount_msat,
    )
    assert abs((claimed.claimed_at - saved.claimed_at).total_seconds()) < 1


async def test_key_update_invalidates_old_taps_and_hits(card):
    hit = await create_hit(card, "peer", "agent", 1)
    changed = card.copy(update={"k1": token_hex(16)})
    await update_card(changed)
    with pytest.raises(ValueError, match="has changed"):
        await create_hit(card, "peer", "agent", 2)
    with pytest.raises(ValueError, match="already claimed"):
        await spend_hit(hit.id, 1_000)
