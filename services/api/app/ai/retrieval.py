import json
import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..deps import require_membership
from ..models import Consent, KnowledgeChunk, KnowledgeDocument, Memory
from ..security import decrypt_text, utc_now
from .embeddings import build_embedding_service, cosine_similarity, local_hash_embedding


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


def _can_use_family_document(
    db: Session,
    *,
    family_id: str,
    user_id: str,
    document_owner_id: str,
    is_elder: bool,
) -> bool:
    if document_owner_id == user_id or not is_elder:
        return True
    grants = db.scalars(
        select(Consent).where(
            Consent.family_id == family_id,
            Consent.subject_user_id == user_id,
            Consent.consent_type == "family_knowledge",
            Consent.revoked_at.is_(None),
        )
    ).all()
    for grant in grants:
        if grant.grantee_user_id not in {None, document_owner_id}:
            continue
        if grant.expires_at is None:
            return True
        expires_at = grant.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=utc_now().tzinfo)
        if expires_at > utc_now():
            return True
    return False


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
    settings = get_settings()
    try:
        query_vector = build_embedding_service(settings).embed([query]).vectors[0]
    except Exception:
        query_vector = local_hash_embedding(query, settings.embedding_dimensions)
    documents = db.scalars(
        select(KnowledgeDocument).where(
            KnowledgeDocument.family_id == family_id,
            KnowledgeDocument.status == "active",
        )
    ).all()
    visible_documents: dict[str, KnowledgeDocument] = {}
    for document in documents:
        allowed = (
            document.visibility_scope == "family"
            or document.owner_user_id == user_id
            or (document.visibility_scope == "elder_only" and member.role == "elder")
            or (document.visibility_scope == "child_only" and member.role in {"child", "admin"})
        )
        if not allowed or not _can_use_family_document(
            db,
            family_id=family_id,
            user_id=user_id,
            document_owner_id=document.owner_user_id,
            is_elder=member.role == "elder",
        ):
            continue
        visible_documents[document.id] = document

    if visible_documents:
        chunks = db.scalars(
            select(KnowledgeChunk).where(
                KnowledgeChunk.document_id.in_(visible_documents),
                KnowledgeChunk.status == "active",
            )
        ).all()
        chunked_document_ids = {chunk.document_id for chunk in chunks}
        for chunk in chunks:
            document = visible_documents[chunk.document_id]
            content = decrypt_text(chunk.content_encrypted) or ""
            lexical_score = _score(query, document.title + " " + content)
            vector: list[float] = []
            if chunk.embedding_json:
                try:
                    vector = [float(value) for value in json.loads(chunk.embedding_json)]
                except (TypeError, ValueError, json.JSONDecodeError):
                    vector = []
            if not vector or len(vector) != len(query_vector):
                vector = local_hash_embedding(
                    document.title + "\n" + content, len(query_vector)
                )
            vector_score = max(0.0, cosine_similarity(query_vector, vector))
            score = round(0.65 * vector_score + 0.35 * lexical_score, 6)
            if score > 0:
                candidates.append(
                    Evidence("knowledge_chunk", chunk.id, document.title, content[:320], score)
                )
        for document_id, document in visible_documents.items():
            if document_id in chunked_document_ids:
                continue
            content = decrypt_text(document.content_encrypted) or ""
            lexical_score = _score(query, document.title + " " + content)
            vector_score = max(
                0.0,
                cosine_similarity(
                    query_vector,
                    local_hash_embedding(document.title + "\n" + content, len(query_vector)),
                ),
            )
            score = round(0.65 * vector_score + 0.35 * lexical_score, 6)
            if score > 0:
                candidates.append(
                    Evidence("knowledge", document.id, document.title, content[:320], score)
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
        lexical_score = _score(query, content)
        vector_score = max(
            0.0,
            cosine_similarity(query_vector, local_hash_embedding(content, len(query_vector))),
        )
        score = round(0.65 * vector_score + 0.35 * lexical_score, 6)
        if score > 0:
            candidates.append(Evidence("memory", memory.id, "已确认记忆", content[:240], score))

    candidates.sort(key=lambda item: item.score, reverse=True)
    return candidates[:limit]
