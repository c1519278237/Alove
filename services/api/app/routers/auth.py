import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..deps import get_current_user
from ..errors import AppError
from ..models import SmsCode, User, UserProfile
from ..schemas import (
    SmsRequest,
    SmsRequestResult,
    SmsVerify,
    TokenResult,
    UserOut,
    UserProfilePatch,
)
from ..security import (
    create_access_token,
    encrypt_text,
    hash_code,
    new_id,
    normalize_phone,
    phone_hash,
    utc_now,
    verify_code,
)

router = APIRouter(prefix="/auth", tags=["auth"])
me_router = APIRouter(tags=["me"])


@router.post("/sms/request", response_model=SmsRequestResult)
def request_sms(payload: SmsRequest, db: Session = Depends(get_db)) -> SmsRequestResult:
    settings = get_settings()
    try:
        phone = normalize_phone(payload.phone)
    except ValueError as exc:
        raise AppError("INVALID_PHONE", str(exc), 422) from exc
    code = f"{secrets.randbelow(1_000_000):06d}"
    record = SmsCode(
        phone_hash=phone_hash(phone),
        code_hash=hash_code(code),
        expires_at=utc_now() + timedelta(seconds=settings.sms_code_ttl_seconds),
    )
    db.add(record)
    db.commit()
    # Local/debug returns the code so the project is immediately testable.
    # Pilot and production must use a reviewed SMS provider and never echo it.
    debug_code = code if settings.is_local and settings.sms_provider == "console" else None
    return SmsRequestResult(
        request_id=record.id,
        expires_in=settings.sms_code_ttl_seconds,
        debug_code=debug_code,
    )


@router.post("/sms/verify", response_model=TokenResult)
def verify_sms(payload: SmsVerify, db: Session = Depends(get_db)) -> TokenResult:
    try:
        phone = normalize_phone(payload.phone)
    except ValueError as exc:
        raise AppError("INVALID_PHONE", str(exc), 422) from exc
    hashed_phone = phone_hash(phone)
    record = db.scalar(
        select(SmsCode)
        .where(SmsCode.phone_hash == hashed_phone, SmsCode.used_at.is_(None))
        .order_by(SmsCode.created_at.desc())
        .limit(1)
    )
    if record is None or not verify_code(payload.code, record.code_hash):
        raise AppError("INVALID_SMS_CODE", "验证码错误或已失效", 401)
    expires_at = record.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=utc_now().tzinfo)
    if expires_at < utc_now():
        raise AppError("INVALID_SMS_CODE", "验证码错误或已失效", 401)
    record.used_at = utc_now()

    user = db.scalar(select(User).where(User.phone_hash == hashed_phone))
    if user is None:
        user = User(
            phone_hash=hashed_phone,
            phone_encrypted=encrypt_text(phone) or "",
            display_name=payload.display_name or "新用户",
        )
        db.add(user)
        db.flush()
        db.add(UserProfile(user_id=user.id))
    elif user.deleted_at is not None:
        raise AppError("ACCOUNT_DELETED", "该账号已申请删除，无法直接恢复", 403)
    elif payload.display_name and user.display_name == "新用户":
        user.display_name = payload.display_name

    db.commit()
    return TokenResult(access_token=create_access_token(user.id), user_id=user.id)


@router.post("/token/refresh", response_model=TokenResult)
def refresh_token(user: User = Depends(get_current_user)) -> TokenResult:
    return TokenResult(access_token=create_access_token(user.id), user_id=user.id)


@router.post("/logout", status_code=204)
def logout() -> None:
    # Stateless access tokens are short-lived. Mobile clients must erase the token.
    return None


@me_router.get("/me", response_model=UserOut)
def get_me(user: User = Depends(get_current_user)) -> User:
    return user


@me_router.patch("/me/profile", response_model=UserOut)
def patch_me(
    payload: UserProfilePatch,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    if payload.display_name is not None:
        user.display_name = payload.display_name
    profile = user.profile
    if profile is None:
        profile = UserProfile(user_id=user.id)
        db.add(profile)
    for field in (
        "preferred_language",
        "region_code",
        "timezone",
        "font_scale",
        "accessibility_settings",
    ):
        value = getattr(payload, field)
        if value is not None:
            setattr(profile, field, value)
    db.commit()
    db.refresh(user)
    return user


@me_router.delete("/me", status_code=204)
def delete_me(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    user.status = "deleted"
    user.deleted_at = utc_now()
    user.phone_hash = hash_code(user.phone_hash + new_id())
    user.phone_encrypted = encrypt_text("[deleted]") or ""
    user.display_name = "已删除用户"
    if user.profile:
        user.profile.accessibility_settings = {}
    db.commit()
    return None
