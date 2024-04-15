import asyncio
from loguru import logger

from fastapi import APIRouter
from lnbits.db import Database
from lnbits.helpers import template_renderer
from lnbits.tasks import create_permanent_unique_task

db = Database("ext_boltcards")

boltcards_static_files = [
    {
        "path": "/boltcards/static",
        "name": "boltcards_static",
    }
]

boltcards_ext: APIRouter = APIRouter(prefix="/boltcards", tags=["boltcards"])


def boltcards_renderer():
    return template_renderer(["boltcards/templates"])


from .lnurl import *  # noqa: F401,F403
from .tasks import *  # noqa: F401,F403

scheduled_tasks: list[asyncio.Task] = []


def boltcards_stop():
    for task in scheduled_tasks:
        try:
            task.cancel()
        except Exception as ex:
            logger.warning(ex)


def boltcards_start():
    task = create_permanent_unique_task(wait_for_paid_invoices)
    scheduled_tasks.append(task)


from .views import *  # noqa: F401,F403
from .views_api import *  # noqa: F401,F403
