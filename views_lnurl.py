import json
from http import HTTPStatus
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from limits import parse as parse_limit
from lnbits.core.services import create_invoice
from lnurl import (
    CallbackUrl,
    LightningInvoice,
    LnurlErrorResponse,
    LnurlPayActionResponse,
    LnurlPayMetadata,
    LnurlPayResponse,
    LnurlSuccessResponse,
    LnurlWithdrawResponse,
    Max144Str,
    MessageAction,
    MilliSatoshi,
)
from loguru import logger
from pydantic import parse_obj_as

from .crud import consume_card_otp, get_card, get_hit
from .models import UIDPost
from .services import pay_card_invoice, scan_card

boltcards_lnurl_router = APIRouter()


# /boltcards/api/v1/scan?p=00000000000000000000000000000000&c=0000000000000000
@boltcards_lnurl_router.get(
    "/api/v1/scan/{external_id}",
    response_model=LnurlWithdrawResponse | LnurlErrorResponse,
)
async def api_scan(
    p: str, c: str, request: Request, external_id: str
) -> JSONResponse | LnurlErrorResponse:
    if not request.client:
        return LnurlErrorResponse(reason="Cannot get client info.")
    try:
        hit = await scan_card(
            external_id,
            p,
            c,
            request.client.host,
            request.headers.get("user-agent", ""),
        )
    except ValueError as exc:
        return LnurlErrorResponse(reason=str(exc))

    # create a lud17 lnurlp to support lud19, add payLink field of the withdrawRequest
    lnurlpay_url = str(request.url_for("boltcards.lnurlp_response", hit_id=hit.id))
    pay_link = lnurlpay_url.replace("http://", "lnurlp://").replace(
        "https://", "lnurlp://"
    )
    callback_url = parse_obj_as(
        CallbackUrl, str(request.url_for("boltcards.lnurl_callback", hit_id=hit.id))
    )
    response = LnurlWithdrawResponse(
        callback=callback_url,
        k1=hit.id,
        minWithdrawable=MilliSatoshi(1000),
        maxWithdrawable=MilliSatoshi(hit.max_msat),
        defaultDescription=f"Boltcard (refund address {pay_link})",
    )
    # lnurl's payLink validator loses the lnurlp scheme during model validation.
    return JSONResponse({**response.dict(), "payLink": pay_link})


@boltcards_lnurl_router.get(
    "/api/v1/lnurl/cb/{hit_id}",
    status_code=HTTPStatus.OK,
    name="boltcards.lnurl_callback",
)
async def lnurl_callback(
    hit_id: str,
    k1: str = Query(None),
    pr: str = Query(None),
) -> LnurlErrorResponse | LnurlSuccessResponse:
    if not k1:
        return LnurlErrorResponse(reason="Missing K1 token")
    if k1 != hit_id:
        return LnurlErrorResponse(reason="K1 token does not match.")

    try:
        await pay_card_invoice(hit_id, pr)
    except ValueError as exc:
        return LnurlErrorResponse(reason=str(exc))
    return LnurlSuccessResponse()


def auth_request(request: Request, response: Response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    # Reuse LNbits' configured limiter storage and trusted transport client address.
    limiter = request.app.state.limiter
    peer = request.client.host if request.client else "unknown"
    if not limiter.limiter.hit(parse_limit("10/minute"), "boltcards-auth", peer):
        logger.warning("Boltcard auth rate limit exceeded")
        raise HTTPException(
            status_code=HTTPStatus.TOO_MANY_REQUESTS, detail="Try again later."
        )


@boltcards_lnurl_router.get("/api/v1/auth", dependencies=[Depends(auth_request)])
async def api_auth(a: str, request: Request, wipe: bool = False):
    card = await consume_card_otp(a, wipe=wipe)
    if not card:
        logger.warning("Boltcard auth rejected")
        raise HTTPException(
            detail="Invalid or expired authorization.", status_code=HTTPStatus.NOT_FOUND
        )
    lnurlw_base = (
        f"{urlparse(str(request.url)).netloc}/boltcards/api/v1/scan/{card.external_id}"
    )
    response = {
        "card_name": card.card_name,
        "id": str(1),
        "k0": card.k0,
        "k1": card.k1,
        "k2": card.k2,
        "k3": card.k1,
        "k4": card.k2,
        "lnurlw_base": "lnurlw://" + lnurlw_base,
        "protocol_name": "new_bolt_card_response",
        "protocol_version": str(1),
    }
    if wipe:
        response["action"] = "wipe"
    return response


@boltcards_lnurl_router.post("/api/v1/auth", dependencies=[Depends(auth_request)])
async def api_auth_post(a: str, request: Request, data: UIDPost, wipe: bool = False):
    card = await consume_card_otp(a, wipe=wipe, uid=data.UID)
    if not card:
        logger.warning("Boltcard auth rejected")
        raise HTTPException(
            detail="Invalid or expired authorization.", status_code=HTTPStatus.NOT_FOUND
        )
    lnurlw_base = (
        f"{urlparse(str(request.url)).netloc}/boltcards/api/v1/scan/{card.external_id}"
    )
    response = {
        "CARD_NAME": card.card_name,
        "ID": str(1),
        "K0": card.k0,
        "K1": card.k1,
        "K2": card.k2,
        "K3": card.k1,
        "K4": card.k2,
        "LNURLW_BASE": "LNURLW://" + lnurlw_base,
        "LNURLW": "LNURLW://" + lnurlw_base,
        "PROTOCOL_NAME": "NEW_BOLT_CARD_RESPONSE",
        "PROTOCOL_VERSION": str(1),
    }
    if wipe:
        response["action"] = "wipe"
    return response


###############LNURLPAY REFUNDS#################
@boltcards_lnurl_router.get(
    "/api/v1/lnurlp/cb/{hit_id}",
    name="boltcards.lnurlp_callback",
)
async def lnurlp_callback(
    hit_id: str, amount: str = Query(None)
) -> LnurlPayActionResponse | LnurlErrorResponse:
    hit = await get_hit(hit_id)
    if not hit:
        return LnurlErrorResponse(reason="LNURL-pay record not found.")
    if not hit.spent:
        return LnurlErrorResponse(reason="Withdrawal has not been claimed yet.")
    card = await get_card(hit.card_id)
    if not card:
        return LnurlErrorResponse(reason="Card not found.")
    if not card.enable:
        return LnurlErrorResponse(reason="Card is disabled.")
    if not amount:
        return LnurlErrorResponse(reason="Missing amount.")
    if int(amount) < 1000:
        return LnurlErrorResponse(reason="Amount too low.")
    if int(amount) > int(card.tx_limit) * 1000:
        return LnurlErrorResponse(reason="Amount too high.")

    payment = await create_invoice(
        wallet_id=card.wallet,
        amount=int(int(amount) / 1000),
        memo=f"Refund {hit_id}",
        unhashed_description=LnurlPayMetadata(
            json.dumps([["text/plain", "Refund"]])
        ).encode(),
        extra={"refund": hit_id},
    )
    action = MessageAction(message=Max144Str("Refunded!"))
    invoice = parse_obj_as(LightningInvoice, payment.bolt11)
    return LnurlPayActionResponse(pr=invoice, successAction=action)


@boltcards_lnurl_router.get(
    "/api/v1/lnurlp/{hit_id}",
    name="boltcards.lnurlp_response",
)
async def lnurlp_response(
    req: Request, hit_id: str
) -> LnurlPayResponse | LnurlErrorResponse:
    hit = await get_hit(hit_id)
    if not hit:
        return LnurlErrorResponse(reason="LNURL-pay hit not found.")
    card = await get_card(hit.card_id)
    if not card:
        return LnurlErrorResponse(reason="Card not found.")
    if not card.enable:
        return LnurlErrorResponse(reason="Card is disabled.")
    callback_url = parse_obj_as(
        CallbackUrl, str(req.url_for("boltcards.lnurlp_callback", hit_id=hit_id))
    )
    return LnurlPayResponse(
        callback=callback_url,
        minSendable=MilliSatoshi(1000),
        maxSendable=MilliSatoshi(int(card.tx_limit) * 1000),
        metadata=LnurlPayMetadata(json.dumps([["text/plain", "Refund"]])),
    )
