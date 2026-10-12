import pytest
from lnbits.db import Database
from sqlalchemy.ext.asyncio import create_async_engine

from .. import crud, migrations
from ..models import Card, Hit

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest.mark.parametrize("enabled", [True, False])
async def test_upgrade_preserves_programmed_card_and_pending_withdrawal(
    tmp_path, monkeypatch, enabled
):
    legacy = Database("ext_boltcards")
    legacy.path = str(tmp_path / "legacy.sqlite3")
    legacy.engine = create_async_engine(f"sqlite+aiosqlite:///{legacy.path}")
    try:
        async with legacy.connect() as conn:
            await migrations.m001_initial(conn)
            await migrations.m002_correct_typing(conn)
        await legacy.execute(
            """
            INSERT INTO boltcards.cards
            (id, wallet, card_name, uid, external_id, counter, tx_limit,
             daily_limit, enable, k0, k1, k2, otp)
            VALUES ('card', 'wallet', 'Existing card', '01020304050607',
                    'existing', 254, 10000000, 100000000, :enabled, :k0, :k1, :k2, :otp)
            """,
            {
                "enabled": enabled,
                "k0": "ab" * 16,
                "k1": "cd" * 16,
                "k2": "ef" * 16,
                "otp": "aa" * 16,
            },
        )
        for hit_id, spent, amount in (("paid", True, 10000), ("pending", False, 0)):
            await legacy.execute(
                """
                INSERT INTO boltcards.hits (id, card_id, ip, spent, amount, useragent)
                VALUES (:id, 'card', 'peer', :spent, :amount, 'agent')
                """,
                {"id": hit_id, "spent": spent, "amount": amount},
            )
        before = await legacy.fetchone("SELECT * FROM boltcards.cards", model=Card)
        async with legacy.connect() as conn:
            await migrations.m003_claims(conn)
        after = await legacy.fetchone("SELECT * FROM boltcards.cards", model=Card)
        assert before.dict(exclude={"otp"}) == after.dict(exclude={"otp"})
        assert before.otp != after.otp and len(after.otp) == 32
        paid = await legacy.fetchone(
            "SELECT * FROM boltcards.hits WHERE id = 'paid'", model=Hit
        )
        assert paid.amount == 10000 and paid.amount_msat == 10_000_000
        assert paid.claimed_at == paid.time
        pending = await legacy.fetchone(
            "SELECT * FROM boltcards.hits WHERE id = 'pending'", model=Hit
        )
        assert not pending.spent and pending.max_msat == 10_000_000_000
        monkeypatch.setattr(crud, "db", legacy)
        # The old bearer token still works with the newly enforced daily budget.
        if enabled:
            await crud.spend_hit("pending", 10_000_000)
            hit = await crud.create_hit(after, "peer", "agent", 255)
            assert hit.new_ctr == 255
        else:
            with pytest.raises(ValueError, match="disabled"):
                await crud.spend_hit("pending", 10_000_000)
    finally:
        await legacy.engine.dispose()
