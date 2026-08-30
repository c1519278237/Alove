from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class SmsRequest(BaseModel):
    phone: str = Field(min_length=6, max_length=30)


class SmsRequestResult(BaseModel):
    request_id: str
    expires_in: int
    debug_code: str | None = None


class SmsVerify(BaseModel):
    phone: str
    code: str = Field(pattern=r"^\d{6}$")
    display_name: str | None = Field(default=None, max_length=80)


class TokenResult(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str


class UserProfileOut(ORMModel):
    preferred_language: str
    region_code: str
    timezone: str
    font_scale: float
    accessibility_settings: dict[str, Any]


class UserOut(ORMModel):
    id: str
    display_name: str
    status: str
    created_at: datetime
    profile: UserProfileOut | None = None


class UserProfilePatch(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    preferred_language: str | None = None
    region_code: str | None = None
    timezone: str | None = None
    font_scale: float | None = Field(default=None, ge=1.0, le=2.0)
    accessibility_settings: dict[str, Any] | None = None


class FamilyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    my_role: Literal["elder", "child", "caregiver", "admin"] = "child"
    relationship_label: str | None = Field(default=None, max_length=50)


class FamilyOut(ORMModel):
    id: str
    name: str
    status: str
    created_by: str
    created_at: datetime


class FamilyMemberOut(ORMModel):
    family_id: str
    user_id: str
    role: str
    relationship_label: str | None
    status: str
    joined_at: datetime
    display_name: str | None = None


class InviteCreate(BaseModel):
    role: Literal["elder", "child", "caregiver"]
    relationship_label: str | None = Field(default=None, max_length=50)
    expires_hours: int = Field(default=24, ge=1, le=168)


class InviteOut(ORMModel):
    code: str
    family_id: str
    invited_role: str
    relationship_label: str | None
    expires_at: datetime


class InviteAccept(BaseModel):
    code: str = Field(min_length=6, max_length=12)


class MemberPatch(BaseModel):
    role: Literal["elder", "child", "caregiver", "admin"] | None = None
    relationship_label: str | None = Field(default=None, max_length=50)
    status: Literal["active", "disabled"] | None = None


class ConsentCreate(BaseModel):
    subject_user_id: str
    grantee_user_id: str | None = None
    family_id: str
    consent_type: Literal[
        "conversation_summary",
        "care_need_sharing",
        "family_knowledge",
        "voice_use",
        "audio_retention",
        "reminder_management",
    ]
    scope: dict[str, Any] = Field(default_factory=dict)
    policy_version: str = "v1.0"
    expires_at: datetime | None = None
    evidence_object_key: str | None = None


class ConsentOut(ORMModel):
    id: str
    subject_user_id: str
    grantee_user_id: str | None
    family_id: str
    consent_type: str
    scope: dict[str, Any]
    policy_version: str
    granted_at: datetime
    expires_at: datetime | None
    revoked_at: datetime | None


class AuditLogOut(ORMModel):
    id: str
    actor_id: str
    action: str
    resource_type: str
    resource_id: str
    reason: str
    result: str
    created_at: datetime


class ConversationCreate(BaseModel):
    family_id: str
    sharing_level: Literal["private", "family_summary", "selected"] = "private"


class ConversationOut(ORMModel):
    id: str
    family_id: str
    owner_user_id: str
    started_at: datetime
    ended_at: datetime | None
    sharing_level: str
    model_config_version: str
    status: str


class SharingLevelPatch(BaseModel):
    sharing_level: Literal["private", "family_summary", "selected"]


class ChatMessageCreate(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class MessageOut(BaseModel):
    id: str
    conversation_id: str
    role: str
    text: str
    source: str
    safety_labels: list[str]
    created_at: datetime


class ChatTurnOut(BaseModel):
    user_message: MessageOut
    assistant_message: MessageOut
    safety_level: str
    evidence: list[dict[str, str]] = Field(default_factory=list)


class KnowledgeCreate(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    content: str = Field(min_length=1, max_length=20_000)
    source_type: str = "manual"
    visibility_scope: Literal["private", "family", "elder_only", "child_only"] = "family"


class KnowledgeOut(BaseModel):
    id: str
    family_id: str
    owner_user_id: str
    title: str
    content: str
    source_type: str
    visibility_scope: str
    status: str
    created_at: datetime


class MemoryOut(BaseModel):
    id: str
    owner_user_id: str
    family_id: str
    memory_type: str
    content: str
    confidence: float
    sensitivity: str
    sharing_level: str
    confirmation_status: str
    source_message_ids: list[str]
    created_at: datetime


class CareNeedCreate(BaseModel):
    elder_user_id: str
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=2000)
    priority: Literal["low", "normal", "high"] = "normal"
    consent_id: str
    due_at: datetime | None = None


class CareNeedOut(BaseModel):
    id: str
    elder_user_id: str
    assignee_user_id: str | None
    title: str
    description: str
    status: str
    priority: str
    consent_id: str | None
    due_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class CareReportOut(BaseModel):
    id: str
    elder_user_id: str
    period_start: datetime
    period_end: datetime
    report: dict[str, Any]
    evidence_message_ids: list[str]
    generation_model: str
    prompt_version: str
    status: str
    feedback: str | None
    created_at: datetime


class ReportGenerate(BaseModel):
    period_days: int = Field(default=7, ge=1, le=31)


class ReportFeedback(BaseModel):
    feedback: Literal["accurate", "partly_accurate", "inaccurate"]


class ReminderCreate(BaseModel):
    owner_user_id: str
    content: str = Field(min_length=1, max_length=500)
    schedule_rule: str = Field(min_length=1, max_length=200)
    category: Literal["life", "activity", "hydration", "family"] = "life"


class ReminderPatch(BaseModel):
    content: str | None = Field(default=None, min_length=1, max_length=500)
    schedule_rule: str | None = Field(default=None, min_length=1, max_length=200)
    category: str | None = None
    status: Literal["active", "paused", "done"] | None = None


class ReminderOut(BaseModel):
    id: str
    owner_user_id: str
    creator_user_id: str
    content: str
    schedule_rule: str
    category: str
    status: str
    created_at: datetime


class FamilyMessageCreate(BaseModel):
    recipient_user_id: str
    type: Literal["text", "audio"] = "text"
    content: str = Field(min_length=1, max_length=3000)
    audio_object_key: str | None = None


class FamilyMessageOut(BaseModel):
    id: str
    sender_user_id: str
    recipient_user_id: str
    type: str
    content: str
    audio_object_key: str | None
    played_at: datetime | None
    created_at: datetime


class VoiceEnrollment(BaseModel):
    consent_id: str
    provider: str = Field(min_length=1, max_length=50)
    allowed_recipient_ids: list[str] = Field(min_length=1, max_length=10)
    expires_at: datetime | None = None


class VoiceProfileOut(BaseModel):
    id: str
    owner_user_id: str
    provider: str
    consent_id: str
    allowed_recipient_ids: list[str]
    status: str
    expires_at: datetime | None
    watermark_config: dict[str, Any]
    created_at: datetime


class HealthOut(BaseModel):
    status: str
    environment: str
    ai_provider: str
