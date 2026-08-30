import json
from collections import Counter
from datetime import timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..audit import append_audit_log
from ..database import get_db
from ..deps import get_current_user
from ..errors import consent_required, forbidden, not_found
from ..models import (
    CareNeed,
    CareReport,
    Consent,
    Conversation,
    FamilyMember,
    FamilyMessage,
    Message,
    User,
)
from ..schemas import (
    CareNeedCreate,
    CareNeedOut,
    CareReportOut,
    FamilyMessageCreate,
    FamilyMessageOut,
    ReportFeedback,
    ReportGenerate,
)
from ..security import decrypt_text, encrypt_text, utc_now
from .consents import is_consent_active, require_active_consent

router = APIRouter(tags=["care"])


TOPIC_TERMS = {
    "家人联系": ("女儿", "儿子", "孩子", "家人", "电话"),
    "饮食与日常": ("吃饭", "做饭", "菜", "买菜", "睡觉"),
    "身体感受": ("疼", "不舒服", "头晕", "睡不着", "累"),
    "外出与活动": ("散步", "出门", "公园", "锻炼", "活动"),
    "情绪与陪伴": ("孤单", "想念", "无聊", "开心", "担心"),
}


def _common_family_ids(db: Session, first_user_id: str, second_user_id: str) -> set[str]:
    first = set(
        db.scalars(
            select(FamilyMember.family_id).where(
                FamilyMember.user_id == first_user_id, FamilyMember.status == "active"
            )
        ).all()
    )
    second = set(
        db.scalars(
            select(FamilyMember.family_id).where(
                FamilyMember.user_id == second_user_id, FamilyMember.status == "active"
            )
        ).all()
    )
    return first & second


def _active_grant(
    db: Session, *, subject_id: str, grantee_id: str, consent_type: str
) -> Consent | None:
    grants = db.scalars(
        select(Consent).where(
            Consent.subject_user_id == subject_id,
            Consent.consent_type == consent_type,
            or_(Consent.grantee_user_id == grantee_id, Consent.grantee_user_id.is_(None)),
        )
    ).all()
    for grant in grants:
        if is_consent_active(grant) and grant.family_id in _common_family_ids(
            db, subject_id, grantee_id
        ):
            return grant
    return None


def _need_out(need: CareNeed) -> CareNeedOut:
    return CareNeedOut(
        id=need.id,
        elder_user_id=need.elder_user_id,
        assignee_user_id=need.assignee_user_id,
        title=decrypt_text(need.title_encrypted) or "",
        description=decrypt_text(need.description_encrypted) or "",
        status=need.status,
        priority=need.priority,
        consent_id=need.consent_id,
        due_at=need.due_at,
        completed_at=need.completed_at,
        created_at=need.created_at,
    )


def _report_out(report: CareReport) -> CareReportOut:
    raw = decrypt_text(report.report_json_encrypted) or "{}"
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = {"status": "unavailable"}
    return CareReportOut(
        id=report.id,
        elder_user_id=report.elder_user_id,
        period_start=report.period_start,
        period_end=report.period_end,
        report=payload,
        evidence_message_ids=report.evidence_message_ids,
        generation_model=report.generation_model,
        prompt_version=report.prompt_version,
        status=report.status,
        feedback=report.feedback,
        created_at=report.created_at,
    )


@router.post("/care-needs", response_model=CareNeedOut, status_code=201)
def create_care_need(
    payload: CareNeedCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CareNeedOut:
    if payload.elder_user_id != user.id:
        raise forbidden("只有老人本人确认后才能转达需求")
    consent = require_active_consent(
        db,
        consent_id=payload.consent_id,
        subject_user_id=user.id,
        consent_type="care_need_sharing",
        grantee_user_id=None,
    )
    need = CareNeed(
        elder_user_id=user.id,
        assignee_user_id=consent.grantee_user_id,
        title_encrypted=encrypt_text(payload.title) or "",
        description_encrypted=encrypt_text(payload.description) or "",
        priority=payload.priority,
        consent_id=consent.id,
        due_at=payload.due_at,
    )
    db.add(need)
    db.commit()
    return _need_out(need)


@router.get("/elders/{elder_id}/needs", response_model=list[CareNeedOut])
def list_needs(
    elder_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[CareNeedOut]:
    if (
        elder_id != user.id
        and _active_grant(
            db, subject_id=elder_id, grantee_id=user.id, consent_type="care_need_sharing"
        )
        is None
    ):
        raise consent_required()
    rows = db.scalars(
        select(CareNeed)
        .where(CareNeed.elder_user_id == elder_id)
        .order_by(CareNeed.created_at.desc())
    ).all()
    append_audit_log(
        db,
        actor_id=user.id,
        action="care_need.list",
        resource_type="user",
        resource_id=elder_id,
        reason="care coordination",
        request=request,
    )
    db.commit()
    return [_need_out(row) for row in rows]


def _accessible_need(db: Session, need_id: str, user_id: str) -> CareNeed:
    need = db.get(CareNeed, need_id)
    if need is None:
        raise not_found("需求")
    if need.elder_user_id == user_id or need.assignee_user_id == user_id:
        return need
    if _active_grant(
        db,
        subject_id=need.elder_user_id,
        grantee_id=user_id,
        consent_type="care_need_sharing",
    ):
        return need
    raise not_found("需求")


@router.post("/care-needs/{need_id}/accept", response_model=CareNeedOut)
def accept_need(
    need_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CareNeedOut:
    need = _accessible_need(db, need_id, user.id)
    if need.elder_user_id == user.id:
        raise forbidden("需求需要由家属或照护者接收")
    need.assignee_user_id = user.id
    need.status = "accepted"
    db.commit()
    return _need_out(need)


@router.post("/care-needs/{need_id}/complete", response_model=CareNeedOut)
def complete_need(
    need_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CareNeedOut:
    need = _accessible_need(db, need_id, user.id)
    if need.assignee_user_id != user.id:
        raise forbidden("只有接收该需求的家属可以标记完成")
    need.status = "completed"
    need.completed_at = utc_now()
    db.commit()
    return _need_out(need)


def _report_access_allowed(db: Session, elder_id: str, viewer_id: str) -> bool:
    return (
        elder_id == viewer_id
        or _active_grant(
            db,
            subject_id=elder_id,
            grantee_id=viewer_id,
            consent_type="conversation_summary",
        )
        is not None
    )


@router.post("/elders/{elder_id}/care-reports/generate", response_model=CareReportOut)
def generate_report(
    elder_id: str,
    payload: ReportGenerate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CareReportOut:
    if not _report_access_allowed(db, elder_id, user.id):
        raise consent_required()
    period_end = utc_now()
    period_start = period_end - timedelta(days=payload.period_days)
    conversations = db.scalars(
        select(Conversation).where(
            Conversation.owner_user_id == elder_id,
            Conversation.sharing_level.in_(["family_summary", "selected"]),
            Conversation.started_at >= period_start,
            Conversation.status != "deleted",
        )
    ).all()
    conversation_ids = [row.id for row in conversations]
    messages = []
    if conversation_ids:
        messages = list(
            db.scalars(
                select(Message)
                .where(
                    Message.conversation_id.in_(conversation_ids),
                    Message.role == "user",
                    Message.created_at >= period_start,
                )
                .order_by(Message.created_at)
            ).all()
        )
    topic_counts: Counter[str] = Counter()
    for message in messages:
        text = decrypt_text(message.text_encrypted) or ""
        for topic, terms in TOPIC_TERMS.items():
            if any(term in text for term in terms):
                topic_counts[topic] += 1
    needs = db.scalars(
        select(CareNeed)
        .where(CareNeed.elder_user_id == elder_id, CareNeed.created_at >= period_start)
        .order_by(CareNeed.created_at.desc())
    ).all()
    report_payload = {
        "title": "生活状态与关怀摘要",
        "disclaimer": "仅基于老人已授权分享的对话生成，不是医疗诊断或完整生活记录。",
        "period": {"start": period_start.isoformat(), "end": period_end.isoformat()},
        "data_sufficiency": "limited" if len(messages) < 5 else "normal",
        "shared_conversation_count": len(conversations),
        "shared_message_count": len(messages),
        "frequent_topics": [
            {"topic": topic, "mentions": count} for topic, count in topic_counts.most_common(5)
        ],
        "needs": [
            {
                "need_id": need.id,
                "title": decrypt_text(need.title_encrypted),
                "status": need.status,
                "priority": need.priority,
            }
            for need in needs[:10]
        ],
        "recommended_action": (
            "数据较少，建议先直接联系老人了解近况。"
            if len(messages) < 5
            else "可结合需求列表主动联系老人，核实需要家人回应的事项。"
        ),
    }
    report = CareReport(
        elder_user_id=elder_id,
        period_start=period_start,
        period_end=period_end,
        report_json_encrypted=encrypt_text(json.dumps(report_payload, ensure_ascii=False)) or "",
        evidence_message_ids=[row.id for row in messages],
        generation_model="evidence-rules-v1",
    )
    db.add(report)
    db.commit()
    return _report_out(report)


@router.get("/elders/{elder_id}/care-reports", response_model=list[CareReportOut])
def list_reports(
    elder_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[CareReportOut]:
    if not _report_access_allowed(db, elder_id, user.id):
        raise consent_required()
    rows = db.scalars(
        select(CareReport)
        .where(CareReport.elder_user_id == elder_id)
        .order_by(CareReport.created_at.desc())
    ).all()
    append_audit_log(
        db,
        actor_id=user.id,
        action="care_report.list",
        resource_type="user",
        resource_id=elder_id,
        reason="view authorized care summary",
        request=request,
    )
    db.commit()
    return [_report_out(row) for row in rows]


@router.get("/care-reports/{report_id}", response_model=CareReportOut)
def get_report(
    report_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CareReportOut:
    report = db.get(CareReport, report_id)
    if report is None or not _report_access_allowed(db, report.elder_user_id, user.id):
        raise not_found("关怀摘要")
    return _report_out(report)


@router.post("/care-reports/{report_id}/feedback", response_model=CareReportOut)
def feedback_report(
    report_id: str,
    payload: ReportFeedback,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CareReportOut:
    report = db.get(CareReport, report_id)
    if report is None or not _report_access_allowed(db, report.elder_user_id, user.id):
        raise not_found("关怀摘要")
    report.feedback = payload.feedback
    db.commit()
    return _report_out(report)


def _family_message_out(message: FamilyMessage) -> FamilyMessageOut:
    return FamilyMessageOut(
        id=message.id,
        sender_user_id=message.sender_user_id,
        recipient_user_id=message.recipient_user_id,
        type=message.type,
        content=decrypt_text(message.content_encrypted) or "",
        audio_object_key=message.audio_object_key,
        played_at=message.played_at,
        created_at=message.created_at,
    )


@router.post("/family-messages", response_model=FamilyMessageOut, status_code=201)
def create_family_message(
    payload: FamilyMessageCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FamilyMessageOut:
    if not _common_family_ids(db, user.id, payload.recipient_user_id):
        raise not_found("家庭成员")
    message = FamilyMessage(
        sender_user_id=user.id,
        recipient_user_id=payload.recipient_user_id,
        type=payload.type,
        content_encrypted=encrypt_text(payload.content) or "",
        audio_object_key=payload.audio_object_key,
    )
    db.add(message)
    db.commit()
    return _family_message_out(message)


@router.get("/family-messages/inbox", response_model=list[FamilyMessageOut])
def family_message_inbox(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[FamilyMessageOut]:
    rows = db.scalars(
        select(FamilyMessage)
        .where(FamilyMessage.recipient_user_id == user.id)
        .order_by(FamilyMessage.created_at.desc())
        .limit(100)
    ).all()
    return [_family_message_out(row) for row in rows]


@router.post("/family-messages/{message_id}/played", response_model=FamilyMessageOut)
def mark_message_played(
    message_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FamilyMessageOut:
    message = db.get(FamilyMessage, message_id)
    if message is None or message.recipient_user_id != user.id:
        raise not_found("家庭留言")
    message.played_at = utc_now()
    db.commit()
    return _family_message_out(message)
