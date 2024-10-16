import asyncio

from lnbits.core.crud import update_payment
from lnbits.core.models import Payment
from lnbits.tasks import register_invoice_listener

from .crud import create_refund, get_hit


async def wait_for_paid_invoices():
    invoice_queue = asyncio.Queue()
    register_invoice_listener(invoice_queue, "ext_boltcards")

    while True:
        payment = await invoice_queue.get()
        await on_invoice_paid(payment)


async def on_invoice_paid(payment: Payment) -> None:

    if not payment.extra or not payment.extra.get("refund"):
        return

    if payment.extra.get("wh_status"):
        # this webhook has already been sent
        return

    hit = await get_hit(str(payment.extra.get("refund")))

    if hit:
        await create_refund(hit_id=hit.id, refund_amount=(payment.amount / 1000))
        payment.extra["wh_status"] = 1
        await update_payment(payment)
