import json
from sqlite3 import Row

from fastapi import Query, Request
from lnurl import Lnurl
from lnurl import encode as lnurl_encode
from lnurl.types import LnurlPayMetadata
from pydantic import BaseModel
from pydantic.schema import Optional

ZERO_KEY = "00000000000000000000000000000000"


class Card(BaseModel):
    id: str
    wallet: str
    card_name: str
    uid: str
    external_id: str
    counter: int
    tx_limit: int
    daily_limit: int
    monthly_limit: int
    limit_type: str
    enable: bool
    k0: str
    k1: str
    k2: str
    prev_k0: str
    prev_k1: str
    prev_k2: str
    otp: str
    time: int
    expiration_date: Optional[str]

    @classmethod
    def from_row(cls, row: Row) -> "Card":
        return cls(**dict(row))

    def lnurl(self, req: Request) -> Lnurl:
        url = str(req.url_for("boltcard.lnurl_response", device_id=self.id, _external=True))
        return lnurl_encode(url)

    async def lnurlpay_metadata(self) -> LnurlPayMetadata:
        return LnurlPayMetadata(json.dumps([["text/plain", self.card_name]]))


class CreateCardData(BaseModel):
    card_name: str = Query(...)
    uid: str = Query(...)
    counter: int = Query(0)
    tx_limit: int = Query(0)
    daily_limit: int = Query(0)
    monthly_limit: int = Query(0)
    limit_type: str = Query("sats")
    enable: bool = Query(True)
    k0: str = Query(ZERO_KEY)
    k1: str = Query(ZERO_KEY)
    k2: str = Query(ZERO_KEY)
    prev_k0: str = Query(ZERO_KEY)
    prev_k1: str = Query(ZERO_KEY)
    prev_k2: str = Query(ZERO_KEY)
    expiration_date: Optional[str]

class Hit(BaseModel):
    id: str
    card_id: str
    ip: str
    spent: bool
    useragent: str
    old_ctr: int
    new_ctr: int
    amount: int
    time: int
    payment_hash: Optional[str]

    @classmethod
    def from_row(cls, row: Row) -> "Hit":
        return cls(**dict(row))


class Refund(BaseModel):
    id: str
    hit_id: str
    refund_amount: int
    time: int

    @classmethod
    def from_row(cls, row: Row) -> "Refund":
        return cls(**dict(row))
