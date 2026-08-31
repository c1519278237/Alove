from fastapi import APIRouter, Depends
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_membership
from ..errors import consent_required, forbidden, not_found
from ..models import StyleProfile, User
from ..schemas import StyleProfileOut, StyleProfileUpsert
from .consents import is_consent_active

router = APIRouter(tags=["style-profiles"])


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
            or_(
                StyleProfile.owner_user_id == user.id,
                StyleProfile.target_user_id == user.id,
            )
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
    from ..models import Consent

    grants = db.scalars(
        select(Consent).where(
            Consent.family_id == family_id,
            Consent.subject_user_id == payload.target_user_id,
            Consent.grantee_user_id == user.id,
            Consent.consent_type == "style_personalization",
        )
    ).all()
    if not any(is_consent_active(grant) for grant in grants):
        raise consent_required("需要老人授权后，家人才能为其设置表达习惯")
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
    return None
