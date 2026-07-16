"""No-browser X crawler facade used by workers and command integration."""

from __future__ import annotations

import inspect
import os
from typing import Any, Callable, Dict, Optional

import config
from api.services.x.collection_service import XCollectionService
from base.base_crawler import AbstractCrawler

from .client import XApiClient
from .exception import XRateLimitError
from .persistence import (
    SessionFactory,
    XCollectionPersistence,
    default_session_factory,
    resolve_owner_user_id,
)


class XOfficialApiCrawler(AbstractCrawler):
    """Official-API crawler that implements the browser-free crawler contract."""

    def __init__(
        self,
        client: Optional[XApiClient] = None,
        *,
        session_factory: Optional[SessionFactory] = None,
        owner_user_id: str = "",
        task_id: str = "",
        clock_ms: Optional[Callable[[], int]] = None,
    ) -> None:
        self.client = client or XApiClient()
        self._owns_client = client is None
        self.collection_service = XCollectionService(self.client)
        self._session_factory = session_factory
        self._owner_user_id = owner_user_id
        self._task_id = task_id
        self._clock_ms = clock_ms

    async def start(self) -> Dict[str, Any]:
        from config import x_config

        mode = os.getenv("X_CRAWLER_MODE", "").strip().lower()
        crawler_type = mode or str(getattr(config, "CRAWLER_TYPE", "trending")).strip().lower()
        try:
            woeid = int(os.getenv("X_DEFAULT_WOEID", str(x_config.X_DEFAULT_WOEID)))
        except (TypeError, ValueError):
            woeid = int(x_config.X_DEFAULT_WOEID)
        task_id = self._task_id
        if not task_id:
            from var import task_id_var

            task_id = task_id_var.get()
        session_factory = self._session_factory or default_session_factory()
        owner_user_id = await resolve_owner_user_id(
            session_factory,
            task_id=task_id,
            explicit_owner_user_id=self._owner_user_id,
        )
        persistence = XCollectionPersistence(
            session_factory,
            owner_user_id=owner_user_id,
            task_id=task_id,
            clock_ms=self._clock_ms,
        )
        run = await persistence.begin_run(
            "search" if crawler_type == "search" else "trends",
            {
                "crawler_type": crawler_type,
                "keywords": str(getattr(config, "KEYWORDS", "")),
                "woeid": woeid,
            },
        )
        previous_response_observer = getattr(self.client, "response_observer", None)
        has_response_observer = hasattr(self.client, "response_observer")
        if has_response_observer:
            async def observe_response(event):
                if previous_response_observer:
                    observed = previous_response_observer(event)
                    if inspect.isawaitable(observed):
                        await observed
                await persistence.observe_response(event)

            self.client.response_observer = observe_response
        try:
            if not x_config.X_READ_ENABLED:
                raise PermissionError("X_READ_ENABLED is false")
            if crawler_type == "search":
                raw_topics = os.getenv("X_SEARCH_TOPIC", "").strip() or str(getattr(config, "KEYWORDS", ""))
                topics = list(
                    dict.fromkeys(
                        item.strip()
                        for item in raw_topics.split(",")
                        if item.strip()
                    )
                )[: max(int(x_config.X_MAX_TOPICS_PER_CYCLE), 1)]
                if not topics:
                    raise ValueError("config.KEYWORDS or X_SEARCH_TOPIC is required for X search")
                results = []
                persistence_results = []
                endpoint = "GET /2/tweets/search/recent"
                for topic in topics:
                    max_posts = max(int(x_config.X_MAX_POSTS_PER_TOPIC), 1)
                    await persistence.preflight_read_budget(
                        endpoint=endpoint,
                        requested=max_posts,
                    )
                    try:
                        collected = await self.search(
                            topic,
                            max_posts=max_posts,
                        )
                    except Exception as exc:
                        await _record_collection_error(
                            persistence,
                            endpoint=endpoint,
                            error=exc,
                        )
                        raise
                    await persistence.record_usage(
                        endpoint=endpoint,
                        success=True,
                        read_count=len(collected.get("posts") or []),
                    )
                    stored = await persistence.persist_search(
                        run,
                        woeid=woeid,
                        topic_name=topic,
                        query=str(collected.get("query") or ""),
                        posts=collected.get("posts") or [],
                        meta=collected.get("meta") or {},
                    )
                    results.append(collected)
                    persistence_results.append(stored)
                result = {
                    "mode": "search",
                    "topics": topics,
                    "results": results,
                    "post_count": sum(len(result["posts"]) for result in results),
                    "persistence": persistence_results,
                    "x_job_id": run.job_id,
                }
                await persistence.mark_succeeded(
                    run,
                    {
                        "mode": "search",
                        "topic_count": len(topics),
                        "post_count": result["post_count"],
                        "persistence": persistence_results,
                    },
                )
                return result
            if crawler_type not in {"trending", "trend"}:
                raise ValueError("X supports CRAWLER_TYPE=trending or search")
            max_trends = max(int(x_config.X_MAX_TOPICS_PER_CYCLE), 1)
            endpoint = "GET /2/trends/by/woeid/{woeid}"
            await persistence.preflight_read_budget(
                endpoint=endpoint,
                requested=max_trends,
            )
            try:
                result = await self.collect_trends(
                    woeid,
                    max_trends=max_trends,
                )
            except Exception as exc:
                await _record_collection_error(
                    persistence,
                    endpoint=endpoint,
                    error=exc,
                )
                raise
            await persistence.record_usage(
                endpoint=endpoint,
                success=True,
                read_count=len(result.get("topics") or []),
            )
            stored = await persistence.persist_trends(
                run,
                woeid=woeid,
                topics=result.get("topics") or [],
            )
            result["mode"] = "trending"
            result["persistence"] = stored
            result["x_job_id"] = run.job_id
            await persistence.mark_succeeded(
                run,
                {
                    "mode": "trending",
                    "woeid": woeid,
                    **stored,
                },
            )
            return result
        except Exception as exc:
            await persistence.mark_failed(run, exc)
            raise
        finally:
            if has_response_observer:
                self.client.response_observer = previous_response_observer
            if self._owns_client:
                await self.client.aclose()

    async def search(
        self,
        topic: str,
        *,
        lang: Optional[str] = None,
        max_posts: int = 50,
    ) -> Dict[str, Any]:
        return await self.collection_service.collect_topic_posts(
            topic=topic,
            lang=lang,
            max_posts=max_posts,
        )

    async def collect_trends(self, woeid: int, *, max_trends: int = 20) -> Dict[str, Any]:
        result = await self.collection_service.collect_trends(
            woeid=woeid,
            max_trends=max_trends,
        )
        result["woeid"] = woeid
        return result

    async def collect_thread(self, root_post_id: str, *, max_posts: int = 50) -> Dict[str, Any]:
        return await self.collection_service.collect_thread(
            root_post_id=root_post_id,
            max_posts=max_posts,
        )


async def _record_collection_error(
    persistence: XCollectionPersistence,
    *,
    endpoint: str,
    error: Exception,
) -> None:
    await persistence.record_usage(
        endpoint=endpoint,
        success=False,
    )
    if isinstance(error, XRateLimitError):
        await persistence.record_rate_limit_error(
            endpoint=endpoint,
            status_code=error.status_code or 429,
            reset_at=error.reset_at,
            headers=error.headers,
        )
