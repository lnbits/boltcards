import asyncio

from fastapi import APIRouter
from loguru import logger

from .crud import db
from .tasks import wait_for_paid_invoices
from .views import boltcards_generic_router
from .views_api import boltcards_api_router
from .views_lnurl import boltcards_lnurl_router

boltcards_static_files = [
    {
        "path": "/boltcards/static",
        "name": "boltcards_static",
    }
]

boltcards_ext: APIRouter = APIRouter(prefix="/boltcards", tags=["boltcards"])
boltcards_ext.include_router(boltcards_generic_router)
boltcards_ext.include_router(boltcards_api_router)
boltcards_ext.include_router(boltcards_lnurl_router)

scheduled_tasks: list[asyncio.Task] = []


def boltcards_stop():
    for task in scheduled_tasks:
        try:
            task.cancel()
        except Exception as ex:
            logger.warning(ex)


def boltcards_start():
    from lnbits.tasks import create_permanent_unique_task

    task = create_permanent_unique_task("ext_boltcards", wait_for_paid_invoices)
    scheduled_tasks.append(task)


__all__ = [
    "db",
    "boltcards_ext",
    "boltcards_static_files",
    "boltcards_start",
    "boltcards_stop",
]
