from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..deps import get_current_user, require_membership
from ..document_ingest import read_uploaded_document
from ..errors import AppError, consent_required, forbidden, not_found
from ..models import Consent, StyleProfile, StyleSample, User
from ..schemas import StyleProfileOut, StyleProfileUpsert, StyleSampleOut
from ..security import decrypt_text, encrypt_text, utc_now
from ..style_learning import analyze_style_samples
from .consents import is_consent_active

router = APIRouter(tags=["style-profiles"])


def _require_style_consent(
    db: Session, *, family_id: str, target_user_id: str, owner_user_id: str
) -> None:
    grants = db.scalars(
        select(Consent).where(
            Consent.family_id == family_id,
            Consent.subject_user_id == target_user_id,
            Consent.grantee_user_id == owner_user_id,
            Consent.consent_type == "style_personalization",
        )
    ).all()
    if not any(is_consent_active(grant) for grant in grants):
        raise consent_required("需要老人授权后，家人才可以上传对话样本并学习表达习惯")


def _sample_out(sample: StyleSample) -> StyleSampleOut:
    return StyleSampleOut(
        id=sample.id,
        family_id=sample.family_id,
        owner_user_id=sample.owner_user_id,
        target_user_id=sample.target_user_id,
        title=sample.title,
        source_type=sample.source_type,
        metrics=sample.metrics,
        status=sample.status,
        created_at=sample.created_at,
    )


def _refresh_learned_profile(
    db: Session, *, family_id: str, owner_user_id: str, target_user_id: str
) -> StyleProfile:
    samples = db.scalars(
        select(StyleSample).where(
            StyleSample.family_id == family_id,
            StyleSample.owner_user_id == owner_user_id,
            StyleSample.target_user_id == target_user_id,
            StyleSample.status == "active",
            StyleSample.deleted_at.is_(None),
        )
    ).all()
    learned = analyze_style_samples(
        [decrypt_text(sample.content_encrypted) or "" for sample in samples]
    )
    profile = db.scalar(
        select(StyleProfile).where(
            StyleProfile.family_id == family_id,
            StyleProfile.owner_user_id == owner_user_id,
            StyleProfile.target_user_id == target_user_id,
        )
    )
    if profile is None:
        profile = StyleProfile(
            family_id=family_id,
            owner_user_id=owner_user_id,
            target_user_id=target_user_id,
        )
        db.add(profile)
    profile.common_greetings = list(learned["common_greetings"])
    profile.sentence_style = str(learned["sentence_style"])
    profile.comfort_style = str(learned["comfort_style"])
    profile.reminder_style = str(learned["reminder_style"])
    profile.status = "active"
    return profile


@router.get("/families/{family_id}/style-profiles", response_model=list[StyleProfileOut])
def list_style_profiles(
    family_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[StyleProfile]:
    member = require_membership(db, family_id, user.id)
    query = select(StyleProfile).where(
        StyleProfile.family_id == family_id,
        StyleProfile.status == "active",
    )
    if member.role != "admin":
        query = query.where(
            or_(StyleProfile.owner_user_id == user.id, StyleProfile.target_user_id == user.id)
        )
    return list(db.scalars(query.order_by(StyleProfile.updated_at.desc())).all())


@router.put("/families/{family_id}/style-profile", response_model=StyleProfileOut)
def upsert_style_profile(
    family_id: str,
    payload: StyleProfileUpsert,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StyleProfile:
    require_membership(db, family_id, user.id)
    require_membership(db, family_id, payload.target_user_id)
    if payload.target_user_id == user.id:
        raise forbidden("表达风格应由家人本人设置，并指定希望服务的老人")
    _require_style_consent(
        db,
        family_id=family_id,
        target_user_id=payload.target_user_id,
        owner_user_id=user.id,
    )
    profile = db.scalar(
        select(StyleProfile).where(
            StyleProfile.family_id == family_id,
            StyleProfile.owner_user_id == user.id,
            StyleProfile.target_user_id == payload.target_user_id,
        )
    )
    values = payload.model_dump(exclude={"target_user_id"})
    if profile is None:
        profile = StyleProfile(
            family_id=family_id,
            owner_user_id=user.id,
            target_user_id=payload.target_user_id,
            **values,
        )
        db.add(profile)
    else:
        for field, value in values.items():
            setattr(profile, field, value)
        profile.status = "active"
    db.commit()
    db.refresh(profile)
    return profile


@router.post(
    "/families/{family_id}/style-samples/upload",
    response_model=StyleSampleOut,
    status_code=201,
)
async def upload_style_sample(
    family_id: str,
    target_user_id: str = Form(...),
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StyleSampleOut:
    member = require_membership(db, family_id, user.id)
    target = require_membership(db, family_id, target_user_id)
    if member.role not in {"child", "caregiver", "admin"} or target.role != "elder":
        raise forbidden("只能由家属为已加入家庭的老人上传本人表达样本")
    _require_style_consent(
        db,
        family_id=family_id,
        target_user_id=target_user_id,
        owner_user_id=user.id,
    )
    content = await read_uploaded_document(file, max_bytes=get_settings().knowledge_max_bytes)
    if len(content) < 20:
        raise AppError("STYLE_SAMPLE_TOO_SHORT", "表达样本至少需要 20 个文字", 422)
    sample = StyleSample(
        family_id=family_id,
        owner_user_id=user.id,
        target_user_id=target_user_id,
        title=(title or file.filename or "表达样本")[:160],
        content_encrypted=encrypt_text(content[:200_000]) or "",
        source_type="upload",
        metrics=analyze_style_samples([content]),
    )
    db.add(sample)
    db.flush()
    _refresh_learned_profile(
        db,
        family_id=family_id,
        owner_user_id=user.id,
        target_user_id=target_user_id,
    )
    db.commit()
    return _sample_out(sample)


@router.get("/families/{family_id}/style-samples", response_model=list[StyleSampleOut])
def list_style_samples(
    family_id: str,
    target_user_id: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[StyleSampleOut]:
    member = require_membership(db, family_id, user.id)
    query = select(StyleSample).where(
        StyleSample.family_id == family_id,
        StyleSample.status == "active",
        StyleSample.deleted_at.is_(None),
    )
    if target_user_id:
        query = query.where(StyleSample.target_user_id == target_user_id)
    if member.role != "admin":
        query = query.where(
            or_(StyleSample.owner_user_id == user.id, StyleSample.target_user_id == user.id)
        )
    return [
        _sample_out(row)
        for row in db.scalars(query.order_by(StyleSample.created_at.desc())).all()
    ]


@router.delete("/style-samples/{sample_id}", status_code=204)
def delete_style_sample(
    sample_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    sample = db.get(StyleSample, sample_id)
    if sample is None or sample.owner_user_id != user.id:
        raise not_found("表达样本")
    sample.status = "deleted"
    sample.deleted_at = utc_now()
    sample.content_encrypted = encrypt_text("[deleted]") or ""
    _refresh_learned_profile(
        db,
        family_id=sample.family_id,
        owner_user_id=sample.owner_user_id,
        target_user_id=sample.target_user_id,
    )
    db.commit()


@router.delete("/style-profiles/{profile_id}", status_code=204)
def delete_style_profile(
    profile_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    profile = db.get(StyleProfile, profile_id)
    if profile is None or profile.owner_user_id != user.id:
        raise not_found("表达风格档案")
    profile.status = "deleted"
    profile.common_greetings = []
    profile.banned_phrases = []
    db.commit()
