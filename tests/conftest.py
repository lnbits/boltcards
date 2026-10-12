import asyncio
from secrets import token_hex
from typing import Any, cast

import lnbits.db as lnbits_db
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from lnbits.core import migrations as core_migrations
from lnbits.core.db import db as core_db
from lnbits.core.helpers import run_migration
from lnbits.core.services.users import create_user_account_no_ckeck
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import create_async_engine

from .. import boltcards_ext, migrations
from ..crud import db, get_card


@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def databases(tmp_path_factory):
    folder = tmp_path_factory.mktemp("boltcards")
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(lnbits_db, "DB_TYPE", lnbits_db.SQLITE)
        for database, migration, name in (
            (core_db, core_migrations, "core"),
            (db, migrations, "boltcards"),
        ):
            path = str(folder / f"{name}.sqlite3")
            engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
            patch.setattr(database, "path", path)
            patch.setattr(database, "type", lnbits_db.SQLITE)
            patch.setattr(database, "engine", engine)
            patch.setattr(database, "lock", asyncio.Lock())
            async with database.connect() as conn:
                await run_migration(conn, migration, name)
        yield
        await db.engine.dispose()
        await core_db.engine.dispose()


@pytest_asyncio.fixture(loop_scope="session")
async def client(databases):
    app = FastAPI()
    app.state.limiter = Limiter(key_func=get_remote_address)
    app.include_router(boltcards_ext)
    async with AsyncClient(
        transport=ASGITransport(app=cast(Any, app)), base_url="https://testserver"
    ) as client:
        yield client


@pytest_asyncio.fixture(loop_scope="session")
async def owner():
    user = await create_user_account_no_ckeck(default_exts=["boltcards"])
    return user, user.wallets[0]


@pytest_asyncio.fixture(loop_scope="session")
async def card(client, owner):
    _, wallet = owner
    response = await client.post(
        "/boltcards/api/v1/cards",
        headers={"X-API-KEY": wallet.adminkey},
        json={
            "card_name": "Test card",
            "uid": token_hex(7),
            "k0": token_hex(16),
            "k1": token_hex(16),
            "k2": token_hex(16),
            "tx_limit": 10,
            "daily_limit": 15,
        },
    )
    assert response.status_code == 201, response.text
    card = await get_card(response.json()["id"])
    assert card
    return card
