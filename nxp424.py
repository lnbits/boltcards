# https://www.nxp.com/docs/en/application-note/AN12196.pdf

from Cryptodome.Cipher import AES
from Cryptodome.Hash import CMAC

SV2 = "3CC300010080"


def my_cmac(key: bytes, msg: bytes = b"") -> bytes:
    cobj = CMAC.new(key, ciphermod=AES)
    if msg != b"":
        cobj.update(msg)
    return cobj.digest()


def decrypt_sun(sun: bytes, key: bytes) -> tuple[bytes, bytes]:
    ivbytes = b"\x00" * 16

    cipher = AES.new(key, AES.MODE_CBC, ivbytes)
    sun_plain = cipher.decrypt(sun)

    uid = sun_plain[1:8]
    counter = sun_plain[8:11]

    return uid, counter


def get_sun_mac(uid: bytes, counter: bytes, key: bytes) -> bytes:
    sv2prefix = bytes.fromhex(SV2)
    sv2bytes = sv2prefix + uid + counter

    mac1 = my_cmac(key, sv2bytes)
    mac2 = my_cmac(mac1)

    return mac2[1::2]
