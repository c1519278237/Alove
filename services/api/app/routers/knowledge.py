from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_membership
from ..errors import forbidden, not_found
from ..models import KnowledgeChunk, KnowledgeDocument, Memory, User
from ..schemas import KnowledgeCreate, KnowledgeOut, MemoryCreate, MemoryOut, MemoryPatch
from ..security import decrypt_text, encrypt_text, utc_now

router = APIRouter(tags=["knowledge"])


def _chunk_text(content: str, *, max_chars: int = 700, overlap: int = 100) -> list[str]:
    normalized = "\n".join(line.strip() for line in content.splitlines() if line.strip())
    if not normalized:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(len(normalized), start + max_chars)
        if end < len(normalized):
            boundary = max(
                normalized.rfind("。", start, end),
                normalized.rfind("！", start, end),
                normalized.rfind("？", start, end),
                normalized.rfind("\n", start, end),
            )
            if boundary > start + max_chars // 2:
                end = boundary + 1
        chunks.append(normalized[start:end])
        if end >= len(normalized):
            break
        start = max(start + 1, end - overlap)
    return chunks


def _knowledge_out(document: KnowledgeDocument) -> KnowledgeOut:
    return KnowledgeOut(
        id=document.id,
        family_id=document.family_id,
        owner_user_id=document.owner_user_id,
        title=document.title,
        content=decrypt_text(document.content_encrypted) or "",
        source_type=document.source_type,
        visibility_scope=document.visibility_scope,
        status=document.status,
        created_at=document.created_at,
    )


def _memory_out(memory: Memory) -> MemoryOut:
    return MemoryOut(
        id=memory.id,
        owner_user_id=memory.owner_user_id,
        family_id=memory.family_id,
        memory_type=memory.memory_type,
        content=decrypt_text(memory.content_encrypted) or "",
        confidence=memory.confidence,
        sensitivity=memory.sensitivity,
        sharing_level=memory.sharing_level,
        confirmation_status=memory.confirmation_status,
        source_message_ids=memory.source_message_ids,
        created_at=memory.created_at,
    )


@router.post("/families/{family_id}/knowledge", response_model=KnowledgeOut, status_code=201)
def create_knowledge(
    family_id: str,
    payload: KnowledgeCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> KnowledgeOut:
    require_membership(db, family_id, user.id)
    document = KnowledgeDocument(
        family_id=family_id,
        owner_user_id=user.id,
        title=payload.title,
        content_encrypted=encrypt_text(payload.content) or "",
        source_type=payload.source_type,
        visibility_scope=payload.visibility_scope,
    )
    db.add(document)
    db.flush()
    for index, chunk in enumerate(_chunk_text(payload.content)):
        db.add(
            KnowledgeChunk(
                document_id=document.id,
                family_id=family_id,
                chunk_index=index,
                content_encrypted=encrypt_text(chunk) or "",
                token_count=max(1, len(chunk) // 2),
            )
        )
    db.commit()
    return _knowledge_out(document)


@router.get("/families/{family_id}/knowledge", response_model=list[KnowledgeOut])
def list_knowledge(
    family_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[KnowledgeOut]:
    member = require_membership(db, family_id, user.id)
    rows = db.scalars(
        select(KnowledgeDocument)
        .where(
            KnowledgeDocument.family_id == family_id,
            KnowledgeDocument.status == "active",
        )
        .order_by(KnowledgeDocument.updated_at.desc())
    ).all()
    visible = [
        row
        for row in rows
        if row.visibility_scope == "family"
        or row.owner_user_id == user.id
        or (row.visibility_scope == "elder_only" and member.role == "elder")
        or (row.visibility_scope == "child_only" and member.role in {"child", "admin"})
    ]
    return [_knowledge_out(row) for row in visible]


@router.delete("/knowledge/{document_id}", status_code=204)
def delete_knowledge(
    document_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    document = db.get(KnowledgeDocument, document_id)
    if document is None:
        raise not_found("家庭资料")
    member = require_membership(db, document.family_id, user.id)
    if document.owner_user_id != user.id and member.role != "admin":
        raise forbidden()
    document.status = "deleted"
    document.content_encrypted = encrypt_text("[deleted]") or ""
    document.updated_at = utc_now()
    chunks = db.scalars(
        select(KnowledgeChunk).where(KnowledgeChunk.document_id == document.id)
    ).all()
    for chunk in chunks:
        chunk.status = "deleted"
        chunk.content_encrypted = encrypt_text("[deleted]") or ""
    db.commit()
    return None


@router.get("/memories", response_model=list[MemoryOut])
def list_memories(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[MemoryOut]:
    rows = db.scalars(
        select(Memory)
        .where(Memory.owner_user_id == user.id, Memory.deleted_at.is_(None))
        .order_by(Memory.created_at.desc())
    ).all()
    return [_memory_out(row) for row in rows]


@router.post("/memories", response_model=MemoryOut, status_code=201)
def create_memory(
    payload: MemoryCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MemoryOut:
    require_membership(db, payload.family_id, user.id)
    memory = Memory(
        owner_user_id=user.id,
        family_id=payload.family_id,
        memory_type=payload.memory_type,
        content_encrypted=encrypt_text(payload.content) or "",
        confidence=1.0,
        sensitivity=payload.sensitivity,
        sharing_level=payload.sharing_level,
        confirmation_status="confirmed",
    )
    db.add(memory)
    db.commit()
    return _memory_out(memory)


def _owned_memory(db: Session, memory_id: str, user_id: str) -> Memory:
    memory = db.get(Memory, memory_id)
    if memory is None or memory.owner_user_id != user_id or memory.deleted_at is not None:
        raise not_found("记忆")
    return memory


@router.patch("/memories/{memory_id}", response_model=MemoryOut)
def patch_memory(
    memory_id: str,
    payload: MemoryPatch,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MemoryOut:
    memory = _owned_memory(db, memory_id, user.id)
    if payload.content is not None:
        memory.content_encrypted = encrypt_text(payload.content) or ""
    for field in ("memory_type", "sensitivity", "sharing_level"):
        value = getattr(payload, field)
        if value is not None:
            setattr(memory, field, value)
    memory.confirmation_status = "confirmed"
    db.commit()
    return _memory_out(memory)


@router.post("/memories/{memory_id}/confirm", response_model=MemoryOut)
def confirm_memory(
    memory_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MemoryOut:
    memory = _owned_memory(db, memory_id, user.id)
    memory.confirmation_status = "confirmed"
    db.commit()
    return _memory_out(memory)


@router.post("/memories/{memory_id}/reject", response_model=MemoryOut)
def reject_memory(
    memory_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MemoryOut:
    memory = _owned_memory(db, memory_id, user.id)
    memory.confirmation_status = "rejected"
    db.commit()
    return _memory_out(memory)


@router.delete("/memories/{memory_id}", status_code=204)
def delete_memory(
    memory_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    memory = _owned_memory(db, memory_id, user.id)
    memory.deleted_at = utc_now()
    memory.content_encrypted = encrypt_text("[deleted]") or ""
    db.commit()
    return None
