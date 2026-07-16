# -*- coding: utf-8 -*-
"""X 官方 API 运营模型的 SQLite 兼容性与租户约束测试。"""

import pytest
from sqlalchemy import Text, create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database.models import (
    Base,
    CrawlerTaskModel,
    XAccount,
    XApiUsageDaily,
    XAuditLog,
    XConversation,
    XInteraction,
    XJob,
    XPolicyDecision,
    XPost,
    XPublishJob,
    XPublishResult,
    XRateLimitState,
    XRegion,
    XReplyCandidate,
    XReviewTask,
    XSystemControl,
    XThreadAnalysis,
    XTopic,
    XTopicSnapshot,
    XUserOptOut,
)


X_MODELS = (
    XAccount,
    XRegion,
    XTopic,
    XTopicSnapshot,
    XPost,
    XConversation,
    XInteraction,
    XThreadAnalysis,
    XReplyCandidate,
    XReviewTask,
    XPolicyDecision,
    XPublishJob,
    XPublishResult,
    XUserOptOut,
    XJob,
    XApiUsageDaily,
    XRateLimitState,
    XSystemControl,
    XAuditLog,
)


@pytest.fixture
def x_engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'x-models.db'}")
    Base.metadata.create_all(engine, tables=[model.__table__ for model in X_MODELS])
    yield engine
    engine.dispose()


def test_all_x_models_share_tenant_and_audit_columns(x_engine):
    assert len(X_MODELS) == 19
    for model in X_MODELS:
        assert "owner_user_id" in model.__table__.columns
        assert model.__table__.columns["owner_user_id"].nullable is False
        assert "created_at" in model.__table__.columns
        assert "updated_at" in model.__table__.columns


def test_json_payloads_use_sqlite_compatible_text_columns():
    for model in X_MODELS:
        for column in model.__table__.columns:
            if column.name.endswith("_json"):
                assert isinstance(column.type, Text), (
                    f"{model.__name__}.{column.name} must remain Text-compatible"
                )


def test_x_post_external_id_is_unique_per_owner(x_engine):
    session = Session(bind=x_engine)
    try:
        session.add_all(
            [
                XPost(
                    owner_user_id="owner-a",
                    x_post_id="1900000000000000000",
                    author_x_user_id="x-user-1",
                ),
                XPost(
                    owner_user_id="owner-b",
                    x_post_id="1900000000000000000",
                    author_x_user_id="x-user-1",
                ),
            ]
        )
        session.commit()

        session.add(
            XPost(
                owner_user_id="owner-a",
                x_post_id="1900000000000000000",
                author_x_user_id="x-user-2",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
    finally:
        session.close()


def test_publish_job_enforces_tenant_idempotency_key(x_engine):
    required = {
        "owner_user_id": "owner-a",
        "account_id": 1,
        "reply_candidate_id": 10,
        "policy_decision_id": 20,
        "target_post_id": "post-1",
        "publish_mode": "manual_review",
        "reply_text": "Thanks for reaching out.",
        "approval_content_hash": "hash-1",
        "idempotency_key": "publish-key",
    }
    session = Session(bind=x_engine)
    try:
        session.add(XPublishJob(**required))
        session.commit()

        session.add(
            XPublishJob(
                **{
                    **required,
                    "target_post_id": "post-2",
                    "approval_content_hash": "hash-2",
                }
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
    finally:
        session.close()


def test_generic_scheduler_has_interval_configuration():
    column = CrawlerTaskModel.__table__.columns["schedule_interval_seconds"]
    assert column.default.arg == 900
