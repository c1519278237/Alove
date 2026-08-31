from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..database import get_db
from ..deps import get_current_user, require_family_role
from ..errors import not_found
from ..models import (
    AiUsageRecord,
    CareNeed,
    Conversation,
    DataAccessAuditLog,
    FamilyMember,
    Message,
    RiskEvent,
    User,
)
from ..schemas import (
    AdminOverviewOut,
    AiUsageOut,
    AuditLogOut,
    RiskEventOut,
    RiskResolve,
)
from ..security import decrypt_text, encrypt_text, utc_now

router = APIRouter(prefix="/admin", tags=["admin"])


def _risk_out(event: RiskEvent) -> RiskEventOut:
    return RiskEventOut(
        id=event.id,
        family_id=event.family_id,
        subject_user_id=event.subject_user_id,
        conversation_id=event.conversation_id,
        level=event.level,
        labels=event.labels,
        summary=decrypt_text(event.summary_encrypted) or "",
        status=event.status,
        handled_by=event.handled_by,
        resolution=decrypt_text(event.resolution_encrypted),
        created_at=event.created_at,
        handled_at=event.handled_at,
    )


@router.get("/families/{family_id}/overview", response_model=AdminOverviewOut)
def overview(
    family_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AdminOverviewOut:
    require_family_role(db, family_id, user.id, {"admin"})
    since = utc_now() - timedelta(days=7)
    active_members = db.scalar(
        select(func.count()).select_from(FamilyMember).where(
            FamilyMember.family_id == family_id, FamilyMember.status == "active"
        )
    ) or 0
    elders = db.scalar(
        select(func.count()).select_from(FamilyMember).where(
            FamilyMember.family_id == family_id,
            FamilyMember.status == "active",
            FamilyMember.role == "elder",
        )
    ) or 0
    conversations_7d = db.scalar(
        select(func.count()).select_from(Conversation).where(
            Conversation.family_id == family_id, Conversation.started_at >= since
        )
    ) or 0
    messages_7d = db.scalar(
        select(func.count())
        .select_from(Message)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(Conversation.family_id == family_id, Message.created_at >= since)
    ) or 0
    open_risks = db.scalar(
        select(func.count()).select_from(RiskEvent).where(
            RiskEvent.family_id == family_id, RiskEvent.status == "open"
        )
    ) or 0
    pending_needs = db.scalar(
        select(func.count())
        .select_from(CareNeed)
        .join(FamilyMember, FamilyMember.user_id == CareNeed.elder_user_id)
        .where(
            FamilyMember.family_id == family_id,
            CareNeed.status.in_(["pending", "accepted"]),
        )
    ) or 0
    usage = db.execute(
        select(
            func.coalesce(func.sum(AiUsageRecord.total_tokens), 0),
            func.coalesce(func.sum(AiUsageRecord.estimated_cost_usd), 0.0),
        ).where(AiUsageRecord.family_id == family_id, AiUsageRecord.created_at >= since)
    ).one()
    settings = get_settings()
    return AdminOverviewOut(
        family_id=family_id,
        active_members=int(active_members),
        elders=int(elders),
        conversations_7d=int(conversations_7d),
        messages_7d=int(messages_7d),
        open_risk_events=int(open_risks),
        pending_care_needs=int(pending_needs),
        ai_tokens_7d=int(usage[0]),
        estimated_cost_usd_7d=float(usage[1]),
        ai_provider=settings.ai_provider if settings.ai_api_key else "demo",
        ai_model=settings.ai_model if settings.ai_api_key else "safe-rules-v1",
    )


@router.get("/families/{family_id}/risk-events", response_model=list[RiskEventOut])
def list_risk_events(
    family_id: str,
    status: str | None = Query(default=None, max_length=30),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[RiskEventOut]:
    require_family_role(db, family_id, user.id, {"admin"})
    query = select(RiskEvent).where(RiskEvent.family_id == family_id)
    if status:
        query = query.where(RiskEvent.status == status)
    rows = db.scalars(query.order_by(RiskEvent.created_at.desc()).limit(200)).all()
    return [_risk_out(row) for row in rows]


@router.post("/risk-events/{event_id}/resolve", response_model=RiskEventOut)
def resolve_risk_event(
    event_id: str,
    payload: RiskResolve,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RiskEventOut:
    event = db.get(RiskEvent, event_id)
    if event is None:
        raise not_found("风险事件")
    require_family_role(db, event.family_id, user.id, {"admin"})
    event.status = payload.status
    event.handled_by = user.id
    event.resolution_encrypted = encrypt_text(payload.resolution)
    event.handled_at = utc_now()
    db.commit()
    return _risk_out(event)


@router.get("/families/{family_id}/ai-usage", response_model=list[AiUsageOut])
def list_ai_usage(
    family_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AiUsageRecord]:
    require_family_role(db, family_id, user.id, {"admin"})
    return list(
        db.scalars(
            select(AiUsageRecord)
            .where(AiUsageRecord.family_id == family_id)
            .order_by(AiUsageRecord.created_at.desc())
            .limit(500)
        ).all()
    )


@router.get("/families/{family_id}/audit-logs", response_model=list[AuditLogOut])
def list_audit_logs(
    family_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[DataAccessAuditLog]:
    require_family_role(db, family_id, user.id, {"admin"})
    member_ids = select(FamilyMember.user_id).where(FamilyMember.family_id == family_id)
    return list(
        db.scalars(
            select(DataAccessAuditLog)
            .where(DataAccessAuditLog.actor_id.in_(member_ids))
            .order_by(DataAccessAuditLog.created_at.desc())
            .limit(500)
        ).all()
    )
