# -*- coding: utf-8 -*-
"""X crawler collection-to-database persistence tests."""

import json

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

import config
from config import x_config
from database.models import (
    CrawlerTaskModel,
    XApiUsageDaily,
    XJob,
    XPost,
    XRateLimitState,
    XRegion,
    XTopic,
    XTopicSnapshot,
)
from media_platform.x.core import XBrowserCrawler
from media_platform.x.persistence import XCrawlLimitExceeded


X_PERSISTENCE_TABLES = (
    CrawlerTaskModel.__table__,
    XRegion.__table__,
    XTopic.__table__,
    XTopicSnapshot.__table__,
    XPost.__table__,
    XJob.__table__,
    XApiUsageDaily.__table__,
    XRateLimitState.__table__,
)


@pytest.fixture
async def x_persistence_store(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'x-persistence.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: [
                table.create(sync_connection, checkfirst=True)
                for table in X_PERSISTENCE_TABLES
            ]
        )
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield engine, factory
    await engine.dispose()


async def _seed_crawler_task(factory, *, task_id, owner_user_id):
    async with factory() as session:
        session.add(
            CrawlerTaskModel(
                id=task_id,
                name="X scheduled task",
                platform="x",
                keywords='["MediaCrawler"]',
                crawl_type="search",
                owner_user_id=owner_user_id,
                created_ts=1,
                updated_ts=1,
            )
        )
        await session.commit()


class FakeXClient:
    def __init__(self, *, fail_search=False):
        self.fail_search = fail_search
        self.search_calls = 0

    async def search_topic(self, topic, *, lang=None, max_total=50):
        self.search_calls += 1
        if self.fail_search:
            raise RuntimeError("X browser search unavailable")
        return {
            "query": f'"{topic}" -is:retweet',
            "data": [
                {
                    "id": "1900000000000000001",
                    "author_id": "1001",
                    "text": f"Post about {topic}",
                    "lang": lang or "en",
                    "created_at": "2026-07-16T08:00:00Z",
                    "conversation_id": "1900000000000000001",
                    "public_metrics": {
                        "like_count": 2,
                        "reply_count": 1,
                        "retweet_count": 0,
                        "quote_count": 0,
                    },
                    "referenced_tweets": [],
                    "entities": {"hashtags": [{"tag": topic}]},
                }
            ],
            "includes": {
                "users": [
                    {
                        "id": "1001",
                        "username": "author",
                        "name": "Author",
                    }
                ]
            },
            "meta": {"result_count": 1},
        }

    async def get_trends(self, woeid, *, max_trends=20, region_name=""):
        return {
            "data": [
                {"trend_name": "#Launch", "tweet_count": 123},
                {"trend_name": "Product News", "tweet_count": 45},
            ][:max_trends]
        }

    async def lookup_post(self, post_id):
        return {"data": {"id": post_id, "text": "root"}}

    async def collect_thread(self, root_post_id, *, max_total=50):
        return {"data": [], "meta": {"result_count": 0}}


@pytest.mark.asyncio
async def test_search_task_persists_topic_snapshot_post_and_job(
    x_persistence_store,
    monkeypatch,
):
    _, factory = x_persistence_store
    monkeypatch.setattr(config, "CRAWLER_TYPE", "search")
    monkeypatch.setattr(config, "KEYWORDS", "MediaCrawler")
    monkeypatch.setattr(x_config, "X_READ_ENABLED", True)
    monkeypatch.setattr(x_config, "X_MAX_TOPICS_PER_CYCLE", 5)
    monkeypatch.setattr(x_config, "X_MAX_POSTS_PER_TOPIC", 50)
    monkeypatch.delenv("X_CRAWLER_MODE", raising=False)
    monkeypatch.delenv("X_SEARCH_TOPIC", raising=False)
    await _seed_crawler_task(
        factory,
        task_id="task-x-search",
        owner_user_id="owner-1",
    )

    crawler = XBrowserCrawler(
        FakeXClient(),
        session_factory=factory,
        task_id="task-x-search",
    )
    result = await crawler.start()
    assert result["mode"] == "search"
    assert result["post_count"] == 1

    async with factory() as session:
        topic = (await session.execute(select(XTopic))).scalar_one()
        snapshot = (await session.execute(select(XTopicSnapshot))).scalar_one()
        post = (await session.execute(select(XPost))).scalar_one()
        job = (await session.execute(select(XJob))).scalar_one()
        usage = (await session.execute(select(XApiUsageDaily))).scalar_one()

    assert topic.owner_user_id == "owner-1"
    assert topic.normalized_name == "mediacrawler"
    assert snapshot.topic_id == topic.id
    assert post.source_topic_id == topic.id
    assert post.owner_user_id == "owner-1"
    assert isinstance(post.public_metrics_json, str)
    assert json.loads(post.public_metrics_json)["like_count"] == 2
    assert isinstance(post.entities_json, str)
    assert json.loads(post.entities_json)["hashtags"][0]["tag"] == "MediaCrawler"
    assert job.status == "succeeded"
    assert json.loads(job.payload_json)["task_id"] == "task-x-search"
    assert json.loads(job.result_json)["post_count"] == 1
    assert usage.endpoint == "BROWSER /search?f=live"
    assert usage.request_count == 1
    assert usage.success_count == 1
    assert usage.read_resource_count == 1


@pytest.mark.asyncio
async def test_trending_task_persists_topics_snapshots_and_job(
    x_persistence_store,
    monkeypatch,
):
    _, factory = x_persistence_store
    monkeypatch.setattr(config, "CRAWLER_TYPE", "trending")
    monkeypatch.setattr(x_config, "X_READ_ENABLED", True)
    monkeypatch.setattr(x_config, "X_MAX_TOPICS_PER_CYCLE", 5)
    monkeypatch.delenv("X_CRAWLER_MODE", raising=False)

    crawler = XBrowserCrawler(
        FakeXClient(),
        session_factory=factory,
        owner_user_id="owner-2",
        task_id="task-x-trends",
    )
    result = await crawler.start()
    assert result["mode"] == "trending"
    assert result["persistence"]["snapshot_count"] == 2

    async with factory() as session:
        topic_count = await session.scalar(select(func.count()).select_from(XTopic))
        snapshot_count = await session.scalar(
            select(func.count()).select_from(XTopicSnapshot)
        )
        job = (await session.execute(select(XJob))).scalar_one()
        usage = (await session.execute(select(XApiUsageDaily))).scalar_one()

    assert topic_count == 2
    assert snapshot_count == 2
    assert job.status == "succeeded"
    assert json.loads(job.result_json)["topic_count"] == 2
    assert usage.read_resource_count == 2


@pytest.mark.asyncio
async def test_repeated_search_updates_post_without_duplicate_rows(
    x_persistence_store,
    monkeypatch,
):
    _, factory = x_persistence_store
    monkeypatch.setattr(config, "CRAWLER_TYPE", "search")
    monkeypatch.setattr(config, "KEYWORDS", "MediaCrawler,MediaCrawler")
    monkeypatch.setattr(x_config, "X_READ_ENABLED", True)
    monkeypatch.setattr(x_config, "X_MAX_TOPICS_PER_CYCLE", 5)
    monkeypatch.delenv("X_CRAWLER_MODE", raising=False)
    monkeypatch.delenv("X_SEARCH_TOPIC", raising=False)
    now = [100_000]

    def clock_ms():
        now[0] += 1
        return now[0]

    first = await XBrowserCrawler(
        FakeXClient(),
        session_factory=factory,
        owner_user_id="owner-repeat",
        task_id="task-repeat",
        clock_ms=clock_ms,
    ).start()
    second = await XBrowserCrawler(
        FakeXClient(),
        session_factory=factory,
        owner_user_id="owner-repeat",
        task_id="task-repeat",
        clock_ms=clock_ms,
    ).start()

    assert first["topics"] == ["MediaCrawler"]
    assert second["persistence"][0]["inserted_post_count"] == 0
    assert second["persistence"][0]["updated_post_count"] == 1
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(XTopic)) == 1
        assert await session.scalar(select(func.count()).select_from(XPost)) == 1
        assert await session.scalar(select(func.count()).select_from(XTopicSnapshot)) == 2
        assert await session.scalar(select(func.count()).select_from(XJob)) == 2


@pytest.mark.asyncio
async def test_search_failure_is_recorded_on_x_job(
    x_persistence_store,
    monkeypatch,
):
    _, factory = x_persistence_store
    monkeypatch.setattr(config, "CRAWLER_TYPE", "search")
    monkeypatch.setattr(config, "KEYWORDS", "MediaCrawler")
    monkeypatch.setattr(x_config, "X_READ_ENABLED", True)
    monkeypatch.delenv("X_CRAWLER_MODE", raising=False)
    monkeypatch.delenv("X_SEARCH_TOPIC", raising=False)

    crawler = XBrowserCrawler(
        FakeXClient(fail_search=True),
        session_factory=factory,
        owner_user_id="owner-3",
        task_id="task-x-failed",
    )
    with pytest.raises(RuntimeError, match="browser search unavailable"):
        await crawler.start()

    async with factory() as session:
        job = (await session.execute(select(XJob))).scalar_one()
    assert job.status == "failed"
    assert job.lease_owner == ""
    assert "unavailable" in job.last_error


@pytest.mark.asyncio
async def test_crawl_limit_preflight_blocks_browser_call_and_marks_usage(
    x_persistence_store,
    monkeypatch,
):
    _, factory = x_persistence_store
    monkeypatch.setattr(config, "CRAWLER_TYPE", "search")
    monkeypatch.setattr(config, "KEYWORDS", "MediaCrawler")
    monkeypatch.setattr(x_config, "X_READ_ENABLED", True)
    monkeypatch.setattr(x_config, "X_DAILY_CRAWLED_POST_LIMIT", 1)
    monkeypatch.delenv("X_CRAWLER_MODE", raising=False)
    monkeypatch.delenv("X_SEARCH_TOPIC", raising=False)
    async with factory() as session:
        session.add(
            XApiUsageDaily(
                owner_user_id="owner-budget",
                account_id=0,
                usage_date="2026-07-16",
                endpoint="BROWSER /search?f=live",
                read_resource_count=1,
                created_at=1,
                updated_at=1,
            )
        )
        await session.commit()

    from media_platform.x import persistence as persistence_module

    monkeypatch.setattr(persistence_module, "utc_usage_date", lambda: "2026-07-16")
    client = FakeXClient()
    crawler = XBrowserCrawler(
        client,
        session_factory=factory,
        owner_user_id="owner-budget",
        task_id="task-budget",
    )
    with pytest.raises(XCrawlLimitExceeded):
        await crawler.start()

    assert client.search_calls == 0
    async with factory() as session:
        usage = (
            await session.execute(
                select(XApiUsageDaily).where(
                    XApiUsageDaily.owner_user_id == "owner-budget"
                )
            )
        ).scalar_one()
        job = (await session.execute(select(XJob))).scalar_one()
    assert usage.budget_exhausted is True
    assert job.status == "failed"
