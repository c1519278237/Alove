import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from cryptography.fernet import Fernet, InvalidToken

from .config import get_settings


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return secrets.token_hex(16)


def _fernet() -> Fernet:
    settings = get_settings()
    if settings.app_encryption_key:
        key = settings.app_encryption_key.encode("ascii")
    else:
        digest = hashlib.sha256(settings.app_secret_key.encode("utf-8")).digest()
        key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_text(value: str | None) -> str | None:
    if value is None:
        return None
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_text(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        return "[无法解密]"


def encrypt_bytes(value: bytes) -> bytes:
    return _fernet().encrypt(value)


def decrypt_bytes(value: bytes) -> bytes:
    return _fernet().decrypt(value)


def normalize_phone(phone: str) -> str:
    normalized = "".join(ch for ch in phone.strip() if ch.isdigit() or ch == "+")
    if len(normalized.replace("+", "")) < 6:
        raise ValueError("手机号格式不正确")
    return normalized


def phone_hash(phone: str) -> str:
    settings = get_settings()
    return hmac.new(
        settings.app_secret_key.encode("utf-8"),
        normalize_phone(phone).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def hash_code(code: str) -> str:
    settings = get_settings()
    return hmac.new(
        settings.app_secret_key.encode("utf-8"), code.encode("ascii"), hashlib.sha256
    ).hexdigest()


def verify_code(code: str, expected_hash: str) -> bool:
    return hmac.compare_digest(hash_code(code), expected_hash)


def create_access_token(user_id: str) -> str:
    settings = get_settings()
    now = utc_now()
    payload: dict[str, Any] = {
        "sub": user_id,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_ttl_minutes),
    }
    return jwt.encode(payload, settings.app_secret_key, algorithm="HS256")


def decode_access_token(token: str) -> str:
    settings = get_settings()
    payload = jwt.decode(token, settings.app_secret_key, algorithms=["HS256"])
    if payload.get("type") != "access" or not payload.get("sub"):
        raise jwt.InvalidTokenError("invalid token type")
    return str(payload["sub"])
