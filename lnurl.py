import json
import secrets
from http import HTTPStatus
from urllib.parse import urlparse
from datetime import datetime

from fastapi import HTTPException, Query, Request
from lnurl import encode as lnurl_encode
from lnurl.types import LnurlPayMetadata
from starlette.responses import HTMLResponse

from lnbits import bolt11
from lnbits.core.services import create_invoice, calculate_fiat_amounts
from lnbits.core.views.api import pay_invoice
from lnbits.core.crud import (
    get_standalone_payment,
    get_wallet,
)

from . import boltcards_ext
from .crud import (
    create_hit,
    get_card,
    get_card_by_external_id,
    get_card_by_otp,
    get_hit,
    get_hits_today,
    get_hits_this_month,
    spend_hit,
    link_hit,
    update_card_counter,
    update_card_otp,
)
from .nxp424 import decryptSUN, getSunMAC

###############LNURLWITHDRAW#################


@boltcards_ext.get("/api/v1/balance/{external_id}")
async def api_balance(p, c, request: Request, external_id: str):
    # some wallets send everything as lower case, no bueno
    p = p.upper()
    c = c.upper()
    card = None
    counter = b""
    card = await get_card_by_external_id(external_id)
    if not card:
        return {"status": "ERROR", "reason": "No card."}
    if not card.enable:
        return {"status": "ERROR", "reason": "Card is disabled."}
    if card.expiration_date is not None and card.expiration_date != "" and datetime.strptime(card.expiration_date, '%Y-%m-%d') < datetime.now():
        return {"status": "ERROR", "reason": "Card is expired."}
    try:
        card_uid, counter = decryptSUN(bytes.fromhex(p), bytes.fromhex(card.k1))
        if card.uid.upper() != card_uid.hex().upper():
            return {"status": "ERROR", "reason": "Card UID mis-match."}
        if c != getSunMAC(card_uid, counter, bytes.fromhex(card.k2)).hex().upper():
            return {"status": "ERROR", "reason": "CMAC does not check."}
    except:
        return {"status": "ERROR", "reason": "Error decrypting card."}

    ctr_int = int.from_bytes(counter, "little")

    if ctr_int <= card.counter:
        return {"status": "ERROR", "reason": "This link is already used."}

    await update_card_counter(ctr_int, card.id)

    wallet = await get_wallet(card.wallet)
    balance = 0

    if wallet:
        balance = wallet.balance_msat / 1000

    return {
        "balance": balance,
    }


# /boltcards/api/v1/scan?p=00000000000000000000000000000000&c=0000000000000000
@boltcards_ext.get("/api/v1/scan/{external_id}")
async def api_scan(p, c, request: Request, external_id: str):
    # some wallets send everything as lower case, no bueno
    p = p.upper()
    c = c.upper()
    card = None
    counter = b""
    card = await get_card_by_external_id(external_id)
    if not card:
        return {"status": "ERROR", "reason": "No card."}
    if not card.enable:
        return {"status": "ERROR", "reason": "Card is disabled."}
    if card.expiration_date is not None and card.expiration_date != "" and datetime.strptime(card.expiration_date, '%Y-%m-%d') < datetime.now():
        return {"status": "ERROR", "reason": "Card is expired."}
    try:
        card_uid, counter = decryptSUN(bytes.fromhex(p), bytes.fromhex(card.k1))
        if card.uid.upper() != card_uid.hex().upper():
            return {"status": "ERROR", "reason": "Card UID mis-match."}
        if c != getSunMAC(card_uid, counter, bytes.fromhex(card.k2)).hex().upper():
            return {"status": "ERROR", "reason": "CMAC does not check."}
    except:
        return {"status": "ERROR", "reason": "Error decrypting card."}

    ctr_int = int.from_bytes(counter, "little")

    if ctr_int <= card.counter:
        return {"status": "ERROR", "reason": "This link is already used."}

    await update_card_counter(ctr_int, card.id)

    # gathering some info for hit record
    assert request.client
    ip = request.client.host
    if "x-real-ip" in request.headers:
        ip = request.headers["x-real-ip"]
    elif "x-forwarded-for" in request.headers:
        ip = request.headers["x-forwarded-for"]

    agent = request.headers["user-agent"] if "user-agent" in request.headers else ""
    todays_hits = await get_hits_today(card.id)

    hits_amount = 0
    for hit in todays_hits:
        if card.limit_type == "fiat":
            payment = await get_standalone_payment(checking_id_or_hash=hit.payment_hash, wallet_id=card.wallet)
            if payment != None and payment.extra != None:
                hits_amount = hits_amount + payment.extra.get("wallet_fiat_amount")
        else:
            hits_amount = hits_amount + hit.amount
    if hits_amount > card.daily_limit:
        return {"status": "ERROR", "reason": "Max daily limit spent."}

    this_month_hits = await get_hits_this_month(card.id)

    this_month_hits_amount = 0
    for hit in this_month_hits:
        if card.limit_type == "fiat":
            payment = await get_standalone_payment(checking_id_or_hash=hit.payment_hash, wallet_id=card.wallet)
            if payment != None and payment.extra != None:
                this_month_hits_amount = this_month_hits_amount + payment.extra.get("wallet_fiat_amount")
        else:
            this_month_hits_amount = this_month_hits_amount + hit.amount
    if this_month_hits_amount > card.monthly_limit:
        return {"status": "ERROR", "reason": "Max monthly limit spent."}

    hit = await create_hit(card.id, ip, agent, card.counter, ctr_int)

    # the raw lnurl
    lnurlpay_raw = str(request.url_for("boltcards.lnurlp_response", hit_id=hit.id))
    # bech32 encoded lnurl
    lnurlpay_bech32 = lnurl_encode(lnurlpay_raw)
    # create a lud17 lnurlp to support lud19, add to payLink field of the withdrawRequest
    lnurlpay_nonbech32_lud17 = lnurlpay_raw.replace("https://", "lnurlp://").replace("http://","lnurlp://")

    return {
        "tag": "withdrawRequest",
        "callback": str(request.url_for("boltcards.lnurl_callback", hit_id=hit.id)),
        "k1": hit.id,
        "minWithdrawable": 1 * 1000,
        "maxWithdrawable": card.tx_limit * 1000,
        "defaultDescription": f"Boltcard (refund address lnurl://{lnurlpay_bech32})",
        "payLink": lnurlpay_nonbech32_lud17,  # LUD-19 compatibility
    }


@boltcards_ext.get(
    "/api/v1/lnurl/cb/{hit_id}",
    status_code=HTTPStatus.OK,
    name="boltcards.lnurl_callback",
)
async def lnurl_callback(
    hit_id: str,
    k1: str = Query(None),
    pr: str = Query(None),
):
    if not k1:
        return {"status": "ERROR", "reason": "Missing K1 token"}

    hit = await get_hit(k1)

    if not hit:
        return {
            "status": "ERROR",
            "reason": "Record not found for this charge (bad k1)",
        }
    if hit.spent:
        return {"status": "ERROR", "reason": "Payment already claimed"}
    if not pr:
        return {"status": "ERROR", "reason": "Missing payment request"}

    try:
        invoice = bolt11.decode(pr)
    except:
        return {"status": "ERROR", "reason": "Failed to decode payment request"}

    card = await get_card(hit.card_id)
    assert card

    todays_hits = await get_hits_today(card.id)

    hits_amount = 0

    if card.limit_type == "fiat":
        amount_sat, extra = await calculate_fiat_amounts(wallet_id=card.wallet, amount=invoice.amount_msat / 1000)
        hits_amount = extra.get("wallet_fiat_amount")
    else:
        hits_amount = int(invoice.amount_msat / 1000)

    for hit in todays_hits:
        if card.limit_type == "fiat":
            payment = await get_standalone_payment(checking_id_or_hash=hit.payment_hash, wallet_id=card.wallet)
            if payment != None and payment.extra != None:
                hits_amount = hits_amount + payment.extra.get("wallet_fiat_amount")
        else:
            hits_amount = hits_amount + hit.amount
    if hits_amount > card.daily_limit:
        return {"status": "ERROR", "reason": "Max daily limit spent."}

    this_month_hits = await get_hits_this_month(card.id)

    this_month_hits_amount = int(invoice.amount_msat / 1000)
    for hit in this_month_hits:
        if card.limit_type == "fiat":
            payment = await get_standalone_payment(checking_id_or_hash=hit.payment_hash, wallet_id=card.wallet)
            if payment != None and payment.extra != None:
                this_month_hits_amount = this_month_hits_amount + payment.extra.get("wallet_fiat_amount")
        else:
            this_month_hits_amount = this_month_hits_amount + hit.amount
    if this_month_hits_amount > card.monthly_limit:
        return {"status": "ERROR", "reason": "Max monthly limit spent."}

    hit = await spend_hit(id=hit.id, amount=int(invoice.amount_msat / 1000))
    assert hit
    try:
        payment_hash = await pay_invoice(
            wallet_id=card.wallet,
            payment_request=pr,
            max_sat=card.tx_limit,
            extra={"tag": "boltcards", "hit": hit.id},
        )
        await link_hit(id=hit.id, hash=payment_hash)
        return {"status": "OK"}
    except Exception as exc:
        return {"status": "ERROR", "reason": f"Payment failed - {exc}"}


# /boltcards/api/v1/auth?a=00000000000000000000000000000000
@boltcards_ext.get("/api/v1/auth")
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


###############LNURLPAY REFUNDS#################


@boltcards_ext.get(
    "/api/v1/lnurlp/{hit_id}",
    response_class=HTMLResponse,
    name="boltcards.lnurlp_response",
)
async def lnurlp_response(req: Request, hit_id: str):
    hit = await get_hit(hit_id)
    assert hit
    card = await get_card(hit.card_id)
    assert card
    if not hit:
        return {"status": "ERROR", "reason": "LNURL-pay record not found."}
    if not card.enable:
        return {"status": "ERROR", "reason": "Card is disabled."}
    payResponse = {
        "tag": "payRequest",
        "callback": str(req.url_for("boltcards.lnurlp_callback", hit_id=hit_id)),
        "metadata": LnurlPayMetadata(json.dumps([["text/plain", "Refund"]])),
        "minSendable": 1 * 1000,
        "maxSendable": card.tx_limit * 1000,
    }
    return json.dumps(payResponse)


@boltcards_ext.get(
    "/api/v1/lnurlp/cb/{hit_id}",
    response_class=HTMLResponse,
    name="boltcards.lnurlp_callback",
)
async def lnurlp_callback(hit_id: str, amount: str = Query(None)):
    hit = await get_hit(hit_id)
    assert hit
    card = await get_card(hit.card_id)
    assert card
    if not hit:
        return {"status": "ERROR", "reason": "LNURL-pay record not found."}

    _, payment_request = await create_invoice(
        wallet_id=card.wallet,
        amount=int(int(amount) / 1000),
        memo=f"Refund {hit_id}",
        unhashed_description=LnurlPayMetadata(
            json.dumps([["text/plain", "Refund"]])
        ).encode(),
        extra={"refund": hit_id},
    )

    payResponse = {"pr": payment_request, "routes": []}

    return json.dumps(payResponse)
