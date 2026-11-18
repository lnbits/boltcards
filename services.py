import bolt11
from lnbits.core.services import pay_invoice
from lnbits.exceptions import PaymentError
from loguru import logger

from .crud import create_hit, get_card_by_external_id, get_hit, release_hit, spend_hit
from .models import Hit
from .nxp424 import decrypt_sun, get_sun_mac

# Longest reason shown to the payer (it ends up on terminals and small displays).
MAX_REASON_LENGTH = 100


def payment_error_reason(exc: PaymentError) -> str:
    """Short single-line reason for the payer, taken from LNbits' own message.

    PaymentError messages are curated by LNbits ("Insufficient balance.", ...),
    unlike arbitrary exceptions, so they are safe to show. Only LNbits' status
    decides the prefix: PaymentError defaults to status "pending", also for
    plain failures without an explicit status, so the message is shown as is
    unless the payment is known to have failed.
    """
    message = " ".join(str(exc.message or "").split())[:MAX_REASON_LENGTH]
    if exc.status == "failed":
        return f"Payment failed: {message}" if message else "Payment failed."
    return message or "Payment is still pending."


async def scan_card(external_id: str, p: str, c: str, ip: str, useragent: str) -> Hit:
    card = await get_card_by_external_id(external_id)
    if not card:
        raise ValueError("Card not found.")
    if not card.enable:
        raise ValueError("Card is disabled.")
    try:
        card_uid, counter = decrypt_sun(bytes.fromhex(p), bytes.fromhex(card.k1))
        expected_mac = get_sun_mac(card_uid, counter, bytes.fromhex(card.k2))
    except Exception as exc:
        raise ValueError("Error decrypting card.") from exc
    if card.uid.upper() != card_uid.hex().upper():
        raise ValueError("Card UID mis-match.")
    if c.upper() != expected_mac.hex().upper():
        raise ValueError("CMAC does not check.")
    return await create_hit(card, ip, useragent, int.from_bytes(counter, "little"))


async def pay_card_invoice(hit_id: str, payment_request: str | None) -> None:
    hit = await get_hit(hit_id)
    if not hit:
        raise ValueError("LNURL-withdraw record not found.")
    if hit.spent:
        raise ValueError("Payment already claimed.")
    if not payment_request:
        raise ValueError("Missing payment request.")
    try:
        invoice = bolt11.decode(payment_request)
    except bolt11.Bolt11Exception as exc:
        raise ValueError("Failed to decode payment request.") from exc
    if not invoice.amount_msat:
        raise ValueError("Invoice has no amount.")
    hit, card = await spend_hit(hit.id, int(invoice.amount_msat))
    try:
        await pay_invoice(
            wallet_id=card.wallet,
            payment_request=payment_request,
            max_sat=card.tx_limit,
            extra={"tag": "boltcards", "hit": hit.id},
        )
    except PaymentError as exc:
        if exc.status == "failed":
            await release_hit(hit.id)
        # The real reason belongs in the server log; the payer gets a short text.
        logger.warning(
            "Boltcard payment not completed: card={} hit={} status={}: {}",
            card.id,
            hit.id,
            exc.status,
            exc.message,
        )
        raise ValueError(payment_error_reason(exc)) from exc
    except Exception as exc:
        # shortcut: unknown outcomes keep their allowance until UTC midnight;
        # reconcile payment status to release it sooner. The details stay in the
        # log, the payer only gets a generic text.
        logger.warning(
            "Boltcard payment outcome unknown: card={} hit={} {}: {}",
            card.id,
            hit.id,
            type(exc).__name__,
            exc,
        )
        raise ValueError("Payment failed or is still pending.") from exc
