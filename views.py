from http import HTTPStatus

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from lnbits.core.models import User
from lnbits.decorators import check_user_exists
from lnbits.helpers import template_renderer

from .crud import get_card_by_external_id, get_hits, get_refunds

boltcards_generic_router = APIRouter()


def boltcards_renderer():
    return template_renderer(["boltcards/templates"])


@boltcards_generic_router.get("/", response_class=HTMLResponse)
async def index(request: Request, user: User = Depends(check_user_exists)):
    return boltcards_renderer().TemplateResponse(
        "boltcards/index.html", {"request": request, "user": user.json()}
    )


@boltcards_generic_router.get("/{card_id}", response_class=HTMLResponse)
async def display(request: Request, card_id: str):
    card = await get_card_by_external_id(card_id)
    if not card:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Card does not exist."
        )
    hits = await get_hits([card.id])
    hits_json = [hit.json() for hit in hits]
    refunds = [refund.hit_id for refund in await get_refunds([hit.id for hit in hits])]
    card_json = card.json(exclude={"wallet"})
    return boltcards_renderer().TemplateResponse(
        "boltcards/display.html",
        {"request": request, "card": card_json, "hits": hits_json, "refunds": refunds},
    )
