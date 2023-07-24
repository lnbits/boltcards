from http import HTTPStatus

from fastapi import Depends, Request
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException
from starlette.responses import HTMLResponse

from lnbits.core.models import User
from lnbits.decorators import check_user_exists

from . import boltcards_ext, boltcards_renderer
from .crud import get_card_by_external_id, get_hits

templates = Jinja2Templates(directory="templates")


@boltcards_ext.get("/", response_class=HTMLResponse)
async def index(request: Request, user: User = Depends(check_user_exists)):
    return boltcards_renderer().TemplateResponse(
        "boltcards/index.html", {"request": request, "user": user.dict()}
    )

@boltcards_ext.get("/{card_id}", response_class=HTMLResponse)
async def display(request: Request, card_id: str):
    card = await get_card_by_external_id(card_id)
    if not card:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Card does not exist."
        )
    hits = await get_hits([card_id])
    return boltcards_renderer().TemplateResponse(
        "boltcards/display.html", {
            "request": request, 
            "card_name": card.card_name,
            
        }
    )