"""Request schemas for the X operations center."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class XOAuthStartRequest(BaseModel):
    redirect_uri: Optional[str] = None
    scopes: str = Field(
        default="tweet.read users.read tweet.write offline.access",
        min_length=1,
        max_length=512,
    )


class XAccountUpdateRequest(BaseModel):
    account_type: Optional[str] = None
    automated_label_enabled: Optional[bool] = None
    write_enabled: Optional[bool] = None
    auto_reply_enabled: Optional[bool] = None
    status: Optional[str] = None

    @field_validator("account_type")
    @classmethod
    def validate_account_type(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and value not in {"brand", "human", "automated"}:
            raise ValueError("account_type must be brand, human, or automated")
        return value

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and value not in {"active", "revoked", "disabled"}:
            raise ValueError("status must be active, revoked, or disabled")
        return value


class XApprovalEvidenceRequest(BaseModel):
    approval_reference: str = Field(min_length=3, max_length=2000)
    x_written_approval: bool = True


class XRegionCreateRequest(BaseModel):
    woeid: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    country_code: str = Field(default="", max_length=16)
    language: str = Field(default="", max_length=32)
    timezone: str = Field(default="UTC", max_length=64)
    poll_interval_seconds: int = Field(default=900, ge=60, le=86400)
    daily_request_budget: int = Field(default=0, ge=0)
    enabled: bool = True

    @field_validator("woeid")
    @classmethod
    def numeric_woeid(cls, value: str) -> str:
        if not value.isdigit():
            raise ValueError("woeid must be numeric")
        return value


class XRegionUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    country_code: Optional[str] = Field(default=None, max_length=16)
    language: Optional[str] = Field(default=None, max_length=32)
    timezone: Optional[str] = Field(default=None, max_length=64)
    poll_interval_seconds: Optional[int] = Field(default=None, ge=60, le=86400)
    daily_request_budget: Optional[int] = Field(default=None, ge=0)
    enabled: Optional[bool] = None


class XTopicRefreshRequest(BaseModel):
    region_ids: List[int] = Field(default_factory=list, max_length=20)
    max_trends: int = Field(default=20, ge=1, le=50)


class XTopicPostCollectionRequest(BaseModel):
    max_posts: int = Field(default=50, ge=1, le=500)
    language: Optional[str] = Field(default=None, max_length=32)


class XThreadCollectionRequest(BaseModel):
    max_posts: int = Field(default=50, ge=1, le=500)


class XConversationAnalysisRequest(BaseModel):
    topic: str = Field(default="", max_length=512)
    max_samples: int = Field(default=25, ge=3, le=100)


class XReplyCandidatesRequest(BaseModel):
    account_id: Optional[int] = Field(default=None, gt=0)
    brand_voice: str = Field(default="helpful, concise, transparent", max_length=2000)
    tone: Optional[str] = Field(default=None, max_length=128)
    candidate_count: int = Field(default=3, ge=1, le=3)
    mode: str = Field(default="draft_only")

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, value: str) -> str:
        if value not in {"draft_only", "manual_review", "auto_reply_candidate"}:
            raise ValueError("invalid generation mode")
        return value


class XReviewApprovalRequest(BaseModel):
    candidate_id: int = Field(gt=0)
    final_text: str = Field(min_length=1, max_length=280)
    content_hash: str = Field(min_length=64, max_length=128)
    explicit_confirmation: bool
    reason: str = Field(default="", max_length=2000)


class XReviewRejectRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class XReviewFlagRequest(BaseModel):
    action: str
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("action")
    @classmethod
    def validate_action(cls, value: str) -> str:
        if value not in {"fact_check", "block"}:
            raise ValueError("action must be fact_check or block")
        return value


class XPublishRequest(BaseModel):
    candidate_id: int = Field(gt=0)
    content_hash: str = Field(min_length=64, max_length=128)
    explicit_confirmation: bool
    publish_mode: str = Field(default="manual_review")

    @field_validator("publish_mode")
    @classmethod
    def validate_publish_mode(cls, value: str) -> str:
        if value not in {"manual_review", "auto_reply"}:
            raise ValueError("publish_mode must be manual_review or auto_reply")
        return value


class XAutomationControlsRequest(BaseModel):
    read_enabled: Optional[bool] = None
    write_enabled: Optional[bool] = None
    auto_reply_enabled: Optional[bool] = None
    global_kill_switch: Optional[bool] = None
    require_human_review: Optional[bool] = None
    daily_write_limit: Optional[int] = Field(default=None, ge=0, le=100000)
    hourly_write_limit: Optional[int] = Field(default=None, ge=0, le=10000)
    max_interactions_per_user: Optional[int] = Field(default=None, ge=1, le=1000)
    min_reply_interval_seconds: Optional[int] = Field(default=None, ge=0, le=86400)
    duplicate_threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    paused_topics: Optional[List[str]] = Field(default=None, max_length=500)
    paused_regions: Optional[List[str]] = Field(default=None, max_length=500)
    paused_keywords: Optional[List[str]] = Field(default=None, max_length=500)
    high_risk_topics: Optional[List[str]] = Field(default=None, max_length=500)
    allowed_intents: Optional[List[str]] = Field(default=None, max_length=100)
    auto_reply_intents: Optional[List[str]] = Field(default=None, max_length=100)
    reason: str = Field(default="operator control update", min_length=3, max_length=2000)


class XInteractionEvaluateRequest(BaseModel):
    account_post_ids: List[str] = Field(default_factory=list, max_length=500)


class XMentionsRefreshRequest(BaseModel):
    account_id: Optional[int] = Field(default=None, gt=0)
    since_id: str = Field(default="", max_length=64)
    max_posts: int = Field(default=50, ge=5, le=100)

    @field_validator("since_id")
    @classmethod
    def validate_since_id(cls, value: str) -> str:
        if value and not value.isdigit():
            raise ValueError("since_id must be a numeric X Post ID")
        return value


class XOptOutRequest(BaseModel):
    account_id: int = Field(default=0, ge=0)
    username_snapshot: str = Field(default="", max_length=255)
    source_interaction_id: Optional[int] = Field(default=None, gt=0)
    source_post_id: str = Field(default="", max_length=64)
    detected_phrase: str = Field(default="manual opt-out", min_length=1, max_length=500)
    evidence: dict = Field(default_factory=dict)
