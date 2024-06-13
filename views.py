from http import HTTPStatus

from fastapi import Depends, Request
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException
from starlette.responses import HTMLResponse

from lnbits.core.models import User
from lnbits.decorators import check_user_exists

from . import dfxboltcards_ext, dfxboltcards_renderer
from .crud import get_card_by_external_id, get_hits, get_refunds

templates = Jinja2Templates(directory="templates")


@dfxboltcards_ext.get("/", response_class=HTMLResponse)
async def index(request: Request, user: User = Depends(check_user_exists)):
    return dfxboltcards_renderer().TemplateResponse(
        "dfxboltcards/index.html", {"request": request, "user": user.dict()}
    )


@dfxboltcards_ext.get("/{card_id}", response_class=HTMLResponse)
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
    card = card.dict()
    # Remove wallet id from card dict
    del card["wallet"]

    return dfxboltcards_renderer().TemplateResponse(
        "dfxboltcards/display.html",
        {"request": request, "card": card, "hits": hits, "refunds": refunds},
    )
