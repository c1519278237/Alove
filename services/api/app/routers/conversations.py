from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai.memory import create_memory_candidates
from ..ai.orchestrator import evidence_as_dicts, run_turn
from ..config import get_settings
from ..database import get_db
from ..deps import get_current_user, require_membership
from ..errors import AppError, not_found
from ..models import AiUsageRecord, Conversation, Message, RiskEvent, User
from ..schemas import (
    ChatMessageCreate,
    ChatTurnOut,
    ConversationCreate,
    ConversationOut,
    MessageOut,
    SharingLevelPatch,
)
from ..security import decrypt_text, encrypt_text, utc_now

router = APIRouter(tags=["conversations"])


def _safety_notice(level: str, labels: list[str]) -> str | None:
    if level == "low":
        return None
    if "medical" in labels:
        return "健康信息仅作安全提示，不构成诊断或用药建议。"
    if "scam_or_transfer" in labels:
        return "已触发防诈骗保护：不要转账或透露验证码，请联系真实家人核实。"
    if level == "high":
        return "已触发高风险保护，请尽快联系真实家人或当地专业援助。"
    return "本轮内容需要谨慎核实，AI 不能替代真实家人或专业人员。"


def require_owned_conversation(db: Session, conversation_id: str, user_id: str) -> Conversation:
    conversation = db.get(Conversation, conversation_id)
    if (
        conversation is None
        or conversation.owner_user_id != user_id
        or conversation.status == "deleted"
    ):
        raise not_found("对话")
    return conversation


def message_out(message: Message) -> MessageOut:
    return MessageOut(
        id=message.id,
        conversation_id=message.conversation_id,
        role=message.role,
        text=decrypt_text(message.text_encrypted) or "",
        source=message.source,
        safety_labels=message.safety_labels,
        created_at=message.created_at,
    )


async def execute_chat_turn(
    db: Session,
    *,
    conversation: Conversation,
    text: str,
) -> tuple[Message, Message, object]:
    if conversation.status != "active":
        raise AppError("CONVERSATION_CLOSED", "该对话已经结束", 409)
    result = await run_turn(db, conversation=conversation, user_text=text)
    retention = utc_now() + timedelta(days=90)
    user_message = Message(
        conversation_id=conversation.id,
        role="user",
        text_encrypted=encrypt_text(text) or "",
        source="app",
        safety_labels=result.labels,
        retention_until=retention,
    )
    assistant_message = Message(
        conversation_id=conversation.id,
        role="assistant",
        text_encrypted=encrypt_text(result.text) or "",
        source=f"{result.provider}:{result.model}",
        safety_labels=result.labels,
        retention_until=retention,
    )
    db.add_all([user_message, assistant_message])
    db.flush()
    create_memory_candidates(
        db,
        owner_user_id=conversation.owner_user_id,
        family_id=conversation.family_id,
        source_message_id=user_message.id,
        text=text,
    )
    usage = result.usage
    prompt_tokens = int(usage.get("prompt_tokens", 0))
    completion_tokens = int(usage.get("completion_tokens", 0))
    total_tokens = int(usage.get("total_tokens", prompt_tokens + completion_tokens))
    settings = get_settings()
    estimated_cost = (
        prompt_tokens * settings.ai_input_cost_per_million_usd
        + completion_tokens * settings.ai_output_cost_per_million_usd
    ) / 1_000_000
    db.add(
        AiUsageRecord(
            user_id=conversation.owner_user_id,
            family_id=conversation.family_id,
            conversation_id=conversation.id,
            provider=result.provider,
            model=result.model,
            latency_ms=result.latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=estimated_cost,
        )
    )
    if result.safety_level == "high":
        db.add(
            RiskEvent(
                family_id=conversation.family_id,
                subject_user_id=conversation.owner_user_id,
                conversation_id=conversation.id,
                message_id=user_message.id,
                level=result.safety_level,
                labels=result.labels,
                summary_encrypted=encrypt_text("高风险对话触发：" + "、".join(result.labels)) or "",
            )
        )
    db.commit()
    return user_message, assistant_message, result


@router.post("/conversations", response_model=ConversationOut, status_code=201)
def create_conversation(
    payload: ConversationCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Conversation:
    require_membership(db, payload.family_id, user.id)
    conversation = Conversation(
        family_id=payload.family_id,
        owner_user_id=user.id,
        sharing_level=payload.sharing_level,
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[Conversation]:
    return list(
        db.scalars(
            select(Conversation)
            .where(
                Conversation.owner_user_id == user.id,
                Conversation.status != "deleted",
            )
            .order_by(Conversation.started_at.desc())
            .limit(100)
        ).all()
    )


@router.get("/conversations/{conversation_id}", response_model=ConversationOut)
def get_conversation(
    conversation_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Conversation:
    return require_owned_conversation(db, conversation_id, user.id)


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
def list_messages(
    conversation_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[MessageOut]:
    require_owned_conversation(db, conversation_id, user.id)
    rows = db.scalars(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
    ).all()
    return [message_out(row) for row in rows]


@router.post("/conversations/{conversation_id}/messages", response_model=ChatTurnOut)
async def create_message(
    conversation_id: str,
    payload: ChatMessageCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatTurnOut:
    conversation = require_owned_conversation(db, conversation_id, user.id)
    user_message, assistant_message, result = await execute_chat_turn(
        db, conversation=conversation, text=payload.text
    )
    return ChatTurnOut(
        user_message=message_out(user_message),
        assistant_message=message_out(assistant_message),
        safety_level=result.safety_level,
        evidence=evidence_as_dicts(result.evidence),
        safety_notice=_safety_notice(result.safety_level, result.labels),
    )


@router.post("/conversations/{conversation_id}/end", response_model=ConversationOut)
def end_conversation(
    conversation_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Conversation:
    conversation = require_owned_conversation(db, conversation_id, user.id)
    conversation.status = "ended"
    conversation.ended_at = utc_now()
    db.commit()
    return conversation


@router.post("/conversations/{conversation_id}/sharing-level", response_model=ConversationOut)
def change_sharing_level(
    conversation_id: str,
    payload: SharingLevelPatch,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Conversation:
    conversation = require_owned_conversation(db, conversation_id, user.id)
    conversation.sharing_level = payload.sharing_level
    db.commit()
    return conversation


@router.delete("/conversations/{conversation_id}", status_code=204)
def delete_conversation(
    conversation_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    conversation = require_owned_conversation(db, conversation_id, user.id)
    messages = db.scalars(select(Message).where(Message.conversation_id == conversation_id)).all()
    for message in messages:
        message.text_encrypted = encrypt_text("[deleted]") or ""
        message.text_redacted = "[deleted]"
        message.audio_object_key = None
        message.safety_labels = []
    conversation.status = "deleted"
    conversation.ended_at = utc_now()
    db.commit()
    return None
