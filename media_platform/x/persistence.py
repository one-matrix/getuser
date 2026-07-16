"""Persistence adapter for browser-collected X results."""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, Mapping, Optional

import config
from api.services.x.usage_service import (
    configured_budgets,
    evaluate_budget,
    utc_usage_date,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from database.db_session import get_async_engine
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

from .field import normalize_topic_name


SessionFactory = Callable[[], AsyncSession]
POST_JSON_FIELDS = (
    "referenced_tweets_json",
    "public_metrics_json",
    "author_public_metrics_json",
    "entities_json",
    "raw_payload_json",
)


@dataclass(frozen=True)
class XInlineRun:
    row_id: int
    job_id: str
    job_type: str
    started_at: int


class XCrawlLimitExceeded(RuntimeError):
    """The tenant's configured daily browser collection limit is exhausted."""

    def __init__(self, budget: Mapping[str, Any]) -> None:
        super().__init__("X daily browser collection limit is exhausted")
        self.budget = dict(budget)


XReadBudgetExceeded = XCrawlLimitExceeded


class XCollectionPersistence:
    """Store normalized collection output and its durable XJob run record."""

    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        owner_user_id: str,
        task_id: str = "",
        clock_ms: Optional[Callable[[], int]] = None,
    ) -> None:
        self.session_factory = session_factory
        self.owner_user_id = str(owner_user_id or "")
        self.task_id = str(task_id or "")
        self.clock_ms = clock_ms or (lambda: int(time.time() * 1000))

    async def begin_run(self, job_type: str, payload: Mapping[str, Any]) -> XInlineRun:
        now_ms = self.clock_ms()
        job_id = f"xjob_{uuid.uuid4().hex}"
        row = XJob(
            owner_user_id=self.owner_user_id,
            job_id=job_id,
            job_type=job_type,
            parent_job_id="",
            dedup_key=f"{self.task_id}:{job_type}:{now_ms}",
            payload_json=_json_text({"task_id": self.task_id, **dict(payload)}),
            result_json="{}",
            status="running",
            priority=0,
            attempt_count=1,
            max_attempts=3,
            scheduled_at=now_ms,
            started_at=now_ms,
            finished_at=0,
            lease_owner=f"inline:{os.getpid()}",
            lease_expires_at=now_ms + 15 * 60 * 1000,
            last_error="",
            created_at=now_ms,
            updated_at=now_ms,
        )
        async with self.session_factory() as session:
            session.add(row)
            await session.commit()
            await session.refresh(row)
        return XInlineRun(row.id, job_id, job_type, now_ms)

    async def mark_succeeded(self, run: XInlineRun, result: Mapping[str, Any]) -> None:
        now_ms = self.clock_ms()
        async with self.session_factory() as session:
            row = await session.get(XJob, run.row_id)
            if row is None:
                return
            row.status = "succeeded"
            row.result_json = _json_text(result)
            row.last_error = ""
            row.finished_at = now_ms
            row.lease_owner = ""
            row.lease_expires_at = 0
            row.updated_at = now_ms
            await session.commit()

    async def mark_failed(self, run: XInlineRun, error: BaseException) -> None:
        now_ms = self.clock_ms()
        async with self.session_factory() as session:
            row = await session.get(XJob, run.row_id)
            if row is None:
                return
            row.status = "failed"
            row.last_error = _error_text(error)
            row.finished_at = now_ms
            row.lease_owner = ""
            row.lease_expires_at = 0
            row.updated_at = now_ms
            await session.commit()

    async def preflight_crawl_limit(
        self,
        *,
        endpoint: str,
        requested: int,
    ) -> Dict[str, Any]:
        usage_date = utc_usage_date()
        async with self.session_factory() as session:
            result = await session.execute(
                select(func.coalesce(func.sum(XApiUsageDaily.read_resource_count), 0)).where(
                    XApiUsageDaily.owner_user_id == self.owner_user_id,
                    XApiUsageDaily.usage_date == usage_date,
                )
            )
            used = int(result.scalar() or 0)
            status = evaluate_budget(
                used,
                configured_budgets()["post_reads"],
                requested=max(int(requested), 1),
            )
            if not status.allowed:
                item = await self._usage_row(session, endpoint=endpoint, usage_date=usage_date)
                item.budget_exhausted = True
                item.updated_at = self.clock_ms()
                await session.commit()
                raise XCrawlLimitExceeded(status.to_dict())
            return status.to_dict()

    async def preflight_read_budget(
        self,
        *,
        endpoint: str,
        requested: int,
    ) -> Dict[str, Any]:
        """Compatibility wrapper for callers using the previous API vocabulary."""

        return await self.preflight_crawl_limit(
            endpoint=endpoint,
            requested=requested,
        )

    async def record_usage(
        self,
        *,
        endpoint: str,
        success: bool,
        read_count: int = 0,
    ) -> None:
        usage_date = utc_usage_date()
        now_ms = self.clock_ms()
        async with self.session_factory() as session:
            item = await self._usage_row(session, endpoint=endpoint, usage_date=usage_date)
            item.request_count = int(item.request_count or 0) + 1
            item.success_count = int(item.success_count or 0) + int(success)
            item.error_count = int(item.error_count or 0) + int(not success)
            item.read_resource_count = int(item.read_resource_count or 0) + max(
                int(read_count),
                0,
            )
            await session.flush()
            total_result = await session.execute(
                select(func.coalesce(func.sum(XApiUsageDaily.read_resource_count), 0)).where(
                    XApiUsageDaily.owner_user_id == self.owner_user_id,
                    XApiUsageDaily.usage_date == usage_date,
                )
            )
            total_used = int(total_result.scalar() or 0)
            limit = configured_budgets()["post_reads"]
            item.budget_exhausted = bool(limit and total_used >= limit)
            item.updated_at = now_ms
            await session.commit()

    async def observe_response(self, event: Mapping[str, Any]) -> None:
        endpoint = _normalize_endpoint(
            str(event.get("method") or "GET"),
            str(event.get("endpoint") or ""),
        )
        now_ms = self.clock_ms()
        async with self.session_factory() as session:
            item = await self._rate_limit_row(session, endpoint=endpoint)
            item.limit_total = int(event.get("rate_limit_limit") or 0)
            item.remaining = int(event.get("rate_limit_remaining") or 0)
            item.reset_at = int(event.get("rate_limit_reset") or 0) * 1000
            item.last_http_status = int(event.get("status_code") or 0)
            item.observed_at = now_ms
            item.updated_at = now_ms
            await session.commit()

    async def record_rate_limit_error(
        self,
        *,
        endpoint: str,
        status_code: int,
        reset_at: Optional[int],
        headers: Mapping[str, Any],
    ) -> None:
        now_ms = self.clock_ms()
        async with self.session_factory() as session:
            item = await self._rate_limit_row(session, endpoint=endpoint)
            item.limit_total = _header_int(headers, "x-rate-limit-limit")
            item.remaining = _header_int(headers, "x-rate-limit-remaining")
            item.reset_at = int(reset_at or _header_int(headers, "x-rate-limit-reset")) * 1000
            item.last_http_status = int(status_code or 429)
            item.observed_at = now_ms
            item.updated_at = now_ms
            await session.commit()

    async def persist_trends(
        self,
        run: XInlineRun,
        *,
        woeid: int,
        topics: Iterable[Mapping[str, Any]],
    ) -> Dict[str, int]:
        captured_at = self.clock_ms()
        deduplicated: Dict[str, Dict[str, Any]] = {}
        for raw_item in topics:
            item = dict(raw_item)
            raw_name = str(item.get("name") or item.get("display_name") or "")
            normalized = str(item.get("normalized_name") or normalize_topic_name(raw_name))
            if normalized and normalized not in deduplicated:
                item["normalized_name"] = normalized
                deduplicated[normalized] = item
        items = list(deduplicated.values())
        async with self.session_factory() as session:
            region = await self._ensure_region(session, woeid, captured_at)
            created_topics = 0
            snapshots = 0
            for item in items:
                topic, created = await self._ensure_topic(
                    session,
                    region_id=region.id,
                    raw_name=str(item.get("name") or item.get("display_name") or ""),
                    normalized_name=str(item.get("normalized_name") or ""),
                    search_query="",
                    language=str(item.get("language") or region.language or ""),
                    status="monitoring",
                    seen_at=captured_at,
                )
                created_topics += int(created)
                session.add(
                    XTopicSnapshot(
                        owner_user_id=self.owner_user_id,
                        topic_id=topic.id,
                        region_id=region.id,
                        capture_batch_id=run.job_id,
                        rank=int(item.get("rank") or 0),
                        rank_delta=int(item.get("rank_delta") or 0),
                        post_volume=int(
                            item.get("discussion_count")
                            or item.get("tweet_count")
                            or item.get("post_volume")
                            or 0
                        ),
                        volume_delta=int(item.get("volume_delta") or 0),
                        post_count_estimate=int(
                            item.get("post_count_estimate")
                            or item.get("tweet_count")
                            or item.get("discussion_count")
                            or 0
                        ),
                        raw_payload_json=_json_text(item.get("raw_payload_json") or item),
                        captured_at=captured_at,
                        created_at=captured_at,
                        updated_at=captured_at,
                    )
                )
                snapshots += 1
            await session.commit()
        return {
            "region_id": region.id,
            "topic_count": len(items),
            "created_topic_count": created_topics,
            "snapshot_count": snapshots,
        }

    async def persist_search(
        self,
        run: XInlineRun,
        *,
        woeid: int,
        topic_name: str,
        query: str,
        posts: Iterable[Mapping[str, Any]],
        meta: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, int]:
        captured_at = self.clock_ms()
        post_items = [dict(item) for item in posts]
        async with self.session_factory() as session:
            region = await self._ensure_region(session, woeid, captured_at)
            topic, created_topic = await self._ensure_topic(
                session,
                region_id=region.id,
                raw_name=topic_name,
                normalized_name=normalize_topic_name(topic_name),
                search_query=query,
                language="",
                status="selected",
                seen_at=captured_at,
            )
            session.add(
                XTopicSnapshot(
                    owner_user_id=self.owner_user_id,
                    topic_id=topic.id,
                    region_id=region.id,
                    capture_batch_id=run.job_id,
                    rank=0,
                    rank_delta=0,
                    post_volume=len(post_items),
                    volume_delta=0,
                    post_count_estimate=int((meta or {}).get("result_count") or len(post_items)),
                    raw_payload_json=_json_text(
                        {
                            "topic": topic_name,
                            "query": query,
                            "meta": dict(meta or {}),
                        }
                    ),
                    captured_at=captured_at,
                    created_at=captured_at,
                    updated_at=captured_at,
                )
            )

            inserted_posts = 0
            updated_posts = 0
            skipped_posts = 0
            for item in post_items:
                inserted = await self._upsert_post(
                    session,
                    topic_id=topic.id,
                    query=query,
                    item=item,
                    now_ms=captured_at,
                )
                if inserted is True:
                    inserted_posts += 1
                elif inserted is False:
                    updated_posts += 1
                else:
                    skipped_posts += 1
            await session.commit()

        return {
            "region_id": region.id,
            "topic_id": topic.id,
            "created_topic_count": int(created_topic),
            "snapshot_count": 1,
            "inserted_post_count": inserted_posts,
            "updated_post_count": updated_posts,
            "skipped_post_count": skipped_posts,
            "post_count": len(post_items),
        }

    async def _ensure_region(
        self,
        session: AsyncSession,
        woeid: int,
        now_ms: int,
    ) -> XRegion:
        result = await session.execute(
            select(XRegion).where(
                XRegion.owner_user_id == self.owner_user_id,
                XRegion.woeid == str(woeid),
            )
        )
        row = result.scalars().first()
        defaults = _region_defaults(woeid)
        if row is None:
            row = XRegion(
                owner_user_id=self.owner_user_id,
                woeid=str(woeid),
                name=defaults["name"],
                country_code=defaults["country_code"],
                language=defaults["language"],
                timezone=defaults["timezone"],
                poll_interval_seconds=defaults["poll_interval_seconds"],
                daily_request_budget=0,
                enabled=True,
                last_polled_at=now_ms,
                next_poll_at=now_ms + defaults["poll_interval_seconds"] * 1000,
                last_error="",
                created_at=now_ms,
                updated_at=now_ms,
            )
            session.add(row)
            await session.flush()
            return row

        row.last_polled_at = now_ms
        row.next_poll_at = now_ms + max(int(row.poll_interval_seconds or 900), 60) * 1000
        row.last_error = ""
        row.updated_at = now_ms
        return row

    async def _usage_row(
        self,
        session: AsyncSession,
        *,
        endpoint: str,
        usage_date: str,
    ) -> XApiUsageDaily:
        result = await session.execute(
            select(XApiUsageDaily).where(
                XApiUsageDaily.owner_user_id == self.owner_user_id,
                XApiUsageDaily.account_id == 0,
                XApiUsageDaily.usage_date == usage_date,
                XApiUsageDaily.endpoint == endpoint,
            )
        )
        row = result.scalars().first()
        if row is None:
            now_ms = self.clock_ms()
            row = XApiUsageDaily(
                owner_user_id=self.owner_user_id,
                account_id=0,
                usage_date=usage_date,
                endpoint=endpoint,
                request_count=0,
                success_count=0,
                error_count=0,
                read_resource_count=0,
                write_count=0,
                estimated_cost_micros=0,
                budget_limit_micros=0,
                budget_exhausted=False,
                created_at=now_ms,
                updated_at=now_ms,
            )
            session.add(row)
            await session.flush()
        return row

    async def _rate_limit_row(
        self,
        session: AsyncSession,
        *,
        endpoint: str,
    ) -> XRateLimitState:
        result = await session.execute(
            select(XRateLimitState).where(
                XRateLimitState.owner_user_id == self.owner_user_id,
                XRateLimitState.account_id == 0,
                XRateLimitState.endpoint == endpoint,
                XRateLimitState.resource_key == "default",
            )
        )
        row = result.scalars().first()
        if row is None:
            now_ms = self.clock_ms()
            row = XRateLimitState(
                owner_user_id=self.owner_user_id,
                account_id=0,
                endpoint=endpoint,
                resource_key="default",
                limit_total=0,
                remaining=0,
                reset_at=0,
                last_http_status=0,
                observed_at=now_ms,
                created_at=now_ms,
                updated_at=now_ms,
            )
            session.add(row)
            await session.flush()
        return row

    async def _ensure_topic(
        self,
        session: AsyncSession,
        *,
        region_id: int,
        raw_name: str,
        normalized_name: str,
        search_query: str,
        language: str,
        status: str,
        seen_at: int,
    ) -> tuple[XTopic, bool]:
        normalized = normalized_name or normalize_topic_name(raw_name)
        result = await session.execute(
            select(XTopic).where(
                XTopic.owner_user_id == self.owner_user_id,
                XTopic.normalized_name == normalized,
                XTopic.region_id == region_id,
            )
        )
        row = result.scalars().first()
        if row is None:
            row = XTopic(
                owner_user_id=self.owner_user_id,
                region_id=region_id,
                raw_name=raw_name,
                normalized_name=normalized,
                search_query=search_query,
                language=language,
                category="general",
                relevance_score=0.0,
                risk_score=0.0,
                is_sensitive=False,
                status=status,
                first_seen_at=seen_at,
                last_seen_at=seen_at,
                created_at=seen_at,
                updated_at=seen_at,
            )
            session.add(row)
            await session.flush()
            return row, True

        row.raw_name = raw_name or row.raw_name
        row.search_query = search_query or row.search_query
        row.language = language or row.language
        row.status = status
        row.last_seen_at = seen_at
        row.updated_at = seen_at
        return row, False

    async def _upsert_post(
        self,
        session: AsyncSession,
        *,
        topic_id: int,
        query: str,
        item: Mapping[str, Any],
        now_ms: int,
    ) -> Optional[bool]:
        x_post_id = str(item.get("x_post_id") or "")
        if not x_post_id:
            return None
        result = await session.execute(
            select(XPost).where(
                XPost.owner_user_id == self.owner_user_id,
                XPost.x_post_id == x_post_id,
            )
        )
        row = result.scalars().first()
        values = _post_values(item, topic_id=topic_id, query=query, now_ms=now_ms)
        if row is None:
            session.add(
                XPost(
                    owner_user_id=self.owner_user_id,
                    x_post_id=x_post_id,
                    created_at=int(item.get("created_at") or now_ms),
                    **values,
                )
            )
            return True

        for key, value in values.items():
            setattr(row, key, value)
        row.updated_at = now_ms
        return False


async def resolve_owner_user_id(
    session_factory: SessionFactory,
    *,
    task_id: str,
    explicit_owner_user_id: str = "",
) -> str:
    explicit = str(explicit_owner_user_id or os.getenv("X_OWNER_USER_ID", "")).strip()
    if explicit:
        return explicit
    if not task_id:
        return ""
    async with session_factory() as session:
        result = await session.execute(
            select(CrawlerTaskModel.owner_user_id).where(CrawlerTaskModel.id == task_id)
        )
        return str(result.scalar_one_or_none() or "")


def default_session_factory() -> SessionFactory:
    engine = get_async_engine(config.SAVE_DATA_OPTION)
    if engine is None:
        raise RuntimeError("X collection persistence requires a database save option")
    return sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def _post_values(
    item: Mapping[str, Any],
    *,
    topic_id: int,
    query: str,
    now_ms: int,
) -> Dict[str, Any]:
    values = {
        "author_x_user_id": str(item.get("author_x_user_id") or ""),
        "author_username": str(item.get("author_username") or ""),
        "author_display_name": str(item.get("author_display_name") or ""),
        "text": str(item.get("text") or ""),
        "lang": str(item.get("lang") or ""),
        "created_at_x": int(item.get("created_at_x") or 0),
        "conversation_id": str(item.get("conversation_id") or ""),
        "parent_post_id": str(item.get("parent_post_id") or ""),
        "post_type": str(item.get("post_type") or "post"),
        "possibly_sensitive": bool(item.get("possibly_sensitive", False)),
        "reply_settings": str(item.get("reply_settings") or ""),
        "source_topic_id": topic_id,
        "source_query": query or str(item.get("source_query") or ""),
        "compliance_status": str(item.get("compliance_status") or "active"),
        "last_hydrated_at": int(item.get("last_hydrated_at") or now_ms),
        "updated_at": now_ms,
    }
    for field_name in POST_JSON_FIELDS:
        default = [] if field_name == "referenced_tweets_json" else {}
        values[field_name] = _json_text(item.get(field_name, default))
    return values


def _region_defaults(woeid: int) -> Dict[str, Any]:
    from config import x_config

    for item in x_config.X_DEFAULT_REGIONS:
        if str(item.get("woeid")) == str(woeid):
            return {
                "name": str(item.get("region_name") or item.get("name") or f"WOEID {woeid}"),
                "country_code": str(item.get("country_code") or ""),
                "language": str(item.get("language") or ""),
                "timezone": str(item.get("timezone") or "UTC"),
                "poll_interval_seconds": max(
                    int(item.get("poll_interval") or item.get("poll_interval_seconds") or 900),
                    60,
                ),
            }
    return {
        "name": f"WOEID {woeid}",
        "country_code": "",
        "language": "",
        "timezone": "UTC",
        "poll_interval_seconds": 900,
    }


def _json_text(value: Any) -> str:
    if isinstance(value, str):
        try:
            json.loads(value)
            return value
        except (TypeError, ValueError):
            return json.dumps(value, ensure_ascii=False)
    return json.dumps(
        value if value is not None else {},
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )


def _error_text(error: BaseException) -> str:
    return " ".join(str(error or "X collection failed").split())[:4000]


def _normalize_endpoint(method: str, endpoint: str) -> str:
    path = endpoint.split("?", 1)[0]
    if not path.startswith("/"):
        path = f"/{path}"
    if not path.startswith("/2/"):
        path = f"/2{path}"
    path = re.sub(r"/trends/by/woeid/\d+", "/trends/by/woeid/{woeid}", path)
    path = re.sub(r"/users/\d+/mentions", "/users/{id}/mentions", path)
    path = re.sub(r"/tweets/\d+", "/tweets/{id}", path)
    return f"{method.upper()} {path}"


def _header_int(headers: Mapping[str, Any], name: str) -> int:
    try:
        return int(headers.get(name) or 0)
    except (TypeError, ValueError):
        return 0
