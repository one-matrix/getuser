"""Browser collection primitives independent from persistence."""

from __future__ import annotations

from typing import Any, Dict, Optional, Protocol

from media_platform.x.field import included_users, map_post, map_trend


class XReadClient(Protocol):
    async def get_trends(
        self,
        woeid: int,
        *,
        max_trends: int = 20,
        region_name: str = "",
    ) -> Dict[str, Any]: ...

    async def search_topic(
        self,
        topic: str,
        *,
        lang: Optional[str] = None,
        max_total: int = 50,
    ) -> Dict[str, Any]: ...

    async def collect_thread(
        self,
        root_post_id: str,
        *,
        max_total: int = 50,
    ) -> Dict[str, Any]: ...


class XCollectionService:
    def __init__(self, client: XReadClient) -> None:
        self.client = client

    async def collect_trends(
        self,
        *,
        woeid: int,
        region_id: Any = None,
        region_name: str = "",
        max_trends: int = 20,
    ) -> Dict[str, Any]:
        payload = await self.client.get_trends(
            woeid,
            max_trends=max_trends,
            region_name=region_name,
        )
        return {
            "topics": [
                map_trend(item, rank=index + 1, region_id=region_id)
                for index, item in enumerate(payload.get("data") or [])
            ],
            "errors": payload.get("errors") or [],
        }

    async def collect_topic_posts(
        self,
        *,
        topic: str,
        topic_id: Any = None,
        lang: Optional[str] = None,
        max_posts: int = 50,
    ) -> Dict[str, Any]:
        payload = await self.client.search_topic(topic, lang=lang, max_total=max_posts)
        users = included_users(payload)
        query = str(payload.get("query") or "")
        return {
            "query": query,
            "posts": [
                map_post(post, users_by_id=users, source_topic_id=topic_id, source_query=query)
                for post in payload.get("data") or []
            ],
            "meta": payload.get("meta") or {},
        }

    async def collect_thread(self, *, root_post_id: str, max_posts: int = 50) -> Dict[str, Any]:
        try:
            thread_payload = await self.client.collect_thread(root_post_id, max_total=max_posts)
        except Exception as exc:
            setattr(exc, "usage_endpoint", "BROWSER /i/web/status/{id}")
            raise
        users = included_users(thread_payload)
        raw_posts = list(thread_payload.get("data") or [])
        deduped = {str(post.get("id")): post for post in raw_posts if post and post.get("id")}
        return {
            "root_post_id": root_post_id,
            "posts": [map_post(post, users_by_id=users) for post in deduped.values()],
            "meta": thread_payload.get("meta") or {},
        }
