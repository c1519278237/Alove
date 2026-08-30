from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base
from .security import new_id, utc_now


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SmsCode(Base):
    __tablename__ = "sms_codes"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    phone_hash: Mapped[str] = mapped_column(String(64), index=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class User(Base, TimestampMixin):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    phone_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    phone_encrypted: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(String(80), default="新用户")
    status: Mapped[str] = mapped_column(String(24), default="active")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    profile: Mapped[UserProfile | None] = relationship(back_populates="user", uselist=False)


class UserProfile(Base):
    __tablename__ = "user_profiles"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    preferred_language: Mapped[str] = mapped_column(String(32), default="zh-CN")
    region_code: Mapped[str] = mapped_column(String(32), default="CN")
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Shanghai")
    font_scale: Mapped[float] = mapped_column(Float, default=1.2)
    accessibility_settings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    user: Mapped[User] = relationship(back_populates="profile")


class Family(Base, TimestampMixin):
    __tablename__ = "families"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(24), default="active")
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)


class FamilyMember(Base):
    __tablename__ = "family_members"
    __table_args__ = (UniqueConstraint("family_id", "user_id"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    family_id: Mapped[str] = mapped_column(ForeignKey("families.id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(24))
    relationship_label: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="active")
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class FamilyInvite(Base, TimestampMixin):
    __tablename__ = "family_invites"
    code: Mapped[str] = mapped_column(String(12), primary_key=True)
    family_id: Mapped[str] = mapped_column(ForeignKey("families.id"), index=True)
    invited_role: Mapped[str] = mapped_column(String(24))
    relationship_label: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class Consent(Base):
    __tablename__ = "consents"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    subject_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    grantee_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    family_id: Mapped[str] = mapped_column(ForeignKey("families.id"), index=True)
    consent_type: Mapped[str] = mapped_column(String(50), index=True)
    scope: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    policy_version: Mapped[str] = mapped_column(String(30), default="v1.0")
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    evidence_object_key: Mapped[str | None] = mapped_column(String(500), nullable=True)


class DataAccessAuditLog(Base):
    __tablename__ = "data_access_audit_logs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(80))
    resource_type: Mapped[str] = mapped_column(String(50))
    resource_id: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(String(200))
    result: Mapped[str] = mapped_column(String(30))
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    family_id: Mapped[str] = mapped_column(ForeignKey("families.id"), index=True)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sharing_level: Mapped[str] = mapped_column(String(30), default="private")
    model_config_version: Mapped[str] = mapped_column(String(30), default="v1")
    status: Mapped[str] = mapped_column(String(24), default="active")


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    role: Mapped[str] = mapped_column(String(24))
    text_encrypted: Mapped[str] = mapped_column(Text)
    text_redacted: Mapped[str | None] = mapped_column(Text, nullable=True)
    audio_object_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source: Mapped[str] = mapped_column(String(40), default="app")
    safety_labels: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, index=True
    )
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class KnowledgeDocument(Base, TimestampMixin):
    __tablename__ = "knowledge_documents"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    family_id: Mapped[str] = mapped_column(ForeignKey("families.id"), index=True)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(160))
    content_encrypted: Mapped[str] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(String(30), default="manual")
    visibility_scope: Mapped[str] = mapped_column(String(30), default="family")
    status: Mapped[str] = mapped_column(String(24), default="active")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class Memory(Base, TimestampMixin):
    __tablename__ = "memories"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    family_id: Mapped[str] = mapped_column(ForeignKey("families.id"), index=True)
    memory_type: Mapped[str] = mapped_column(String(30), default="fact")
    content_encrypted: Mapped[str] = mapped_column(Text)
    source_message_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    sensitivity: Mapped[str] = mapped_column(String(30), default="normal")
    sharing_level: Mapped[str] = mapped_column(String(30), default="private")
    confirmation_status: Mapped[str] = mapped_column(String(30), default="pending")
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CareNeed(Base, TimestampMixin):
    __tablename__ = "care_needs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    elder_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    assignee_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    title_encrypted: Mapped[str] = mapped_column(Text)
    description_encrypted: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    priority: Mapped[str] = mapped_column(String(20), default="normal")
    consent_id: Mapped[str | None] = mapped_column(ForeignKey("consents.id"), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CareReport(Base, TimestampMixin):
    __tablename__ = "care_reports"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    elder_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    report_json_encrypted: Mapped[str] = mapped_column(Text)
    evidence_message_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    generation_model: Mapped[str] = mapped_column(String(100), default="rules-v1")
    prompt_version: Mapped[str] = mapped_column(String(30), default="care-report-v1")
    status: Mapped[str] = mapped_column(String(30), default="ready")
    feedback: Mapped[str | None] = mapped_column(String(30), nullable=True)


class Reminder(Base, TimestampMixin):
    __tablename__ = "reminders"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    creator_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    content_encrypted: Mapped[str] = mapped_column(Text)
    schedule_rule: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(30), default="life")
    status: Mapped[str] = mapped_column(String(30), default="active")


class FamilyMessage(Base, TimestampMixin):
    __tablename__ = "family_messages"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    sender_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    recipient_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    type: Mapped[str] = mapped_column(String(24), default="text")
    content_encrypted: Mapped[str] = mapped_column(Text)
    audio_object_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    played_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class VoiceProfile(Base, TimestampMixin):
    __tablename__ = "voice_profiles"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    provider: Mapped[str] = mapped_column(String(50))
    provider_voice_ref_encrypted: Mapped[str] = mapped_column(Text)
    consent_id: Mapped[str] = mapped_column(ForeignKey("consents.id"))
    allowed_recipient_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    watermark_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


Index("ix_member_family_status", FamilyMember.family_id, FamilyMember.status)
Index("ix_consent_family_type", Consent.family_id, Consent.consent_type)
Index("ix_message_conversation_time", Message.conversation_id, Message.created_at)
