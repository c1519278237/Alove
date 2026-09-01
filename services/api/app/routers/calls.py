from fastapi import APIRouter, Depends, Request
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..audit import append_audit_log
from ..database import get_db
from ..deps import get_current_user, require_membership
from ..errors import forbidden, not_found
from ..models import CallEvent, FamilyMember, User
from ..schemas import CallEventCreate, CallEventOut, CallEventPatch, FamilyContactOut
from ..security import decrypt_text, utc_now

router = APIRouter(tags=["calls"])


def _call_out(event: CallEvent, names: dict[str, str]) -> CallEventOut:
    return CallEventOut(
        id=event.id,
        family_id=event.family_id,
        caller_user_id=event.caller_user_id,
        caller_name=names.get(event.caller_user_id, "家庭成员"),
        callee_user_id=event.callee_user_id,
        callee_name=names.get(event.callee_user_id, "家庭成员"),
        status=event.status,
        source=event.source,
        duration_seconds=event.duration_seconds,
        created_at=event.created_at,
        ended_at=event.ended_at,
    )


@router.get("/families/{family_id}/contacts", response_model=list[FamilyContactOut])
def list_family_contacts(
    family_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[FamilyContactOut]:
    require_membership(db, family_id, user.id)
    rows = db.execute(
        select(FamilyMember, User)
        .join(User, User.id == FamilyMember.user_id)
        .where(
            FamilyMember.family_id == family_id,
            FamilyMember.status == "active",
            User.status == "active",
            User.id != user.id,
        )
        .order_by(FamilyMember.joined_at)
    ).all()
    append_audit_log(
        db,
        actor_id=user.id,
        action="family_contacts.list",
        resource_type="family",
        resource_id=family_id,
        reason="quick call family member",
        request=request,
    )
    db.commit()
    return [
        FamilyContactOut(
            user_id=member.user_id,
            display_name=contact.display_name,
            relationship_label=member.relationship_label,
            role=member.role,
            phone=decrypt_text(contact.phone_encrypted) or "",
        )
        for member, contact in rows
    ]


@router.post("/families/{family_id}/call-events", response_model=CallEventOut, status_code=201)
def create_call_event(
    family_id: str,
    payload: CallEventCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CallEventOut:
    require_membership(db, family_id, user.id)
    require_membership(db, family_id, payload.callee_user_id)
    if payload.callee_user_id == user.id:
        raise forbidden("不能呼叫自己")
    event = CallEvent(
        family_id=family_id,
        caller_user_id=user.id,
        callee_user_id=payload.callee_user_id,
    )
    db.add(event)
    db.commit()
    names = {
        row.id: row.display_name
        for row in db.scalars(
            select(User).where(User.id.in_([event.caller_user_id, event.callee_user_id]))
        ).all()
    }
    return _call_out(event, names)


@router.get("/families/{family_id}/call-events", response_model=list[CallEventOut])
def list_call_events(
    family_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[CallEventOut]:
    member = require_membership(db, family_id, user.id)
    query = select(CallEvent).where(CallEvent.family_id == family_id)
    if member.role != "admin":
        query = query.where(
            or_(CallEvent.caller_user_id == user.id, CallEvent.callee_user_id == user.id)
        )
    events = list(db.scalars(query.order_by(CallEvent.created_at.desc()).limit(100)).all())
    user_ids = {value for event in events for value in (event.caller_user_id, event.callee_user_id)}
    names = {
        row.id: row.display_name
        for row in db.scalars(select(User).where(User.id.in_(user_ids))).all()
    }
    return [_call_out(event, names) for event in events]


@router.patch("/call-events/{event_id}", response_model=CallEventOut)
def patch_call_event(
    event_id: str,
    payload: CallEventPatch,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CallEventOut:
    event = db.get(CallEvent, event_id)
    if event is None or event.caller_user_id != user.id:
        raise not_found("呼叫记录")
    event.status = payload.status
    event.duration_seconds = payload.duration_seconds
    if payload.status in {"completed", "cancelled", "failed"}:
        event.ended_at = utc_now()
    db.commit()
    names = {
        row.id: row.display_name
        for row in db.scalars(
            select(User).where(User.id.in_([event.caller_user_id, event.callee_user_id]))
        ).all()
    }
    return _call_out(event, names)
