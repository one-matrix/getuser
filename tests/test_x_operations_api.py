import importlib.util
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text

from api.services.x.policy_service import content_hash
from database.db_session import get_session
from database.models import (
    XAccount,
    XInteraction,
    XPost,
    XPublishJob,
    XPublishResult,
    XReplyCandidate,
    XReviewTask,
)


@pytest.fixture(scope="session")
def x_router_module():
    path = Path(__file__).parent.parent / "api" / "routers" / "x_operations.py"
    spec = importlib.util.spec_from_file_location("x_operations_isolated", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


@pytest.fixture
async def x_app_client(test_engine, x_router_module):
    import database.db_session as dbs
    from api.services.auth import get_current_user

    original_engine_fn = dbs.get_async_engine
    dbs.get_async_engine = lambda *args, **kwargs: test_engine

    async def fake_current_user():
        return {"id": 1, "username": "testadmin", "role": "admin", "status": "active"}

    app = FastAPI()
    app.include_router(x_router_module.router, prefix="/api")
    app.dependency_overrides[get_current_user] = fake_current_user
    async with test_engine.begin() as connection:
        for table in [
            "x_publish_results",
            "x_publish_jobs",
            "x_policy_decisions",
            "x_review_tasks",
            "x_reply_candidates",
            "x_thread_analyses",
            "x_interactions",
            "x_conversations",
            "x_posts",
            "x_topic_snapshots",
            "x_topics",
            "x_regions",
            "x_accounts",
            "x_user_opt_outs",
            "x_jobs",
            "x_api_usage_daily",
            "x_rate_limit_state",
            "x_system_controls",
            "x_audit_logs",
        ]:
            await connection.execute(text(f"DELETE FROM {table}"))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    dbs.get_async_engine = original_engine_fn


@pytest.mark.asyncio
async def test_x_status_starts_write_disabled_and_kill_switch_on(x_app_client):
    response = await x_app_client.get("/api/x/automation/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["write_enabled"] is False
    assert payload["auto_reply_enabled"] is False
    assert payload["global_kill_switch"] is True
    assert payload["require_human_review"] is True
    assert payload["effective_write_allowed"] is False


def test_rate_limit_endpoint_normalization_matches_usage_keys(x_router_module):
    assert (
        x_router_module._normalize_endpoint("GET", "/trends/by/woeid/1")
        == "GET /2/trends/by/woeid/{woeid}"
    )
    assert (
        x_router_module._normalize_endpoint("GET", "/tweets/search/recent")
        == "GET /2/tweets/search/recent"
    )
    assert (
        x_router_module._normalize_endpoint("POST", "/tweets")
        == "POST /2/tweets"
    )


@pytest.mark.asyncio
async def test_policy_extras_survive_scalar_control_toggle(x_app_client):
    saved = await x_app_client.patch(
        "/api/x/automation/controls",
        json={
            "hourly_write_limit": 4,
            "max_interactions_per_user": 2,
            "min_reply_interval_seconds": 300,
            "duplicate_threshold": 0.8,
            "auto_reply_intents": ["support_question", "售后查询"],
            "paused_regions": ["23424977"],
            "paused_keywords": ["paused-campaign"],
            "high_risk_topics": ["unverified-breaking-news"],
            "reason": "save policy thresholds",
        },
    )
    assert saved.status_code == 200, saved.text
    toggled = await x_app_client.patch(
        "/api/x/automation/controls",
        json={"write_enabled": True, "reason": "toggle write only"},
    )
    assert toggled.status_code == 200, toggled.text
    status = (await x_app_client.get("/api/x/automation/status")).json()
    assert status["hourly_write_limit"] == 4
    assert status["max_interactions_per_user"] == 2
    assert status["min_reply_interval_seconds"] == 300
    assert status["duplicate_threshold"] == 0.8
    assert status["auto_reply_intents"] == ["support_question", "售后查询"]
    assert status["paused_regions"] == ["23424977"]
    assert status["paused_keywords"] == ["paused-campaign"]
    assert status["high_risk_topics"] == ["unverified-breaking-news"]


@pytest.mark.asyncio
async def test_x_region_create_and_list_persists(x_app_client):
    created = await x_app_client.post(
        "/api/x/regions",
        json={
            "woeid": "1",
            "name": "Worldwide",
            "language": "en",
            "poll_interval_seconds": 900,
        },
    )
    assert created.status_code == 200
    region_id = created.json()["region"]["id"]

    listed = await x_app_client.get("/api/x/regions")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["id"] == region_id


@pytest.mark.asyncio
async def test_x_fallback_candidate_review_and_hash_bound_approval(x_app_client, monkeypatch):
    from config import x_config

    monkeypatch.setattr(x_config, "LLM_BASE_URL", "")
    monkeypatch.setattr(x_config, "LLM_API_KEY", "")
    monkeypatch.setattr(x_config, "LLM_MODEL", "")
    async with get_session() as session:
        account = XAccount(
            owner_user_id="1",
            x_user_id="123",
            username="brandbot",
            display_name="Brand",
            granted_scopes='["tweet.read","tweet.write"]',
            status="active",
            created_at=1,
            updated_at=1,
        )
        post = XPost(
            owner_user_id="1",
            x_post_id="987654321",
            author_x_user_id="456",
            author_username="customer",
            text="Can you clarify how this works?",
            lang="en",
            conversation_id="987654321",
            entities_json='{"mentions":[{"username":"brandbot"}]}',
            created_at=1,
            updated_at=1,
        )
        session.add_all([account, post])
        await session.flush()
        account_id, post_id = account.id, post.id

    generated = await x_app_client.post(
        f"/api/x/posts/{post_id}/reply-candidates",
        json={"account_id": account_id, "tone": "friendly", "candidate_count": 3},
    )
    assert generated.status_code == 200, generated.text
    payload = generated.json()
    assert payload["fallback_used"] is True
    assert payload["total"] == 3
    first = payload["items"][0]
    review_id = first["review"]["id"]
    candidate = first["candidate"]

    listed = await x_app_client.get("/api/x/reviews")
    assert listed.status_code == 200
    review = next(item for item in listed.json()["items"] if item["id"] == review_id)
    assert review["candidate"]["id"] == candidate["id"]
    assert review["post"]["x_post_id"] == "987654321"
    assert review["api_reply_eligible"] is True
    assert isinstance(review["policy_checks"], list)

    rejected_hash = await x_app_client.post(
        f"/api/x/reviews/{review_id}/approve",
        json={
            "candidate_id": candidate["id"],
            "final_text": candidate["generated_text"],
            "content_hash": "0" * 64,
            "explicit_confirmation": True,
        },
    )
    assert rejected_hash.status_code == 400

    approved = await x_app_client.post(
        f"/api/x/reviews/{review_id}/approve",
        json={
            "candidate_id": candidate["id"],
            "final_text": candidate["generated_text"],
            "content_hash": content_hash(candidate["generated_text"]),
            "explicit_confirmation": True,
        },
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["review"]["review_status"] == "approved"


@pytest.mark.asyncio
async def test_mentions_refresh_only_collects_and_never_publishes(
    x_app_client,
    x_router_module,
    monkeypatch,
):
    async with get_session() as session:
        account = XAccount(
            owner_user_id="1",
            x_user_id="123",
            username="brandbot",
            display_name="Brand",
            access_token_encrypted="test-placeholder",
            granted_scopes='["tweet.read","users.read"]',
            status="active",
            created_at=1,
            updated_at=1,
        )
        session.add(account)
        await session.flush()
        account_id = account.id

    async def fake_access_token(*args, **kwargs):
        return "user-token"

    async def fake_mentions(self, user_id, **kwargs):
        assert user_id == "123"
        return {
            "data": [
                {
                    "id": "9001",
                    "author_id": "777",
                    "text": "@brandbot Can you help?",
                    "lang": "en",
                    "created_at": "2026-07-16T00:00:00.000Z",
                    "conversation_id": "9001",
                    "entities": {"mentions": [{"username": "brandbot"}]},
                    "referenced_tweets": [],
                }
            ],
            "includes": {
                "users": [{"id": "777", "username": "customer", "name": "Customer"}]
            },
            "meta": {"result_count": 1},
        }

    monkeypatch.setattr(x_router_module, "_account_access_token", fake_access_token)
    monkeypatch.setattr(x_router_module.XApiClient, "get_mentions", fake_mentions)

    response = await x_app_client.post(
        "/api/x/interactions/refresh",
        json={"account_id": account_id, "max_posts": 5},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total"] == 1
    assert payload["auto_publish_created"] is False
    assert payload["items"][0]["eligibility"]["eligible"] is True
    intent = payload["items"][0]["interaction"]["opt_in_evidence_json"]["intent"]
    assert intent["code"] == "support_question"
    assert intent["classifier_version"] == "rules-v1"

    async with get_session() as session:
        from sqlalchemy import select

        result = await session.execute(
            select(XInteraction).where(XInteraction.owner_user_id == "1")
        )
        interaction = result.scalars().one()
        assert interaction.interaction_post_id == "9001"
        assert interaction.status == "eligible"


@pytest.mark.asyncio
async def test_failed_publish_reuses_job_and_keeps_monotonic_attempt_history(
    x_app_client,
    x_router_module,
    monkeypatch,
):
    from media_platform.x.exception import XServerError
    from sqlalchemy import func, select

    final_text = "Thanks for reaching out."
    digest = content_hash(final_text)
    async with get_session() as session:
        account = XAccount(
            owner_user_id="1",
            x_user_id="123",
            username="brandbot",
            display_name="Brand",
            access_token_encrypted="test-placeholder",
            granted_scopes='["tweet.read","tweet.write"]',
            write_enabled=True,
            status="active",
            created_at=1,
            updated_at=1,
        )
        post = XPost(
            owner_user_id="1",
            x_post_id="7001",
            author_x_user_id="777",
            author_username="customer",
            text="@brandbot Can you help?",
            lang="en",
            conversation_id="7001",
            entities_json='{"mentions":[{"username":"brandbot"}]}',
            created_at=1,
            updated_at=1,
        )
        session.add_all([account, post])
        await session.flush()
        candidate = XReplyCandidate(
            owner_user_id="1",
            account_id=account.id,
            source_post_id=post.id,
            generated_text=final_text,
            style="informative",
            risk_level="low",
            confidence=0.95,
            requires_fact_check=False,
            model_version="test",
            prompt_version="test",
            content_hash=digest,
            review_status="approved",
            created_at=1,
            updated_at=1,
        )
        session.add(candidate)
        await session.flush()
        review = XReviewTask(
            owner_user_id="1",
            account_id=account.id,
            reply_candidate_id=candidate.id,
            review_status="approved",
            final_text=final_text,
            final_content_hash=digest,
            reviewed_by_user_id="1",
            reviewed_at=1,
            created_at=1,
            updated_at=1,
        )
        session.add(review)
        await session.flush()
        review_id, candidate_id = review.id, candidate.id

    controls = await x_app_client.patch(
        "/api/x/automation/controls",
        json={
            "write_enabled": True,
            "global_kill_switch": False,
            "reason": "enable controlled retry test",
        },
    )
    assert controls.status_code == 200, controls.text

    async def fake_access_token(*args, **kwargs):
        return "user-token"

    async def fake_lookup(self, post_id):
        return {
            "data": {
                "id": post_id,
                "author_id": "777",
                "text": "@brandbot Can you help?",
                "lang": "en",
                "created_at": "2026-07-16T00:00:00.000Z",
                "conversation_id": post_id,
                "entities": {"mentions": [{"username": "brandbot"}]},
                "referenced_tweets": [],
            },
            "includes": {
                "users": [{"id": "777", "username": "customer", "name": "Customer"}]
            },
        }

    attempts = {"count": 0}

    async def flaky_create_reply(self, **kwargs):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise XServerError(
                "temporary upstream failure",
                status_code=503,
                error_code="upstream_503",
                retryable=True,
            )
        return {"data": {"id": "8001", "text": kwargs["text"]}}

    monkeypatch.setattr(x_router_module, "_account_access_token", fake_access_token)
    monkeypatch.setattr(x_router_module.XApiClient, "lookup_post", fake_lookup)
    monkeypatch.setattr(x_router_module.XApiClient, "create_reply", flaky_create_reply)
    request_body = {
        "candidate_id": candidate_id,
        "content_hash": digest,
        "explicit_confirmation": True,
        "publish_mode": "manual_review",
    }

    first = await x_app_client.post(
        f"/api/x/reviews/{review_id}/publish",
        json=request_body,
    )
    assert first.status_code == 502, first.text
    async with get_session() as session:
        jobs = (await session.execute(select(XPublishJob))).scalars().all()
        assert len(jobs) == 1
        original_job_id = jobs[0].id
        assert jobs[0].status == "retry_wait"
        assert jobs[0].retry_count == 1
        results = (
            await session.execute(
                select(XPublishResult)
                .where(XPublishResult.publish_job_id == original_job_id)
                .order_by(XPublishResult.attempt_no)
            )
        ).scalars().all()
        assert [item.attempt_no for item in results] == [1]
        assert results[0].success is False

    second = await x_app_client.post(
        f"/api/x/reviews/{review_id}/publish",
        json=request_body,
    )
    assert second.status_code == 200, second.text
    assert second.json()["publish_job"]["id"] == original_job_id
    assert second.json()["x_post_id"] == "8001"

    async with get_session() as session:
        job_count = await session.execute(select(func.count(XPublishJob.id)))
        assert int(job_count.scalar() or 0) == 1
        job = (await session.execute(select(XPublishJob))).scalars().one()
        assert job.id == original_job_id
        assert job.status == "succeeded"
        results = (
            await session.execute(
                select(XPublishResult)
                .where(XPublishResult.publish_job_id == original_job_id)
                .order_by(XPublishResult.attempt_no)
            )
        ).scalars().all()
        assert [item.attempt_no for item in results] == [1, 2]
        assert [item.success for item in results] == [False, True]
