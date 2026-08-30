from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai.orchestrator import evidence_as_dicts, run_turn
from ..database import get_db
from ..deps import get_current_user, require_membership
from ..errors import AppError, not_found
from ..models import Conversation, Message, User
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
