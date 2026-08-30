import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..deps import require_membership
from ..models import KnowledgeDocument, Memory
from ..security import decrypt_text


@dataclass(slots=True)
class Evidence:
    source_type: str
    source_id: str
    title: str
    excerpt: str
    score: float


def _tokens(text: str) -> set[str]:
    latin = set(re.findall(r"[a-zA-Z0-9_]{2,}", text.lower()))
    chinese = "".join(re.findall(r"[\u4e00-\u9fff]", text))
    bigrams = {chinese[i : i + 2] for i in range(max(0, len(chinese) - 1))}
    return latin | bigrams


def _score(query: str, candidate: str) -> float:
    query_tokens = _tokens(query)
    if not query_tokens:
        return 0.0
    matched = query_tokens & _tokens(candidate)
    return len(matched) / len(query_tokens)


def retrieve_family_context(
    db: Session,
    *,
    family_id: str,
    user_id: str,
    query: str,
    limit: int = 4,
) -> list[Evidence]:
    member = require_membership(db, family_id, user_id)
    candidates: list[Evidence] = []
    documents = db.scalars(
        select(KnowledgeDocument).where(
            KnowledgeDocument.family_id == family_id,
            KnowledgeDocument.status == "active",
        )
    ).all()
    for document in documents:
        allowed = (
            document.visibility_scope == "family"
            or document.owner_user_id == user_id
            or (document.visibility_scope == "elder_only" and member.role == "elder")
            or (document.visibility_scope == "child_only" and member.role in {"child", "admin"})
        )
        if not allowed:
            continue
        content = decrypt_text(document.content_encrypted) or ""
        score = _score(query, document.title + " " + content)
        if score > 0:
            candidates.append(
                Evidence("knowledge", document.id, document.title, content[:240], score)
            )

    memories = db.scalars(
        select(Memory).where(
            Memory.family_id == family_id,
            Memory.owner_user_id == user_id,
            Memory.confirmation_status == "confirmed",
            Memory.deleted_at.is_(None),
        )
    ).all()
    for memory in memories:
        content = decrypt_text(memory.content_encrypted) or ""
        score = _score(query, content)
        if score > 0:
            candidates.append(Evidence("memory", memory.id, "已确认记忆", content[:240], score))

    candidates.sort(key=lambda item: item.score, reverse=True)
    return candidates[:limit]
