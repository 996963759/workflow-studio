import base64
import hashlib
import hmac
import os

from .config import MODEL_CONFIG_SECRET


def _keystream(nonce: bytes, length: int) -> bytes:
    seed = MODEL_CONFIG_SECRET.encode("utf-8")
    output = bytearray()
    counter = 0
    while len(output) < length:
        output.extend(hashlib.sha256(seed + nonce + counter.to_bytes(4, "big")).digest())
        counter += 1
    return bytes(output[:length])


def protect_secret(value: str) -> str:
    raw = value.encode("utf-8")
    nonce = os.urandom(16)
    stream = _keystream(nonce, len(raw))
    cipher = bytes(left ^ right for left, right in zip(raw, stream))
    mac = hmac.new(MODEL_CONFIG_SECRET.encode("utf-8"), nonce + cipher, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(nonce + mac + cipher).decode("ascii")


def reveal_secret(value: str) -> str:
    try:
        payload = base64.urlsafe_b64decode(value.encode("ascii"))
        nonce = payload[:16]
        mac = payload[16:48]
        cipher = payload[48:]
        expected = hmac.new(MODEL_CONFIG_SECRET.encode("utf-8"), nonce + cipher, hashlib.sha256).digest()
        if not hmac.compare_digest(mac, expected):
            raise ValueError("secret signature mismatch")
        stream = _keystream(nonce, len(cipher))
        raw = bytes(left ^ right for left, right in zip(cipher, stream))
        return raw.decode("utf-8")
    except Exception as error:  # noqa: BLE001 - convert low-level parsing issues into one message.
        raise ValueError("Unable to reveal protected secret") from error


def mask_secret(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}{'*' * 8}{value[-4:]}"
