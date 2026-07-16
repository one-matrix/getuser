"""Browser-based X crawler facade used by tasks and scheduled workers."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional

import config
from api.services.x.collection_service import XCollectionService, XReadClient
from base.base_crawler import AbstractBrowserCrawler
from config import x_config

from .browser_client import XBrowserClient
from .browser_session import open_x_browser
from .persistence import (
    SessionFactory,
    XCollectionPersistence,
    default_session_factory,
    resolve_owner_user_id,
)

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext, BrowserType, Playwright
    from tools.cdp_browser import CDPBrowserManager
else:
    BrowserContext = BrowserType = Playwright = CDPBrowserManager = Any


class XBrowserCrawler(AbstractBrowserCrawler):
    """Collect X pages through a dedicated Chrome profile and CDP/Playwright."""

    def __init__(
        self,
        client: Optional[XReadClient] = None,
        *,
        session_factory: Optional[SessionFactory] = None,
        owner_user_id: str = "",
        task_id: str = "",
        clock_ms: Optional[Callable[[], int]] = None,
    ) -> None:
        self.client = client
        self.collection_service: Optional[XCollectionService] = (
            XCollectionService(client) if client is not None else None
        )
        self._session_factory = session_factory
        self._owner_user_id = owner_user_id
        self._task_id = task_id
        self._clock_ms = clock_ms
        self.cdp_manager: Optional[CDPBrowserManager] = None
        self.browser_context: Optional[BrowserContext] = None

    async def start(self) -> Dict[str, Any]:
        if self.client is not None:
            return await self._run(self.client)
        async with open_x_browser() as runtime:
            self.cdp_manager = runtime.cdp_manager
            self.browser_context = runtime.context
            client = XBrowserClient(runtime.page, cdp_url=runtime.cdp_url)
            return await self._run(client)

    async def _run(self, client: XReadClient) -> Dict[str, Any]:
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
                "read_source": "browser",
            },
        )
        self.client = client
        self.collection_service = XCollectionService(client)
        try:
            if not x_config.X_READ_ENABLED:
                raise PermissionError("X_READ_ENABLED is false")
            if crawler_type == "search":
                return await self._run_search(
                    persistence,
                    run,
                    woeid=woeid,
                )
            if crawler_type not in {"trending", "trend"}:
                raise ValueError("X supports CRAWLER_TYPE=trending or search")
            return await self._run_trends(
                persistence,
                run,
                woeid=woeid,
            )
        except Exception as exc:
            await persistence.mark_failed(run, exc)
            raise

    async def _run_search(
        self,
        persistence: XCollectionPersistence,
        run: Any,
        *,
        woeid: int,
    ) -> Dict[str, Any]:
        raw_topics = os.getenv("X_SEARCH_TOPIC", "").strip() or str(getattr(config, "KEYWORDS", ""))
        topics = list(
            dict.fromkeys(item.strip() for item in raw_topics.split(",") if item.strip())
        )[: max(int(x_config.X_MAX_TOPICS_PER_CYCLE), 1)]
        if not topics:
            raise ValueError("config.KEYWORDS or X_SEARCH_TOPIC is required for X search")
        results = []
        persistence_results = []
        endpoint = "BROWSER /search?f=live"
        for topic in topics:
            max_posts = max(int(x_config.X_MAX_POSTS_PER_TOPIC), 1)
            await persistence.preflight_crawl_limit(endpoint=endpoint, requested=max_posts)
            try:
                collected = await self.search(topic, max_posts=max_posts)
            except Exception:
                await persistence.record_usage(endpoint=endpoint, success=False)
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
            "read_source": "browser",
            "topics": topics,
            "results": results,
            "post_count": sum(len(item["posts"]) for item in results),
            "persistence": persistence_results,
            "x_job_id": run.job_id,
        }
        await persistence.mark_succeeded(
            run,
            {
                "mode": "search",
                "read_source": "browser",
                "topic_count": len(topics),
                "post_count": result["post_count"],
                "persistence": persistence_results,
            },
        )
        return result

    async def _run_trends(
        self,
        persistence: XCollectionPersistence,
        run: Any,
        *,
        woeid: int,
    ) -> Dict[str, Any]:
        max_trends = max(int(x_config.X_MAX_TOPICS_PER_CYCLE), 1)
        endpoint = "BROWSER /explore/tabs/trending"
        await persistence.preflight_crawl_limit(endpoint=endpoint, requested=max_trends)
        try:
            result = await self.collect_trends(
                woeid,
                region_name=x_config.X_DEFAULT_REGIONS[0]["region_name"],
                max_trends=max_trends,
            )
        except Exception:
            await persistence.record_usage(endpoint=endpoint, success=False)
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
        result.update(
            {
                "mode": "trending",
                "read_source": "browser",
                "persistence": stored,
                "x_job_id": run.job_id,
            }
        )
        await persistence.mark_succeeded(
            run,
            {
                "mode": "trending",
                "read_source": "browser",
                "woeid": woeid,
                **stored,
            },
        )
        return result

    async def search(
        self,
        topic: str,
        *,
        lang: Optional[str] = None,
        max_posts: int = 50,
    ) -> Dict[str, Any]:
        if self.collection_service is None:
            raise RuntimeError("X browser collection service is not initialized")
        return await self.collection_service.collect_topic_posts(
            topic=topic,
            lang=lang,
            max_posts=max_posts,
        )

    async def collect_trends(
        self,
        woeid: int,
        *,
        region_name: str = "",
        max_trends: int = 20,
    ) -> Dict[str, Any]:
        if self.collection_service is None:
            raise RuntimeError("X browser collection service is not initialized")
        result = await self.collection_service.collect_trends(
            woeid=woeid,
            region_name=region_name,
            max_trends=max_trends,
        )
        result["woeid"] = woeid
        return result

    async def collect_thread(self, root_post_id: str, *, max_posts: int = 50) -> Dict[str, Any]:
        if self.collection_service is None:
            raise RuntimeError("X browser collection service is not initialized")
        return await self.collection_service.collect_thread(
            root_post_id=root_post_id,
            max_posts=max_posts,
        )

    async def launch_browser(
        self,
        chromium: BrowserType,
        playwright_proxy: Optional[Dict],
        user_agent: Optional[str],
        headless: bool = True,
    ) -> BrowserContext:
        options: Dict[str, Any] = {
            "user_data_dir": x_config.X_BROWSER_USER_DATA_DIR
            or os.path.join(os.getcwd(), "browser_data", "x_user_data_dir"),
            "headless": headless,
            "viewport": {"width": 1440, "height": 1000},
            "proxy": playwright_proxy,
        }
        if user_agent:
            options["user_agent"] = user_agent
        return await chromium.launch_persistent_context(**options)

    async def launch_browser_with_cdp(
        self,
        playwright: Playwright,
        playwright_proxy: Optional[Dict],
        user_agent: Optional[str],
        headless: bool = True,
    ) -> BrowserContext:
        from tools.cdp_browser import CDPBrowserManager

        self.cdp_manager = CDPBrowserManager(
            user_data_dir_override=x_config.X_BROWSER_USER_DATA_DIR or None
        )
        return await self.cdp_manager.launch_and_connect(
            playwright=playwright,
            playwright_proxy=playwright_proxy,
            user_agent=user_agent,
            headless=headless,
        )
