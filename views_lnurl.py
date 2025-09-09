import json
import secrets
from http import HTTPStatus
from urllib.parse import urlparse

import bolt11
from fastapi import APIRouter, HTTPException, Query, Request
from lnbits.core.services import create_invoice, pay_invoice
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
from pydantic import parse_obj_as

from .crud import (
    create_hit,
    get_card,
    get_card_by_external_id,
    get_card_by_otp,
    get_card_by_uid,
    get_hit,
    get_hits_today,
    spend_hit,
    update_card_counter,
    update_card_otp,
)
from .models import UIDPost
from .nxp424 import decrypt_sun, get_sun_mac

boltcards_lnurl_router = APIRouter()


# /boltcards/api/v1/scan?p=00000000000000000000000000000000&c=0000000000000000
@boltcards_lnurl_router.get("/api/v1/scan/{external_id}")
async def api_scan(
    p, c, request: Request, external_id: str
) -> LnurlWithdrawResponse | LnurlErrorResponse:
    # some wallets send everything as lower case, no bueno
    p = p.upper()
    c = c.upper()
    card = None
    counter = b""
    card = await get_card_by_external_id(external_id)
    if not card:
        return LnurlErrorResponse(reason="Card not found.")
    if not card.enable:
        return LnurlErrorResponse(reason="Card is disabled.")
    try:
        card_uid, counter = decrypt_sun(bytes.fromhex(p), bytes.fromhex(card.k1))
        if card.uid.upper() != card_uid.hex().upper():
            return LnurlErrorResponse(reason="Card UID mis-match.")
        if c != get_sun_mac(card_uid, counter, bytes.fromhex(card.k2)).hex().upper():
            return LnurlErrorResponse(reason="CMAC does not check.")
    except Exception:
        return LnurlErrorResponse(reason="Error decrypting card.")

    ctr_int = int.from_bytes(counter, "little")

    if ctr_int <= card.counter:
        return LnurlErrorResponse(reason="This link is already used.")

    await update_card_counter(ctr_int, card.id)

    # gathering some info for hit record
    if not request.client:
        return LnurlErrorResponse(reason="Cannot get client info.")
    ip = request.client.host
    if "x-real-ip" in request.headers:
        ip = request.headers["x-real-ip"]
    elif "x-forwarded-for" in request.headers:
        ip = request.headers["x-forwarded-for"]

    agent = request.headers["user-agent"] if "user-agent" in request.headers else ""
    todays_hits = await get_hits_today(card.id)

    hits_amount = 0
    for hit in todays_hits:
        hits_amount += hit.amount
    if hits_amount > int(card.daily_limit):
        return LnurlErrorResponse(reason="Max daily limit spent.")
    hit = await create_hit(card.id, ip, agent, card.counter, ctr_int)

    # create a lud17 lnurlp to support lud19, add payLink field of the withdrawRequest
    lnurlpay_url = str(request.url_for("boltcards.lnurlp_response", hit_id=hit.id))
    pay_link = lnurlpay_url.replace("http://", "lnurlp://").replace(
        "https://", "lnurlp://"
    )
    callback_url = parse_obj_as(
        CallbackUrl, str(request.url_for("boltcards.lnurl_callback", hit_id=hit.id))
    )
    return LnurlWithdrawResponse(
        callback=callback_url,
        k1=hit.id,
        minWithdrawable=MilliSatoshi(1000),
        maxWithdrawable=MilliSatoshi(int(card.tx_limit) * 1000),
        defaultDescription=f"Boltcard (refund address {pay_link})",
        payLink=pay_link,  # type: ignore
    )


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

    hit = await get_hit(hit_id)
    if not hit:
        return LnurlErrorResponse(reason="LNURL-withdraw record not found.")
    if hit.spent:
        return LnurlErrorResponse(reason="Payment already claimed.")
    if not pr:
        return LnurlErrorResponse(reason="Missing payment request.")

    try:
        invoice = bolt11.decode(pr)
    except bolt11.Bolt11Exception:
        return LnurlErrorResponse(reason="Failed to decode payment request.")
    if not invoice.amount_msat:
        return LnurlErrorResponse(reason="Invoice has no amount.")
    card = await get_card(hit.card_id)
    if not card:
        return LnurlErrorResponse(reason="Card not found.")
    hit = await spend_hit(card_id=hit.id, amount=int(invoice.amount_msat / 1000))
    if not hit:
        return LnurlErrorResponse(reason="Failed to update hit as spent.")
    try:
        await pay_invoice(
            wallet_id=card.wallet,
            payment_request=pr,
            max_sat=int(card.tx_limit),
            extra={"tag": "boltcards", "hit": hit.id},
        )
        return LnurlSuccessResponse()
    except Exception as exc:
        return LnurlErrorResponse(reason=f"Payment failed - {exc}")


# /boltcards/api/v1/auth?a=00000000000000000000000000000000
@boltcards_lnurl_router.get("/api/v1/auth")
async def api_auth(a, request: Request):
    if a == "00000000000000000000000000000000":
        response = {"k0": "0" * 32, "k1": "1" * 32, "k2": "2" * 32}
        return response

    card = await get_card_by_otp(a)
    if not card:
        raise HTTPException(
            detail="Card does not exist.", status_code=HTTPStatus.NOT_FOUND
        )

    new_otp = secrets.token_hex(16)
    await update_card_otp(new_otp, card.id)

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

    return response


# /boltcards/api/v1/auth?a=00000000000000000000000000000000
@boltcards_lnurl_router.post("/api/v1/auth")
async def api_auth_post(a: str, request: Request, data: UIDPost, wipe: bool = False):
    card = None
    if wipe:
        card = await get_card_by_otp(a)
    else:
        if not data.UID:
            raise HTTPException(
                detail="Missing UID.", status_code=HTTPStatus.BAD_REQUEST
            )

        card = await get_card_by_uid(data.UID)
    if not card:
        raise HTTPException(
            detail="Card does not exist.", status_code=HTTPStatus.NOT_FOUND
        )
    new_otp = secrets.token_hex(16)
    await update_card_otp(new_otp, card.id)
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
