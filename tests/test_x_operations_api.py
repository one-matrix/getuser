import importlib.util
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi import HTTPException
from sqlalchemy import select, text

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
from media_platform.x.exception import XBrowserError


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
    assert payload["effective_browser_write_allowed"] is False


def test_write_rate_limit_endpoint_normalization_matches_usage_keys(x_router_module):
    assert (
        x_router_module._normalize_endpoint("POST", "/tweets")
        == "POST /2/tweets"
    )


def test_browser_profile_conflict_is_returned_as_actionable_409(x_router_module):
    with pytest.raises(HTTPException) as captured:
        x_router_module._raise_x_browser_error(
            XBrowserError(
                "profile is open without CDP",
                error_code="browser_profile_in_use_without_cdp",
                retryable=True,
            )
        )

    assert captured.value.status_code == 409
    assert captured.value.detail["error_code"] == "browser_profile_in_use_without_cdp"


def test_x_snowflake_id_is_not_treated_as_postgres_integer_pk(x_router_module):
    assert x_router_module._local_post_pk("2077921225230426406") is None
    assert x_router_module._local_post_pk("2147483647") == 2_147_483_647
    assert x_router_module._local_post_pk("2147483648") is None
    assert x_router_module._local_post_pk("not-a-post-id") is None


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
async def test_browser_sync_creates_draft_only_account_without_oauth(
    x_app_client,
    x_router_module,
    monkeypatch,
):
    class FakeBrowser:
        @staticmethod
        async def get_current_identity():
            return {
                "id": "web:brandbot",
                "username": "brandbot",
                "name": "Brand Bot",
                "source": "browser_profile",
            }

    @asynccontextmanager
    async def fake_browser_reader(**kwargs):
        yield FakeBrowser()

    monkeypatch.setattr(x_router_module, "_browser_reader", fake_browser_reader)
    monkeypatch.setattr(
        x_router_module,
        "x_browser_profile_status",
        lambda: {
            "profile_source": "project_default",
            "profile_dir": "/tmp/x-profile",
            "profile_exists": True,
            "cookie_store_detected": True,
            "cdp_mode": True,
            "connect_existing": False,
            "debug_port": 9222,
            "headless": False,
            "browser_use_fallback_enabled": False,
        },
    )

    synced = await x_app_client.post("/api/x/browser/sync-account")
    assert synced.status_code == 200, synced.text
    account = synced.json()["account"]
    assert account["username"] == "brandbot"
    assert account["write_enabled"] is False
    assert account["auto_reply_enabled"] is False
    assert account["token_configured"] is False
    assert account["browser_synced"] is True

    listed = await x_app_client.get("/api/x/accounts")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["username"] == "brandbot"

    status = await x_app_client.get("/api/x/browser/status")
    assert status.status_code == 200
    assert status.json()["cookie_store_detected"] is True
    assert status.json()["synced_account_count"] == 1


@pytest.mark.asyncio
async def test_open_browser_login_uses_dedicated_profile(
    x_app_client,
    x_router_module,
    monkeypatch,
):
    monkeypatch.setattr(
        x_router_module,
        "launch_x_login_window",
        lambda: {
            "pid": 123,
            "profile_dir": "/tmp/x-profile",
            "browser_name": "Google Chrome",
            "url": "https://x.com/home",
        },
    )
    response = await x_app_client.post("/api/x/browser/open-login")
    assert response.status_code == 200, response.text
    assert response.json()["browser"]["profile_dir"] == "/tmp/x-profile"


@pytest.mark.asyncio
async def test_controlled_auto_reply_can_enable_without_written_approval(x_app_client):
    async with get_session() as session:
        account = XAccount(
            owner_user_id="1",
            x_user_id="auto-123",
            username="brandbot",
            display_name="Brand",
            granted_scopes='["tweet.write"]',
            automated_label_enabled=True,
            x_written_approval=False,
            status="active",
            created_at=1,
            updated_at=1,
        )
        session.add(account)
        await session.flush()
        account_id = account.id

    global_control = await x_app_client.patch(
        "/api/x/automation/controls",
        json={"auto_reply_enabled": True, "reason": "enable controlled auto reply"},
    )
    assert global_control.status_code == 200, global_control.text
    assert global_control.json()["controls"]["auto_reply_enabled"] is True

    account_control = await x_app_client.patch(
        f"/api/x/accounts/{account_id}",
        json={"auto_reply_enabled": True},
    )
    assert account_control.status_code == 200, account_control.text
    assert account_control.json()["account"]["auto_reply_enabled"] is True
    assert account_control.json()["account"]["x_written_approval"] is False


@pytest.mark.asyncio
async def test_prepare_manual_post_comment_is_hash_bound_and_idempotent(
    x_app_client,
    x_router_module,
    monkeypatch,
):
    async with get_session() as session:
        account = XAccount(
            owner_user_id="1",
            x_user_id="web:brandbot",
            username="brandbot",
            display_name="Brand",
            granted_scopes="[]",
            write_enabled=False,
            status="active",
            created_at=1,
            updated_at=1,
        )
        post = XPost(
            owner_user_id="1",
            x_post_id="2077921225230426406",
            author_x_user_id="author-1",
            author_username="author",
            text="A public post",
            conversation_id="2077921225230426406",
            created_at=1,
            updated_at=1,
        )
        session.add_all([account, post])
        await session.flush()
        account_id, post_id = account.id, post.id

    class FakeBrowser:
        @staticmethod
        async def get_current_identity():
            return {
                "id": "web:brandbot",
                "username": "brandbot",
                "name": "Brand",
                "source": "browser_profile",
            }

    @asynccontextmanager
    async def fake_browser_reader(**kwargs):
        yield FakeBrowser()

    monkeypatch.setattr(x_router_module, "_browser_reader", fake_browser_reader)

    controls = await x_app_client.patch(
        "/api/x/automation/controls",
        json={
            "write_enabled": True,
            "global_kill_switch": False,
            "reason": "enable explicit manual comment test",
        },
    )
    assert controls.status_code == 200, controls.text

    rejected = await x_app_client.post(
        f"/api/x/posts/{post_id}/comments/prepare",
        json={
            "text": "Thanks for sharing this.",
            "explicit_confirmation": False,
        },
    )
    assert rejected.status_code == 400

    body = {
        "text": "Thanks for sharing this.",
        "explicit_confirmation": True,
    }
    prepared = await x_app_client.post(
        f"/api/x/posts/{post_id}/comments/prepare",
        json=body,
    )
    assert prepared.status_code == 200, prepared.text
    payload = prepared.json()
    assert payload["candidate"]["model_version"] == "human-authored-browser-v1"
    assert payload["candidate"]["review_status"] == "approved"
    assert payload["review"]["review_status"] == "approved"
    assert payload["content_hash"] == content_hash(body["text"])
    assert payload["identity"]["username"] == "brandbot"
    assert payload["account"]["id"] == account_id

    replay = await x_app_client.post(
        f"/api/x/posts/{post_id}/comments/prepare",
        json=body,
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["reused"] is True
    assert replay.json()["candidate"]["id"] == payload["candidate"]["id"]
    assert replay.json()["review"]["id"] == payload["review"]["id"]


@pytest.mark.asyncio
async def test_manual_comment_publishes_to_visible_public_post(
    x_app_client,
    x_router_module,
    monkeypatch,
):
    async with get_session() as session:
        account = XAccount(
            owner_user_id="1",
            x_user_id="web:brandbot",
            username="brandbot",
            display_name="Brand",
            granted_scopes="[]",
            write_enabled=False,
            status="active",
            created_at=1,
            updated_at=1,
        )
        post = XPost(
            owner_user_id="1",
            x_post_id="2077921225230426406",
            author_x_user_id="public-author",
            author_username="author",
            text="A public post without a brand mention",
            conversation_id="2077921225230426406",
            created_at=1,
            updated_at=1,
        )
        session.add_all([account, post])
        await session.flush()
        account_id, post_id = account.id, post.id

    controls = await x_app_client.patch(
        "/api/x/automation/controls",
        json={
            "write_enabled": True,
            "global_kill_switch": False,
            "reason": "enable manual public reply test",
        },
    )
    assert controls.status_code == 200, controls.text
    automation_status = await x_app_client.get("/api/x/automation/status")
    assert automation_status.status_code == 200, automation_status.text
    assert automation_status.json()["effective_browser_write_allowed"] is True
    assert automation_status.json()["effective_write_allowed"] is False

    captured = {}

    class FakeBrowser:
        @staticmethod
        async def get_current_identity():
            return {
                "id": "web:brandbot",
                "username": "brandbot",
                "name": "Brand",
                "source": "browser_profile",
            }

        @staticmethod
        async def lookup_post(target_post_id):
            return {
                "data": {
                    "id": target_post_id,
                    "author_id": "public-author",
                    "text": "A public post without a brand mention",
                    "lang": "en",
                    "created_at": "2026-07-17T00:00:00.000Z",
                    "conversation_id": target_post_id,
                    "entities": {"mentions": []},
                    "referenced_tweets": [],
                },
                "includes": {
                    "users": [
                        {"id": "public-author", "username": "author", "name": "Author"}
                    ]
                },
            }

        @staticmethod
        async def publish_reply(**kwargs):
            captured.update(kwargs)
            return {
                "data": {"id": "published-comment-1", "text": kwargs["text"]},
                "meta": {"source": "browser", "http_status": 200, "confirmation": "test"},
            }

    @asynccontextmanager
    async def fake_browser_reader(**kwargs):
        yield FakeBrowser()

    monkeypatch.setattr(x_router_module, "_browser_reader", fake_browser_reader)

    comment_text = "Thanks for sharing this update."
    prepared = await x_app_client.post(
        f"/api/x/posts/{post_id}/comments/prepare",
        json={
            "text": comment_text,
            "explicit_confirmation": True,
        },
    )
    assert prepared.status_code == 200, prepared.text
    prepared_payload = prepared.json()

    published = await x_app_client.post(
        f"/api/x/reviews/{prepared_payload['review']['id']}/publish",
        json={
            "candidate_id": prepared_payload["candidate"]["id"],
            "content_hash": prepared_payload["content_hash"],
            "explicit_confirmation": True,
            "publish_mode": "manual_review",
        },
    )
    assert published.status_code == 200, published.text
    assert published.json()["x_post_id"] == "published-comment-1"
    assert prepared_payload["account"]["id"] == account_id
    assert captured["target_post_id"] == "2077921225230426406"
    assert captured["text"] == comment_text


@pytest.mark.asyncio
async def test_manual_comment_can_publish_multiple_confirmed_texts_to_same_target(
    x_app_client,
    x_router_module,
    monkeypatch,
):
    async with get_session() as session:
        account = XAccount(
            owner_user_id="1",
            x_user_id="web:brandbot",
            username="brandbot",
            display_name="Brand",
            granted_scopes="[]",
            write_enabled=False,
            status="active",
            created_at=1,
            updated_at=1,
        )
        post = XPost(
            owner_user_id="1",
            x_post_id="2077921225230426406",
            author_x_user_id="public-author",
            author_username="author",
            text="A public post",
            conversation_id="2077921225230426406",
            created_at=1,
            updated_at=1,
        )
        session.add_all([account, post])
        await session.flush()
        post_id = post.id

    controls = await x_app_client.patch(
        "/api/x/automation/controls",
        json={
            "write_enabled": True,
            "global_kill_switch": False,
            "reason": "enable multiple manual comments test",
        },
    )
    assert controls.status_code == 200, controls.text

    published_texts = []
    retained_page_requests = []

    class FakeBrowser:
        @staticmethod
        async def get_current_identity():
            return {
                "id": "web:brandbot",
                "username": "brandbot",
                "name": "Brand",
                "source": "browser_profile",
            }

        @staticmethod
        async def lookup_post(target_post_id):
            return {
                "data": {
                    "id": target_post_id,
                    "author_id": "public-author",
                    "text": "A public post",
                    "lang": "en",
                    "created_at": "2026-07-17T00:00:00.000Z",
                    "conversation_id": target_post_id,
                    "entities": {"mentions": []},
                    "referenced_tweets": [],
                },
                "includes": {
                    "users": [
                        {"id": "public-author", "username": "author", "name": "Author"}
                    ]
                },
            }

        @staticmethod
        async def publish_reply(**kwargs):
            published_texts.append(kwargs["text"])
            return {
                "data": {
                    "id": f"published-comment-{len(published_texts)}",
                    "text": kwargs["text"],
                },
                "meta": {"source": "browser", "http_status": 200, "confirmation": "test"},
            }

    @asynccontextmanager
    async def fake_browser_reader(**kwargs):
        retained_page_requests.append(bool(kwargs.get("retain_page")))
        yield FakeBrowser()

    monkeypatch.setattr(x_router_module, "_browser_reader", fake_browser_reader)

    async def prepare(text_value):
        response = await x_app_client.post(
            f"/api/x/posts/{post_id}/comments/prepare",
            json={"text": text_value, "explicit_confirmation": True},
        )
        assert response.status_code == 200, response.text
        return response.json()

    async def publish(prepared):
        return await x_app_client.post(
            f"/api/x/reviews/{prepared['review']['id']}/publish",
            json={
                "candidate_id": prepared["candidate"]["id"],
                "content_hash": prepared["content_hash"],
                "explicit_confirmation": True,
                "publish_mode": "manual_review",
            },
        )

    first_prepared = await prepare("First explicitly confirmed comment text.")
    first_publish = await publish(first_prepared)
    assert first_publish.status_code == 200, first_publish.text
    assert first_publish.json()["x_post_id"] == "published-comment-1"
    first_replay = await publish(first_prepared)
    assert first_replay.status_code == 200, first_replay.text
    assert first_replay.json()["idempotent_replay"] is True
    assert published_texts == ["First explicitly confirmed comment text."]

    second_prepared = await prepare("Second explicitly confirmed comment text.")
    second_publish = await publish(second_prepared)
    assert second_publish.status_code == 200, second_publish.text
    assert second_publish.json()["x_post_id"] == "published-comment-2"

    async with get_session() as session:
        jobs = (
            await session.execute(select(XPublishJob).order_by(XPublishJob.id.asc()))
        ).scalars().all()
        results = (
            await session.execute(select(XPublishResult).order_by(XPublishResult.id.asc()))
        ).scalars().all()
        assert len(jobs) == 2
        assert len(results) == 2
        assert [job.reply_text for job in jobs] == [
            "First explicitly confirmed comment text.",
            "Second explicitly confirmed comment text.",
        ]
        assert [job.approval_content_hash for job in jobs] == [
            first_prepared["content_hash"],
            second_prepared["content_hash"],
        ]
        assert all(job.status == "succeeded" for job in jobs)
        assert all(job.interaction_id is None for job in jobs)
        assert [result.x_post_id for result in results] == [
            "published-comment-1",
            "published-comment-2",
        ]
    assert published_texts == [
        "First explicitly confirmed comment text.",
        "Second explicitly confirmed comment text.",
    ]
    assert retained_page_requests
    assert all(retained_page_requests)


@pytest.mark.asyncio
async def test_long_x_post_id_lookup_is_tenant_scoped(
    x_app_client,
):
    long_x_post_id = "2077921225230426406"
    async with get_session() as session:
        session.add_all(
            [
                XPost(
                    owner_user_id="1",
                    x_post_id="111",
                    author_x_user_id="author-1",
                    author_username="owner-one",
                    text="Unrelated owner-one post",
                    conversation_id="111",
                    created_at=1,
                    updated_at=1,
                ),
                XPost(
                    owner_user_id="2",
                    x_post_id=long_x_post_id,
                    author_x_user_id="author-2",
                    author_username="owner-two",
                    text="Other tenant post",
                    conversation_id=long_x_post_id,
                    created_at=1,
                    updated_at=1,
                ),
            ]
        )

    response = await x_app_client.get(f"/api/x/posts/{long_x_post_id}")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_collect_thread_accepts_long_x_post_id(
    x_app_client,
    x_router_module,
    monkeypatch,
):
    long_x_post_id = "2077921225230426406"
    async with get_session() as session:
        session.add(
            XPost(
                owner_user_id="1",
                x_post_id=long_x_post_id,
                author_x_user_id="author-1",
                author_username="brand-fan",
                text="Root post",
                conversation_id=long_x_post_id,
                created_at=1,
                updated_at=1,
            )
        )

    class FakeBrowser:
        @staticmethod
        async def collect_thread(root_post_id, **kwargs):
            assert root_post_id == long_x_post_id
            return {
                "data": [
                    {
                        "id": long_x_post_id,
                        "author_id": "author-1",
                        "text": "Root post",
                        "lang": "en",
                        "created_at": "2026-07-17T08:00:00.000Z",
                        "conversation_id": long_x_post_id,
                        "public_metrics": {},
                    },
                    {
                        "id": "2077921225230426407",
                        "author_id": "author-2",
                        "text": "Reply post",
                        "lang": "en",
                        "created_at": "2026-07-17T08:01:00.000Z",
                        "conversation_id": long_x_post_id,
                        "referenced_tweets": [
                            {"type": "replied_to", "id": long_x_post_id}
                        ],
                        "public_metrics": {},
                    },
                ],
                "includes": {
                    "users": [
                        {"id": "author-1", "username": "brand-fan", "name": "Fan"},
                        {"id": "author-2", "username": "reply-user", "name": "Reply"},
                    ]
                },
                "meta": {"result_count": 2},
            }

    @asynccontextmanager
    async def fake_browser_reader(**kwargs):
        yield FakeBrowser()

    monkeypatch.setattr(x_router_module, "_browser_reader", fake_browser_reader)

    response = await x_app_client.post(
        f"/api/x/posts/{long_x_post_id}/collect-thread",
        json={"max_posts": 10},
    )

    assert response.status_code == 200, response.text
    assert response.json()["conversation"]["root_post_id"] == long_x_post_id
    assert len(response.json()["posts"]) == 2


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
    blocked_review_id = payload["items"][1]["review"]["id"]

    listed = await x_app_client.get("/api/x/reviews")
    assert listed.status_code == 200
    review = next(item for item in listed.json()["items"] if item["id"] == review_id)
    assert review["candidate"]["id"] == candidate["id"]
    assert review["post"]["x_post_id"] == "987654321"
    assert review["api_reply_eligible"] is True
    assert review["manual_browser_publish_eligible"] is True
    assert isinstance(review["policy_checks"], list)

    fact_check = await x_app_client.post(
        f"/api/x/reviews/{review_id}/flag",
        json={"action": "fact_check", "reason": "verify product claim"},
    )
    assert fact_check.status_code == 200, fact_check.text
    assert fact_check.json()["review"]["review_status"] == "needs_fact_check"
    assert fact_check.json()["review"]["candidate"]["requires_fact_check"] is True

    blocked = await x_app_client.post(
        f"/api/x/reviews/{blocked_review_id}/flag",
        json={"action": "block", "reason": "brand should not participate"},
    )
    assert blocked.status_code == 200, blocked.text
    assert blocked.json()["review"]["review_status"] == "blocked"
    assert blocked.json()["review"]["candidate"]["risk_level"] == "blocked"

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

    async def fake_mentions(username, **kwargs):
        assert username == "brandbot"
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

    class FakeBrowser:
        get_mentions = staticmethod(fake_mentions)

    @asynccontextmanager
    async def fake_browser_reader(**kwargs):
        yield FakeBrowser()

    monkeypatch.setattr(x_router_module, "_account_access_token", fake_access_token)
    monkeypatch.setattr(x_router_module, "_browser_reader", fake_browser_reader)

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
    from sqlalchemy import func, select

    final_text = "Thanks for reaching out."
    digest = content_hash(final_text)
    async with get_session() as session:
        account = XAccount(
            owner_user_id="1",
            x_user_id="123",
            username="brandbot",
            display_name="Brand",
            access_token_encrypted="",
            granted_scopes="[]",
            write_enabled=False,
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

    async def fake_lookup(post_id):
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

    async def flaky_create_reply(**kwargs):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise XBrowserError(
                "temporary upstream failure",
                error_code="upstream_503",
                retryable=True,
            )
        return {
            "data": {"id": "8001", "text": kwargs["text"]},
            "meta": {"source": "browser", "http_status": 200, "confirmation": "test"},
        }

    class FakeBrowser:
        lookup_post = staticmethod(fake_lookup)
        publish_reply = staticmethod(flaky_create_reply)

        @staticmethod
        async def get_current_identity():
            return {
                "id": "web:brandbot",
                "username": "brandbot",
                "name": "Brand",
                "source": "browser_profile",
            }

    @asynccontextmanager
    async def fake_browser_reader(**kwargs):
        yield FakeBrowser()

    monkeypatch.setattr(x_router_module, "_browser_reader", fake_browser_reader)
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
