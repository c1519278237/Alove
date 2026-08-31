from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Memory
from ..security import decrypt_text, encrypt_text

SENSITIVE_TERMS = (
    "癌",
    "病",
    "药",
    "欠债",
    "存款",
    "银行卡",
    "吵架",
    "虐待",
    "自杀",
)

PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("preference", re.compile(r"我(?:很|最|比较)?喜欢([^。！？\n]{1,40})")),
    ("preference", re.compile(r"我不喜欢([^。！？\n]{1,40})")),
    ("routine", re.compile(r"我每天([^。！？\n]{1,50})")),
    ("routine", re.compile(r"我通常([^。！？\n]{1,50})")),
    ("fact", re.compile(r"我住在([^。！？\n]{1,50})")),
)


def create_memory_candidates(
    db: Session,
    *,
    owner_user_id: str,
    family_id: str,
    source_message_id: str,
    text: str,
) -> list[Memory]:
    """Create low-risk candidates only; the owner must confirm before retrieval."""
    if any(term in text for term in SENSITIVE_TERMS):
        return []
    candidates: list[Memory] = []
    existing = db.scalars(
        select(Memory).where(
            Memory.owner_user_id == owner_user_id,
            Memory.family_id == family_id,
            Memory.deleted_at.is_(None),
        )
    ).all()
    existing_texts = {decrypt_text(item.content_encrypted) or "" for item in existing}
    for memory_type, pattern in PATTERNS:
        match = pattern.search(text)
        if match is None:
            continue
        content = match.group(0).strip("，,。！？ ")
        if len(content) < 4 or content in existing_texts:
            continue
        memory = Memory(
            owner_user_id=owner_user_id,
            family_id=family_id,
            memory_type=memory_type,
            content_encrypted=encrypt_text(content) or "",
            source_message_ids=[source_message_id],
            confidence=0.72,
            sensitivity="normal",
            sharing_level="private",
            confirmation_status="pending",
        )
        db.add(memory)
        candidates.append(memory)
        existing_texts.add(content)
        if len(candidates) >= 2:
            break
    return candidates
