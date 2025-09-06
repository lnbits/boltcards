import secrets
from datetime import datetime

from lnbits.db import Database
from lnbits.helpers import urlsafe_short_hash

from .models import Card, CreateCardData, Hit, Refund

db = Database("ext_boltcards")


async def create_card(data: CreateCardData, wallet_id: str) -> Card:
    card_id = urlsafe_short_hash().upper()
    extenal_id = urlsafe_short_hash().lower()

    await db.execute(
        """
        INSERT INTO boltcards.cards (
            id,
            uid,
            external_id,
            wallet,
            card_name,
            counter,
            tx_limit,
            daily_limit,
            pin_limit,
            pin_try,
            pin,
            pin_enable,
            enable,
            k0,
            k1,
            k2,
            otp
        )
        VALUES (
            :id, :uid, :external_id, :wallet, :card_name, :counter,
            :tx_limit, :daily_limit, :pin_limit, :pin_try, :pin, :pin_enable,
            :enable, :k0, :k1, :k2, :otp
        )
        """,
        {
            "id": card_id,
            "uid": data.uid.upper(),
            "external_id": extenal_id,
            "wallet": wallet_id,
            "card_name": data.card_name,
            "counter": data.counter,
            "tx_limit": data.tx_limit,
            "daily_limit": data.daily_limit,
            "pin_limit": data.pin_limit,
            "pin_try": 0,
            "pin": data.pin,
            "pin_enable": False,
            "enable": True,
            "k0": data.k0,
            "k1": data.k1,
            "k2": data.k2,
            "otp": secrets.token_hex(16),
        },
    )
    card = await get_card(card_id)
    assert card, "Newly created card couldn't be retrieved"
    return card


async def update_card(card: Card) -> Card:
    await db.update("boltcards.cards", card)
    return card


async def get_cards(wallet_ids: list[str]) -> list[Card]:
    if len(wallet_ids) == 0:
        return []
    q = ",".join([f"'{wallet_id}'" for wallet_id in wallet_ids])
    return await db.fetchall(
        f"SELECT * FROM boltcards.cards WHERE wallet IN ({q})",
        model=Card,
    )


async def get_card(card_id: str) -> Card | None:
    return await db.fetchone(
        "SELECT * FROM boltcards.cards WHERE id = :id",
        {"id": card_id},
        Card,
    )


async def get_card_by_uid(card_uid: str) -> Card | None:
    return await db.fetchone(
        "SELECT * FROM boltcards.cards WHERE uid = :uid",
        {"uid": card_uid.upper()},
        Card,
    )


async def get_card_by_external_id(external_id: str) -> Card | None:
    return await db.fetchone(
        "SELECT * FROM boltcards.cards WHERE external_id = :ext_id",
        {"ext_id": external_id.lower()},
        Card,
    )


async def get_card_by_otp(otp: str) -> Card | None:
    return await db.fetchone(
        "SELECT * FROM boltcards.cards WHERE otp = :otp",
        {"otp": otp},
        Card,
    )


async def delete_card(card_id: str) -> None:
    # Delete cards
    await db.execute("DELETE FROM boltcards.cards WHERE id = :id", {"id": card_id})
    # Delete hits
    hits = await get_hits([card_id])
    for hit in hits:
        await db.execute("DELETE FROM boltcards.hits WHERE id = :id", {"id": hit.id})
        # Delete refunds
        refunds = await get_refunds([hit.id])
        for refund in refunds:
            await db.execute(
                "DELETE FROM boltcards.refunds WHERE id = :id", {"id": refund.id}
            )


async def update_card_counter(counter: int, card_id: str):
    await db.execute(
        "UPDATE boltcards.cards SET counter = :counter WHERE id = :id",
        {"counter": counter, "id": card_id},
    )


async def enable_disable_card(enable: bool, card_id: str) -> Card | None:
    await db.execute(
        "UPDATE boltcards.cards SET enable = :enable WHERE id = :id",
        {"enable": enable, "id": card_id},
    )
    if enable:
        await update_card_pin_try(0, card_id)
    return await get_card(card_id)


async def update_card_otp(otp: str, card_id: str):
    await db.execute(
        "UPDATE boltcards.cards SET otp = :otp WHERE id = :id",
        {"otp": otp, "id": card_id},
    )


async def update_card_pin_try(pin_try: int, card_id: str):
    await db.execute(
        "UPDATE boltcards.cards SET pin_try = :pin_try WHERE id = :id",
        {"pin_try": pin_try, "id": card_id},
    )


async def get_hit(hit_id: str) -> Hit | None:
    return await db.fetchone(
        "SELECT * FROM boltcards.hits WHERE id = :id",
        {"id": hit_id},
        Hit,
    )


async def get_hits(cards_ids: list[str]) -> list[Hit]:
    if len(cards_ids) == 0:
        return []

    q = ",".join([f"'{card_id}'" for card_id in cards_ids])
    return await db.fetchall(
        f"SELECT * FROM boltcards.hits WHERE card_id IN ({q})",
        model=Hit,
    )


async def get_hits_today(card_id: str) -> list[Hit]:
    rows = await db.fetchall(
        "SELECT * FROM boltcards.hits WHERE card_id = :id",
        {"id": card_id},
        Hit,
    )
    updatedrow = []
    for hit in rows:
        if datetime.now().date() == hit.time.date():
            updatedrow.append(hit)

    return updatedrow


async def spend_hit(card_id: str, amount: int):
    await db.execute(
        "UPDATE boltcards.hits SET spent = :spent, amount = :amount WHERE id = :id",
        {"spent": True, "amount": amount, "id": card_id},
    )
    return await get_hit(card_id)


async def create_hit(card_id, ip, useragent, old_ctr, new_ctr) -> Hit:
    hit_id = urlsafe_short_hash()
    await db.execute(
        """
        INSERT INTO boltcards.hits (
            id,
            card_id,
            ip,
            spent,
            useragent,
            old_ctr,
            new_ctr,
            amount
        )
        VALUES (:id, :card_id, :ip, :spent, :useragent, :old_ctr, :new_ctr, :amount)
        """,
        {
            "id": hit_id,
            "card_id": card_id,
            "ip": ip,
            "spent": False,
            "useragent": useragent,
            "old_ctr": old_ctr,
            "new_ctr": new_ctr,
            "amount": 0,
        },
    )
    hit = await get_hit(hit_id)
    assert hit, "Newly recorded hit couldn't be retrieved"
    return hit


async def create_refund(hit_id, refund_amount) -> Refund:
    refund_id = urlsafe_short_hash()
    await db.execute(
        """
        INSERT INTO boltcards.refunds (
            id,
            hit_id,
            refund_amount
        )
        VALUES (:id, :hit_id, :refund_amount)
        """,
        {
            "id": refund_id,
            "hit_id": hit_id,
            "refund_amount": refund_amount,
        },
    )
    refund = await get_refund(refund_id)
    assert refund, "Newly recorded hit couldn't be retrieved"
    return refund


async def get_refund(refund_id: str) -> Refund | None:
    return await db.fetchone(
        "SELECT * FROM boltcards.refunds WHERE id = :id",
        {"id": refund_id},
        Refund,
    )


async def get_refunds(hits_ids: list[str]) -> list[Refund]:
    if len(hits_ids) == 0:
        return []
    q = ",".join([f"'{hit_id}'" for hit_id in hits_ids])
    return await db.fetchall(
        f"SELECT * FROM boltcards.refunds WHERE hit_id IN ({q})",
        model=Refund,
    )
