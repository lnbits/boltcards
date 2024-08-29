from http import HTTPStatus

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from lnbits.core.models import User
from lnbits.decorators import check_user_exists
from lnbits.helpers import template_renderer
from starlette.exceptions import HTTPException
from starlette.responses import HTMLResponse

from .crud import get_card_by_external_id, get_hits, get_refunds

templates = Jinja2Templates(directory="templates")
boltcards_generic_router = APIRouter()


def boltcards_renderer():
    return template_renderer(["boltcards/templates"])


@boltcards_generic_router.get("/", response_class=HTMLResponse)
async def index(request: Request, user: User = Depends(check_user_exists)):
    return boltcards_renderer().TemplateResponse(
        "boltcards/index.html", {"request": request, "user": user.dict()}
    )


@boltcards_generic_router.get("/{card_id}", response_class=HTMLResponse)
async def display(request: Request, card_id: str):
    card = await get_card_by_external_id(card_id)
    if not card:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Card does not exist."
        )
    hits = [hit.dict() for hit in await get_hits([card.id])]
    refunds = [
        refund.hit_id for refund in await get_refunds([hit["id"] for hit in hits])
    ]
    card_dict = card.dict()
    # Remove wallet id from card dict
    del card_dict["wallet"]

    return boltcards_renderer().TemplateResponse(
        "boltcards/display.html",
        {"request": request, "card": card_dict, "hits": hits, "refunds": refunds},
    )
