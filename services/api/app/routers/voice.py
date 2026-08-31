from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_membership
from ..errors import not_found
from ..models import User, VoiceProfile
from ..schemas import VoiceEnrollment, VoiceProfileOut
from ..security import encrypt_text, utc_now
from .consents import require_active_consent

router = APIRouter(tags=["voice"])


def _voice_out(profile: VoiceProfile) -> VoiceProfileOut:
    return VoiceProfileOut(
        id=profile.id,
        owner_user_id=profile.owner_user_id,
        provider=profile.provider,
        consent_id=profile.consent_id,
        allowed_recipient_ids=profile.allowed_recipient_ids,
        status=profile.status,
        expires_at=profile.expires_at,
        watermark_config=profile.watermark_config,
        created_at=profile.created_at,
    )


@router.get("/voice-profiles", response_model=list[VoiceProfileOut])
def list_voice_profiles(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[VoiceProfileOut]:
    rows = db.scalars(
        select(VoiceProfile)
        .where(VoiceProfile.status != "revoked")
        .order_by(VoiceProfile.created_at.desc())
    ).all()
    return [
        _voice_out(row)
        for row in rows
        if row.owner_user_id == user.id or user.id in row.allowed_recipient_ids
    ]


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
    profile = VoiceProfile(
        owner_user_id=user.id,
        provider=payload.provider,
        provider_voice_ref_encrypted=encrypt_text("pending-provider-enrollment") or "",
        consent_id=consent.id,
        allowed_recipient_ids=payload.allowed_recipient_ids,
        status="pending_consent_verification",
        expires_at=payload.expires_at,
        watermark_config={"required": True, "ai_identity_notice": True},
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
    profile.status = "approved_for_provider_enrollment"
    db.commit()
    return _voice_out(profile)


@router.post("/voice-profiles/{profile_id}/revoke", response_model=VoiceProfileOut)
def revoke_voice_profile(
    profile_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VoiceProfileOut:
    profile = db.get(VoiceProfile, profile_id)
    if profile is None or profile.owner_user_id != user.id:
        raise not_found("声线授权")
    profile.status = "revoked"
    profile.deleted_at = utc_now()
    profile.provider_voice_ref_encrypted = encrypt_text("[revoked]") or ""
    db.commit()
    return _voice_out(profile)
