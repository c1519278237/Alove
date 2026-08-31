from fastapi import APIRouter, Depends
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..errors import consent_required, forbidden, not_found
from ..models import Reminder, ReminderEvent, User
from ..schemas import (
    ReminderAction,
    ReminderCreate,
    ReminderEventOut,
    ReminderOut,
    ReminderPatch,
)
from ..security import decrypt_text, encrypt_text
from .care import _common_family_ids

router = APIRouter(tags=["reminders"])


def _reminder_out(reminder: Reminder) -> ReminderOut:
    return ReminderOut(
        id=reminder.id,
        owner_user_id=reminder.owner_user_id,
        creator_user_id=reminder.creator_user_id,
        content=decrypt_text(reminder.content_encrypted) or "",
        schedule_rule=reminder.schedule_rule,
        category=reminder.category,
        status=reminder.status,
        created_at=reminder.created_at,
    )


def _event_out(event: ReminderEvent) -> ReminderEventOut:
    return ReminderEventOut(
        id=event.id,
        reminder_id=event.reminder_id,
        actor_user_id=event.actor_user_id,
        action=event.action,
        note=decrypt_text(event.note_encrypted),
        created_at=event.created_at,
    )


@router.post("/reminders", response_model=ReminderOut, status_code=201)
def create_reminder(
    payload: ReminderCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReminderOut:
    if payload.owner_user_id != user.id:
        common_families = _common_family_ids(db, user.id, payload.owner_user_id)
        if not common_families:
            raise not_found("家庭成员")
        from ..models import Consent
        from .consents import is_consent_active

        grants = db.scalars(
            select(Consent).where(
                Consent.subject_user_id == payload.owner_user_id,
                Consent.grantee_user_id == user.id,
                Consent.consent_type == "reminder_management",
                Consent.family_id.in_(common_families),
            )
        ).all()
        if not any(is_consent_active(grant) for grant in grants):
            raise consent_required("需要老人授权后，家属才能为其创建提醒")
    reminder = Reminder(
        owner_user_id=payload.owner_user_id,
        creator_user_id=user.id,
        content_encrypted=encrypt_text(payload.content) or "",
        schedule_rule=payload.schedule_rule,
        category=payload.category,
    )
    db.add(reminder)
    db.commit()
    return _reminder_out(reminder)


@router.get("/reminders", response_model=list[ReminderOut])
def list_reminders(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[ReminderOut]:
    rows = db.scalars(
        select(Reminder)
        .where(or_(Reminder.owner_user_id == user.id, Reminder.creator_user_id == user.id))
        .order_by(Reminder.created_at.desc())
    ).all()
    return [_reminder_out(row) for row in rows]


def _editable_reminder(db: Session, reminder_id: str, user_id: str) -> Reminder:
    reminder = db.get(Reminder, reminder_id)
    if reminder is None:
        raise not_found("提醒")
    if user_id not in {reminder.owner_user_id, reminder.creator_user_id}:
        raise forbidden()
    return reminder


@router.patch("/reminders/{reminder_id}", response_model=ReminderOut)
def patch_reminder(
    reminder_id: str,
    payload: ReminderPatch,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReminderOut:
    reminder = _editable_reminder(db, reminder_id, user.id)
    if payload.content is not None:
        reminder.content_encrypted = encrypt_text(payload.content) or ""
    for field in ("schedule_rule", "category", "status"):
        value = getattr(payload, field)
        if value is not None:
            setattr(reminder, field, value)
    db.commit()
    return _reminder_out(reminder)


@router.post("/reminders/{reminder_id}/actions", response_model=ReminderEventOut)
def record_reminder_action(
    reminder_id: str,
    payload: ReminderAction,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReminderEventOut:
    reminder = _editable_reminder(db, reminder_id, user.id)
    if user.id != reminder.owner_user_id:
        raise forbidden("提醒播放和确认状态只能由接收提醒的人更新")
    event = ReminderEvent(
        reminder_id=reminder.id,
        actor_user_id=user.id,
        action=payload.action,
        note_encrypted=encrypt_text(payload.note),
    )
    if payload.action == "confirmed":
        reminder.status = "done" if reminder.schedule_rule.startswith("once:") else "active"
    elif payload.action == "expired":
        reminder.status = "expired"
    db.add(event)
    db.commit()
    return _event_out(event)


@router.get("/reminders/{reminder_id}/events", response_model=list[ReminderEventOut])
def list_reminder_events(
    reminder_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ReminderEventOut]:
    _editable_reminder(db, reminder_id, user.id)
    rows = db.scalars(
        select(ReminderEvent)
        .where(ReminderEvent.reminder_id == reminder_id)
        .order_by(ReminderEvent.created_at.desc())
    ).all()
    return [_event_out(row) for row in rows]


@router.delete("/reminders/{reminder_id}", status_code=204)
def delete_reminder(
    reminder_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    reminder = _editable_reminder(db, reminder_id, user.id)
    reminder.status = "deleted"
    reminder.content_encrypted = encrypt_text("[deleted]") or ""
    db.commit()
    return None
