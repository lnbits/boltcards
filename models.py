import json
from datetime import datetime

from fastapi import Query, Request
from lnurl import Lnurl
from lnurl import encode as lnurl_encode
from lnurl.types import LnurlPayMetadata
from pydantic import BaseModel, Field

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
    pin_limit: int
    pin_try: int
    pin: str
    pin_enable: bool
    enable: bool
    k0: str
    k1: str
    k2: str
    prev_k0: str
    prev_k1: str
    prev_k2: str
    otp: str
    time: datetime

    def lnurl(self, req: Request) -> Lnurl:
        url = str(
            req.url_for("boltcard.lnurl_response", device_id=self.id, _external=True)
        )
        return lnurl_encode(url)

    async def lnurlpay_metadata(self) -> LnurlPayMetadata:
        return LnurlPayMetadata(json.dumps([["text/plain", self.card_name]]))


class CreateCardData(BaseModel):
    card_name: str = Query(...)
    uid: str = Query(...)
    counter: int = Query(0)
    tx_limit: int = Query(0)
    daily_limit: int = Query(0)
    pin_limit: int = Query(0)
    pin_try: int = Query(0)
    pin: str = Query('')
    pin_enable: str = Query(False)
    enable: bool = Query(True)
    k0: str = Query(ZERO_KEY)
    k1: str = Query(ZERO_KEY)
    k2: str = Query(ZERO_KEY)
    prev_k0: str = Query(ZERO_KEY)
    prev_k1: str = Query(ZERO_KEY)
    prev_k2: str = Query(ZERO_KEY)


class Hit(BaseModel):
    id: str
    card_id: str
    ip: str
    spent: bool
    useragent: str
    old_ctr: int
    new_ctr: int
    amount: int
    time: datetime


class Refund(BaseModel):
    id: str
    hit_id: str
    refund_amount: int
    time: datetime


class UIDPost(BaseModel):
    UID: str = Field(description="The UID of the card.")
    LNURLW: str = Field(description="The LNURLW of the card.")
