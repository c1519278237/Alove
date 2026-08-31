import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..deps import get_current_user
from ..errors import AppError
from ..models import (
    CareNeed,
    Consent,
    Conversation,
    FamilyMember,
    FamilyMessage,
    KnowledgeChunk,
    KnowledgeDocument,
    MediaObject,
    Memory,
    Message,
    Reminder,
    SmsCode,
    User,
    UserProfile,
    VoiceProfile,
)
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
    decrypt_text,
    encrypt_text,
    hash_code,
    new_id,
    normalize_phone,
    phone_hash,
    utc_now,
    verify_code,
)
from ..sms import deliver_sms_code

router = APIRouter(prefix="/auth", tags=["auth"])
me_router = APIRouter(tags=["me"])


@router.post("/sms/request", response_model=SmsRequestResult)
def request_sms(payload: SmsRequest, db: Session = Depends(get_db)) -> SmsRequestResult:
    settings = get_settings()
    try:
        phone = normalize_phone(payload.phone)
    except ValueError as exc:
        raise AppError("INVALID_PHONE", str(exc), 422) from exc
    hashed_phone = phone_hash(phone)
    if not settings.is_local:
        recent = db.scalar(
            select(func.count(SmsCode.id)).where(
                SmsCode.phone_hash == hashed_phone,
                SmsCode.created_at
                >= utc_now() - timedelta(seconds=settings.sms_min_interval_seconds),
            )
        )
        hourly = db.scalar(
            select(func.count(SmsCode.id)).where(
                SmsCode.phone_hash == hashed_phone,
                SmsCode.created_at >= utc_now() - timedelta(hours=1),
            )
        )
        if int(recent or 0) > 0 or int(hourly or 0) >= settings.sms_hourly_limit:
            raise AppError("SMS_RATE_LIMITED", "验证码请求过于频繁，请稍后再试", 429)
    code = f"{secrets.randbelow(1_000_000):06d}"
    deliver_sms_code(settings, phone=phone, code=code)
    record = SmsCode(
        phone_hash=hashed_phone,
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


@me_router.get("/me/export")
def export_me(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    conversations = db.scalars(
        select(Conversation).where(Conversation.owner_user_id == user.id)
    ).all()
    conversation_ids = [item.id for item in conversations]
    messages = (
        db.scalars(
            select(Message)
            .where(Message.conversation_id.in_(conversation_ids))
            .order_by(Message.created_at)
        ).all()
        if conversation_ids
        else []
    )
    memories = db.scalars(select(Memory).where(Memory.owner_user_id == user.id)).all()
    needs = db.scalars(select(CareNeed).where(CareNeed.elder_user_id == user.id)).all()
    reminders = db.scalars(select(Reminder).where(Reminder.owner_user_id == user.id)).all()
    family_messages = db.scalars(
        select(FamilyMessage).where(
            (FamilyMessage.sender_user_id == user.id)
            | (FamilyMessage.recipient_user_id == user.id)
        )
    ).all()
    consents = db.scalars(
        select(Consent).where(
            (Consent.subject_user_id == user.id) | (Consent.grantee_user_id == user.id)
        )
    ).all()
    memberships = db.scalars(
        select(FamilyMember).where(FamilyMember.user_id == user.id)
    ).all()
    return {
        "exported_at": utc_now().isoformat(),
        "user": {
            "id": user.id,
            "display_name": user.display_name,
            "status": user.status,
            "created_at": user.created_at.isoformat(),
        },
        "memberships": [
            {
                "family_id": item.family_id,
                "role": item.role,
                "relationship_label": item.relationship_label,
                "status": item.status,
            }
            for item in memberships
        ],
        "consents": [
            {
                "id": item.id,
                "family_id": item.family_id,
                "consent_type": item.consent_type,
                "grantee_user_id": item.grantee_user_id,
                "scope": item.scope,
                "granted_at": item.granted_at.isoformat(),
                "revoked_at": item.revoked_at.isoformat() if item.revoked_at else None,
            }
            for item in consents
        ],
        "conversations": [
            {
                "id": item.id,
                "family_id": item.family_id,
                "sharing_level": item.sharing_level,
                "status": item.status,
                "started_at": item.started_at.isoformat(),
            }
            for item in conversations
        ],
        "messages": [
            {
                "conversation_id": item.conversation_id,
                "role": item.role,
                "text": decrypt_text(item.text_encrypted),
                "safety_labels": item.safety_labels,
                "created_at": item.created_at.isoformat(),
            }
            for item in messages
        ],
        "memories": [
            {
                "id": item.id,
                "type": item.memory_type,
                "content": decrypt_text(item.content_encrypted),
                "confirmation_status": item.confirmation_status,
                "sharing_level": item.sharing_level,
            }
            for item in memories
        ],
        "care_needs": [
            {
                "id": item.id,
                "title": decrypt_text(item.title_encrypted),
                "description": decrypt_text(item.description_encrypted),
                "status": item.status,
                "priority": item.priority,
            }
            for item in needs
        ],
        "reminders": [
            {
                "id": item.id,
                "content": decrypt_text(item.content_encrypted),
                "schedule_rule": item.schedule_rule,
                "status": item.status,
            }
            for item in reminders
        ],
        "family_messages": [
            {
                "id": item.id,
                "sender_user_id": item.sender_user_id,
                "recipient_user_id": item.recipient_user_id,
                "type": item.type,
                "content": decrypt_text(item.content_encrypted),
                "played_at": item.played_at.isoformat() if item.played_at else None,
            }
            for item in family_messages
        ],
    }


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
    conversations = db.scalars(
        select(Conversation).where(Conversation.owner_user_id == user.id)
    ).all()
    conversation_ids = [item.id for item in conversations]
    if conversation_ids:
        messages = db.scalars(
            select(Message).where(Message.conversation_id.in_(conversation_ids))
        ).all()
        for message in messages:
            message.text_encrypted = encrypt_text("[deleted]") or ""
            message.text_redacted = "[deleted]"
            message.audio_object_key = None
            message.safety_labels = []
        for conversation in conversations:
            conversation.status = "deleted"
            conversation.ended_at = utc_now()
    documents = db.scalars(
        select(KnowledgeDocument).where(KnowledgeDocument.owner_user_id == user.id)
    ).all()
    document_ids = [item.id for item in documents]
    for document in documents:
        document.status = "deleted"
        document.content_encrypted = encrypt_text("[deleted]") or ""
    if document_ids:
        chunks = db.scalars(
            select(KnowledgeChunk).where(KnowledgeChunk.document_id.in_(document_ids))
        ).all()
        for chunk in chunks:
            chunk.status = "deleted"
            chunk.content_encrypted = encrypt_text("[deleted]") or ""
    for memory in db.scalars(select(Memory).where(Memory.owner_user_id == user.id)).all():
        memory.deleted_at = utc_now()
        memory.content_encrypted = encrypt_text("[deleted]") or ""
    for need in db.scalars(select(CareNeed).where(CareNeed.elder_user_id == user.id)).all():
        need.status = "deleted"
        need.title_encrypted = encrypt_text("[deleted]") or ""
        need.description_encrypted = encrypt_text("[deleted]") or ""
    family_messages = db.scalars(
        select(FamilyMessage).where(
            (FamilyMessage.sender_user_id == user.id)
            | (FamilyMessage.recipient_user_id == user.id)
        )
    ).all()
    for message in family_messages:
        message.content_encrypted = encrypt_text("[deleted]") or ""
        message.audio_object_key = None
    for profile in db.scalars(
        select(VoiceProfile).where(VoiceProfile.owner_user_id == user.id)
    ).all():
        profile.status = "revoked"
        profile.deleted_at = utc_now()
        profile.provider_voice_ref_encrypted = encrypt_text("[deleted]") or ""
    owned_media = db.scalars(
        select(MediaObject).where(MediaObject.owner_user_id == user.id)
    ).all()
    if owned_media:
        from .media import media_path

        for media in owned_media:
            media.status = "deleted"
            media.original_name = "[deleted]"
            media.size_bytes = 0
            media_path(media.storage_key).unlink(missing_ok=True)
    user.status = "deleted"
    user.deleted_at = utc_now()
    user.phone_hash = hash_code(user.phone_hash + new_id())
    user.phone_encrypted = encrypt_text("[deleted]") or ""
    user.display_name = "已删除用户"
    if user.profile:
        user.profile.accessibility_settings = {}
    db.commit()
    return None
