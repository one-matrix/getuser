"""Official-API collection primitives independent from persistence."""

from __future__ import annotations

from typing import Any, Dict, Optional

from media_platform.x.client import XApiClient
from media_platform.x.field import included_users, map_post, map_trend


class XCollectionService:
    def __init__(self, client: XApiClient) -> None:
        self.client = client

    async def collect_trends(self, *, woeid: int, region_id: Any = None, max_trends: int = 20) -> Dict[str, Any]:
        payload = await self.client.get_trends(woeid, max_trends=max_trends)
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
            root_payload = await self.client.lookup_post(root_post_id)
        except Exception as exc:
            setattr(exc, "usage_endpoint", "GET /2/tweets/{id}")
            raise
        try:
            thread_payload = await self.client.collect_thread(root_post_id, max_total=max_posts)
        except Exception as exc:
            setattr(exc, "usage_endpoint", "GET /2/tweets/search/recent")
            raise
        users = included_users(thread_payload)
        users.update(included_users(root_payload))
        raw_posts = [root_payload.get("data")] if root_payload.get("data") else []
        raw_posts.extend(thread_payload.get("data") or [])
        deduped = {str(post.get("id")): post for post in raw_posts if post and post.get("id")}
        return {
            "root_post_id": root_post_id,
            "posts": [map_post(post, users_by_id=users) for post in deduped.values()],
            "meta": thread_payload.get("meta") or {},
        }
