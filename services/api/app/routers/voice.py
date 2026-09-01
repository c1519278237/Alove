from contextlib import suppress
from datetime import UTC

import httpx
from cryptography.fernet import InvalidToken
from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..deps import get_current_user, require_membership
from ..errors import AppError, not_found
from ..models import MediaObject, User, VoiceProfile
from ..schemas import VoiceEnrollment, VoiceProfileOut, VoiceSynthesis
from ..security import decrypt_bytes, decrypt_text, encrypt_text, utc_now
from ..voice_provider import DashScopeQwenVoiceProvider, WebhookVoiceProvider
from .consents import require_active_consent
from .media import media_path

router = APIRouter(tags=["voice"])


def _voice_out(profile: VoiceProfile) -> VoiceProfileOut:
    return VoiceProfileOut(
        id=profile.id,
        owner_user_id=profile.owner_user_id,
        provider=profile.provider,
        consent_id=profile.consent_id,
        sample_media_id=profile.sample_media_id,
        allowed_recipient_ids=profile.allowed_recipient_ids,
        status=profile.status,
        expires_at=profile.expires_at,
        watermark_config=profile.watermark_config,
        created_at=profile.created_at,
    )


def _valid_profile_for_user(profile: VoiceProfile, user_id: str) -> bool:
    if profile.status == "revoked" or profile.deleted_at is not None:
        return False
    if profile.expires_at is not None:
        expires_at = profile.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= utc_now():
            return False
    return profile.owner_user_id == user_id or user_id in profile.allowed_recipient_ids


@router.get("/voice-profiles", response_model=list[VoiceProfileOut])
def list_voice_profiles(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[VoiceProfileOut]:
    rows = db.scalars(
        select(VoiceProfile).order_by(VoiceProfile.created_at.desc())
    ).all()
    return [_voice_out(row) for row in rows if _valid_profile_for_user(row, user.id)]


@router.post("/voice-profiles/enrollment", response_model=VoiceProfileOut, status_code=201)
def create_voice_enrollment(
    payload: VoiceEnrollment,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VoiceProfileOut:
    consent = require_active_consent(
        db,
        consent_id=payload.consent_id,
        subject_user_id=user.id,
        consent_type="voice_use",
    )
    for recipient_id in payload.allowed_recipient_ids:
        require_membership(db, consent.family_id, recipient_id)
    media = None
    if payload.sample_media_id:
        media = db.get(MediaObject, payload.sample_media_id)
        if (
            media is None
            or media.owner_user_id != user.id
            or media.status != "active"
            or not media.mime_type.startswith("audio/")
        ):
            raise not_found("声线样本")
    provider = payload.provider or get_settings().voice_provider
    if provider != "device_tts" and media is None:
        raise AppError("VOICE_SAMPLE_REQUIRED", "真实声线复刻需要先上传本人声音样本", 422)
    profile = VoiceProfile(
        owner_user_id=user.id,
        provider=provider,
        provider_voice_ref_encrypted=encrypt_text("pending-provider-enrollment") or "",
        sample_media_id=media.id if media else None,
        consent_id=consent.id,
        allowed_recipient_ids=payload.allowed_recipient_ids,
        status="pending_consent_verification",
        expires_at=payload.expires_at,
        watermark_config={
            "required": True,
            "ai_identity_notice": True,
            "sample_retention": "delete_after_enrollment",
        },
    )
    db.add(profile)
    db.commit()
    return _voice_out(profile)


@router.post("/voice-profiles/{profile_id}/verify-consent", response_model=VoiceProfileOut)
def verify_voice_consent(
    profile_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VoiceProfileOut:
    profile = db.get(VoiceProfile, profile_id)
    if profile is None or profile.owner_user_id != user.id:
        raise not_found("声线授权")
    require_active_consent(
        db,
        consent_id=profile.consent_id,
        subject_user_id=user.id,
        consent_type="voice_use",
    )
    if profile.provider == "device_tts":
        profile.status = "ready_device_fallback"
    elif profile.provider in {"webhook", "dashscope_qwen"}:
        media = db.get(MediaObject, profile.sample_media_id) if profile.sample_media_id else None
        if media is None:
            raise not_found("声线样本")
        try:
            sample = decrypt_bytes(media_path(media.storage_key).read_bytes())
            provider = (
                WebhookVoiceProvider(get_settings())
                if profile.provider == "webhook"
                else DashScopeQwenVoiceProvider(get_settings())
            )
            result = provider.enroll(
                profile_id=profile.id,
                mime_type=media.mime_type,
                sample=sample,
            )
        except (FileNotFoundError, InvalidToken, httpx.HTTPError, ValueError) as exc:
            raise AppError("VOICE_PROVIDER_ERROR", "声线供应商暂时无法完成复刻", 502) from exc
        profile.provider_voice_ref_encrypted = encrypt_text(result.voice_id) or ""
        profile.status = result.status
        # A source voice sample is biometric data. Once the provider voice id
        # exists, retain only a tombstoned media record instead of the audio.
        media.status = "deleted"
        media.size_bytes = 0
        media.original_name = "[deleted-after-enrollment]"
        media_path(media.storage_key).unlink(missing_ok=True)
    else:
        raise AppError("VOICE_PROVIDER_UNSUPPORTED", "未配置可用的声线供应商", 422)
    db.commit()
    return _voice_out(profile)


@router.post("/voice-profiles/{profile_id}/synthesize")
def synthesize_voice(
    profile_id: str,
    payload: VoiceSynthesis,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    profile = db.get(VoiceProfile, profile_id)
    if profile is None or not _valid_profile_for_user(profile, user.id):
        raise not_found("声线")
    if user.id not in profile.allowed_recipient_ids:
        raise AppError("VOICE_RECIPIENT_NOT_ALLOWED", "该声线没有授权给当前接收人", 403)
    if profile.provider == "device_tts" or profile.status == "ready_device_fallback":
        raise AppError(
            "VOICE_DEVICE_FALLBACK",
            "当前声线使用手机设备朗读，不需要服务端合成",
            409,
        )
    if profile.provider not in {"webhook", "dashscope_qwen"} or profile.status not in {
        "active",
        "ready",
    }:
        raise AppError("VOICE_NOT_READY", "声线仍在准备中", 409)
    voice_id = decrypt_text(profile.provider_voice_ref_encrypted) or ""
    try:
        provider = (
            WebhookVoiceProvider(get_settings())
            if profile.provider == "webhook"
            else DashScopeQwenVoiceProvider(get_settings())
        )
        audio = provider.synthesize(
            voice_id=voice_id,
            text=(
                "这里是归音AI助手为您生成的语音。"
                + payload.text
            )[: get_settings().voice_max_text_chars],
        )
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise AppError("VOICE_PROVIDER_ERROR", "声线合成服务暂时不可用", 502) from exc
    return Response(
        audio.payload,
        media_type=audio.mime_type,
        headers={
            "Cache-Control": "private, no-store",
            "X-AI-Generated-Voice": "true",
            "X-Voice-Watermark": "required",
        },
    )


@router.post("/voice-profiles/{profile_id}/revoke", response_model=VoiceProfileOut)
def revoke_voice_profile(
    profile_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VoiceProfileOut:
    profile = db.get(VoiceProfile, profile_id)
    if profile is None or profile.owner_user_id != user.id:
        raise not_found("声线授权")
    voice_id = decrypt_text(profile.provider_voice_ref_encrypted) or ""
    if profile.provider in {"webhook", "dashscope_qwen"} and voice_id not in {
        "",
        "pending-provider-enrollment",
    }:
        with suppress(httpx.HTTPError, ValueError):
            provider = (
                WebhookVoiceProvider(get_settings())
                if profile.provider == "webhook"
                else DashScopeQwenVoiceProvider(get_settings())
            )
            provider.revoke(voice_id)
    if profile.sample_media_id:
        media = db.get(MediaObject, profile.sample_media_id)
        if media and media.owner_user_id == user.id:
            media.status = "deleted"
            media.size_bytes = 0
            media.original_name = "[deleted]"
            media_path(media.storage_key).unlink(missing_ok=True)
    profile.status = "revoked"
    profile.deleted_at = utc_now()
    profile.provider_voice_ref_encrypted = encrypt_text("[revoked]") or ""
    db.commit()
    return _voice_out(profile)
