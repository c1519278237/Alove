import secrets
import string
from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_family_role, require_membership
from ..errors import AppError, forbidden, not_found
from ..models import Family, FamilyInvite, FamilyMember, User
from ..schemas import (
    FamilyCreate,
    FamilyMemberOut,
    FamilyOut,
    InviteAccept,
    InviteCreate,
    InviteOut,
    MemberPatch,
)
from ..security import utc_now

router = APIRouter(tags=["families"])


def _invite_code() -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(8))


@router.get("/families", response_model=list[FamilyOut])
def list_families(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[Family]:
    return list(
        db.scalars(
            select(Family)
            .join(FamilyMember, FamilyMember.family_id == Family.id)
            .where(
                FamilyMember.user_id == user.id,
                FamilyMember.status == "active",
                Family.status == "active",
            )
            .order_by(Family.created_at.desc())
        ).all()
    )


@router.post("/families", response_model=FamilyOut, status_code=201)
def create_family(
    payload: FamilyCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Family:
    family = Family(name=payload.name, created_by=user.id)
    db.add(family)
    db.flush()
    db.add(
        FamilyMember(
            family_id=family.id,
            user_id=user.id,
            role=payload.my_role,
            relationship_label=payload.relationship_label,
        )
    )
    db.commit()
    db.refresh(family)
    return family


@router.get("/families/{family_id}", response_model=FamilyOut)
def get_family(
    family_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Family:
    require_membership(db, family_id, user.id)
    family = db.get(Family, family_id)
    if family is None:
        raise not_found("家庭")
    return family


@router.post("/families/{family_id}/invites", response_model=InviteOut, status_code=201)
def create_invite(
    family_id: str,
    payload: InviteCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FamilyInvite:
    require_family_role(db, family_id, user.id, {"child", "caregiver", "admin"})
    code = _invite_code()
    while db.get(FamilyInvite, code) is not None:
        code = _invite_code()
    invite = FamilyInvite(
        code=code,
        family_id=family_id,
        invited_role=payload.role,
        relationship_label=payload.relationship_label,
        created_by=user.id,
        expires_at=utc_now() + timedelta(hours=payload.expires_hours),
    )
    db.add(invite)
    db.commit()
    return invite


@router.post("/family-invites/{code}/accept", response_model=FamilyMemberOut)
def accept_invite(
    code: str,
    payload: InviteAccept,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FamilyMember:
    if payload.code.upper() != code.upper():
        raise AppError("INVALID_INVITE", "邀请码不一致", 422)
    invite = db.get(FamilyInvite, code.upper())
    if invite is None or invite.accepted_by is not None:
        raise AppError("INVALID_INVITE", "邀请码不存在或已使用", 404)
    expires_at = invite.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=utc_now().tzinfo)
    if expires_at < utc_now():
        raise AppError("INVALID_INVITE", "邀请码已过期", 410)
    existing = db.scalar(
        select(FamilyMember).where(
            FamilyMember.family_id == invite.family_id,
            FamilyMember.user_id == user.id,
        )
    )
    if existing:
        member = existing
        member.status = "active"
    else:
        member = FamilyMember(
            family_id=invite.family_id,
            user_id=user.id,
            role=invite.invited_role,
            relationship_label=invite.relationship_label,
        )
        db.add(member)
    invite.accepted_by = user.id
    db.commit()
    return member


@router.get("/families/{family_id}/members", response_model=list[FamilyMemberOut])
def list_members(
    family_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[FamilyMemberOut]:
    require_membership(db, family_id, user.id)
    rows = db.execute(
        select(FamilyMember, User.display_name)
        .join(User, User.id == FamilyMember.user_id)
        .where(FamilyMember.family_id == family_id, FamilyMember.status == "active")
        .order_by(FamilyMember.joined_at)
    ).all()
    return [
        FamilyMemberOut.model_validate(member).model_copy(update={"display_name": name})
        for member, name in rows
    ]


@router.patch("/families/{family_id}/members/{user_id}", response_model=FamilyMemberOut)
def patch_member(
    family_id: str,
    user_id: str,
    payload: MemberPatch,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FamilyMember:
    require_family_role(db, family_id, user.id, {"admin"})
    member = db.scalar(
        select(FamilyMember).where(
            FamilyMember.family_id == family_id, FamilyMember.user_id == user_id
        )
    )
    if member is None:
        raise not_found("家庭成员")
    for field in ("role", "relationship_label", "status"):
        value = getattr(payload, field)
        if value is not None:
            setattr(member, field, value)
    db.commit()
    return member


@router.delete("/families/{family_id}/members/{user_id}", status_code=204)
def remove_member(
    family_id: str,
    user_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    actor = require_membership(db, family_id, user.id)
    if user.id != user_id and actor.role != "admin":
        raise forbidden()
    member = db.scalar(
        select(FamilyMember).where(
            FamilyMember.family_id == family_id, FamilyMember.user_id == user_id
        )
    )
    if member is None:
        raise not_found("家庭成员")
    member.status = "removed"
    db.commit()
    return None
