import asyncio
from loguru import logger

from fastapi import APIRouter
from lnbits.db import Database
from lnbits.helpers import template_renderer
from lnbits.tasks import create_permanent_unique_task

db = Database("ext_dfxboltcards")

dfxboltcards_static_files = [
    {
        "path": "/dfxboltcards/static",
        "name": "dfxboltcards_static",
    }
]

dfxboltcards_ext: APIRouter = APIRouter(prefix="/dfxboltcards", tags=["dfxboltcards"])


def dfxboltcards_renderer():
    return template_renderer(["dfxboltcards/templates"])


from .lnurl import *  # noqa: F401,F403
from .tasks import *  # noqa: F401,F403

scheduled_tasks: list[asyncio.Task] = []


def dfxboltcards_stop():
    for task in scheduled_tasks:
        try:
            task.cancel()
        except Exception as ex:
            logger.warning(ex)


def dfxboltcards_start():
    task = create_permanent_unique_task("ext_dfxboltcards", wait_for_paid_invoices)
    scheduled_tasks.append(task)


from .views import *  # noqa: F401,F403
from .views_api import *  # noqa: F401,F403
