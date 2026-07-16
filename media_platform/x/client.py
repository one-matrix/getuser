"""Async client for the official X API.

This module intentionally has no Playwright, cookie, CDP, proxy-pool, or browser
dependencies. Read endpoints use an app Bearer Token; write endpoints require a
separate user-context access token.
"""

from __future__ import annotations

import inspect
import os
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Mapping, Optional

import httpx

from .exception import (
    XApiError,
    XAuthenticationError,
    XConfigurationError,
    XForbiddenError,
    XNotFoundError,
    XRateLimitError,
    XServerError,
)
from .field import build_topic_query


DEFAULT_TWEET_FIELDS = ",".join(
    [
        "id",
        "text",
        "author_id",
        "created_at",
        "lang",
        "conversation_id",
        "public_metrics",
        "referenced_tweets",
        "possibly_sensitive",
        "reply_settings",
        "entities",
        "edit_history_tweet_ids",
    ]
)
DEFAULT_EXPANSIONS = "author_id,referenced_tweets.id,referenced_tweets.id.author_id"
DEFAULT_USER_FIELDS = "id,name,username,description,verified,public_metrics,protected"

ResponseObserver = Callable[[Dict[str, Any]], Optional[Awaitable[None]]]


class XApiClient:
    """Small, injectable X API v2 client with typed error mapping."""

    def __init__(
        self,
        *,
        bearer_token: Optional[str] = None,
        user_access_token: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 30.0,
        http_client: Optional[httpx.AsyncClient] = None,
        response_observer: Optional[ResponseObserver] = None,
    ) -> None:
        self.bearer_token = (bearer_token or os.getenv("X_BEARER_TOKEN", "")).strip()
        self.user_access_token = (
            user_access_token
            or os.getenv("X_ACCESS_TOKEN", "")
            or os.getenv("X_USER_ACCESS_TOKEN", "")
        ).strip()
        configured_base = base_url or os.getenv("X_API_BASE_URL", "https://api.x.com")
        configured_base = configured_base.rstrip("/")
        self.base_url = configured_base if configured_base.endswith("/2") else f"{configured_base}/2"
        self.timeout = timeout
        self._client = http_client or httpx.AsyncClient(timeout=timeout)
        self._owns_client = http_client is None
        self.response_observer = response_observer

    async def __aenter__(self) -> "XApiClient":
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _token(self, auth: str) -> str:
        if auth == "user":
            token = self.user_access_token
            label = "X user access token"
        else:
            token = self.bearer_token
            label = "X_BEARER_TOKEN"
        if not token:
            raise XConfigurationError(f"{label} is not configured", error_code="credentials_missing")
        return token

    async def _observe(self, response: httpx.Response, endpoint: str, method: str) -> None:
        if not self.response_observer:
            return
        event = {
            "endpoint": endpoint,
            "method": method.upper(),
            "status_code": response.status_code,
            "rate_limit_limit": _int_header(response.headers, "x-rate-limit-limit"),
            "rate_limit_remaining": _int_header(response.headers, "x-rate-limit-remaining"),
            "rate_limit_reset": _int_header(response.headers, "x-rate-limit-reset"),
        }
        result = self.response_observer(event)
        if inspect.isawaitable(result):
            await result

    async def request(
        self,
        method: str,
        path: str,
        *,
        auth: str = "app",
        params: Optional[Mapping[str, Any]] = None,
        json: Any = None,
        headers: Optional[Mapping[str, str]] = None,
    ) -> Dict[str, Any]:
        token = self._token(auth)
        request_headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "MediaCrawler-X-Official-API/1.0",
        }
        if json is not None:
            request_headers["Content-Type"] = "application/json"
        if headers:
            request_headers.update(headers)

        url = path if path.startswith("http") else f"{self.base_url}/{path.lstrip('/')}"
        try:
            response = await self._client.request(
                method,
                url,
                params=dict(params or {}),
                json=json,
                headers=request_headers,
                timeout=self.timeout,
            )
        except httpx.TimeoutException as exc:
            raise XServerError(
                "X API request timed out",
                error_code="timeout",
                retryable=True,
            ) from exc
        except httpx.RequestError as exc:
            raise XServerError(
                f"X API network error: {exc}",
                error_code="network_error",
                retryable=True,
            ) from exc

        await self._observe(response, path, method)
        try:
            payload: Any = response.json()
        except ValueError:
            payload = {"detail": response.text[:500]}

        if 200 <= response.status_code < 300:
            return payload if isinstance(payload, dict) else {"data": payload}

        message, error_code = _extract_error(payload, response.status_code)
        kwargs = {
            "status_code": response.status_code,
            "error_code": error_code,
            "payload": payload,
        }
        if response.status_code == 401:
            raise XAuthenticationError(message, **kwargs)
        if response.status_code == 403:
            raise XForbiddenError(message, **kwargs)
        if response.status_code == 404:
            raise XNotFoundError(message, **kwargs)
        if response.status_code == 429:
            raise XRateLimitError(
                message,
                reset_at=_int_header(response.headers, "x-rate-limit-reset"),
                headers=response.headers,
                **kwargs,
            )
        if response.status_code >= 500:
            raise XServerError(message, retryable=True, **kwargs)
        raise XApiError(message, **kwargs)

    async def get_trends(self, woeid: int, *, max_trends: int = 20) -> Dict[str, Any]:
        return await self.request(
            "GET",
            f"/trends/by/woeid/{int(woeid)}",
            params={
                "max_trends": min(max(int(max_trends), 1), 50),
                "trend.fields": "trend_name,tweet_count",
            },
        )

    async def recent_search(
        self,
        query: str,
        *,
        max_total: int = 50,
        since_id: str = "",
        sort_order: str = "relevancy",
    ) -> Dict[str, Any]:
        if not query or len(query) > 512:
            raise ValueError("recent-search query must contain 1-512 characters")
        max_total = min(max(int(max_total), 1), 500)
        remaining = max_total
        next_token = ""
        combined_data: List[Dict[str, Any]] = []
        combined_users: Dict[str, Dict[str, Any]] = {}
        last_meta: Dict[str, Any] = {}

        while remaining > 0:
            per_page = min(max(remaining, 10), 100)
            params: Dict[str, Any] = {
                "query": query,
                "max_results": per_page,
                "sort_order": sort_order if sort_order in {"recency", "relevancy"} else "relevancy",
                "tweet.fields": DEFAULT_TWEET_FIELDS,
                "expansions": DEFAULT_EXPANSIONS,
                "user.fields": DEFAULT_USER_FIELDS,
            }
            if since_id:
                params["since_id"] = since_id
            if next_token:
                params["next_token"] = next_token
            payload = await self.request("GET", "/tweets/search/recent", params=params)
            page_data = list(payload.get("data") or [])
            combined_data.extend(page_data[:remaining])
            for user in (payload.get("includes") or {}).get("users") or []:
                if user.get("id"):
                    combined_users[str(user["id"])] = user
            last_meta = dict(payload.get("meta") or {})
            remaining = max_total - len(combined_data)
            next_token = str(last_meta.get("next_token") or "")
            if not next_token or not page_data:
                break

        return {
            "data": combined_data[:max_total],
            "includes": {"users": list(combined_users.values())},
            "meta": {
                **last_meta,
                "result_count": len(combined_data[:max_total]),
                "truncated_by_client": bool(next_token and len(combined_data) >= max_total),
            },
        }

    async def search_topic(
        self,
        topic: str,
        *,
        lang: Optional[str] = None,
        max_total: int = 50,
    ) -> Dict[str, Any]:
        query = build_topic_query(topic, lang=lang)
        payload = await self.recent_search(query, max_total=max_total)
        payload["query"] = query
        return payload

    async def recent_counts(
        self,
        query: str,
        *,
        granularity: str = "hour",
    ) -> Dict[str, Any]:
        if not query or len(query) > 512:
            raise ValueError("counts query must contain 1-512 characters")
        if granularity not in {"minute", "hour", "day"}:
            raise ValueError("granularity must be minute, hour, or day")
        return await self.request(
            "GET",
            "/tweets/counts/recent",
            params={"query": query, "granularity": granularity},
        )

    async def lookup_post(self, post_id: str) -> Dict[str, Any]:
        if not str(post_id).isdigit():
            raise ValueError("post_id must be a numeric X Post ID")
        return await self.request(
            "GET",
            f"/tweets/{post_id}",
            params={
                "tweet.fields": DEFAULT_TWEET_FIELDS,
                "expansions": DEFAULT_EXPANSIONS,
                "user.fields": DEFAULT_USER_FIELDS,
            },
        )

    async def get_mentions(
        self,
        user_id: str,
        *,
        since_id: str = "",
        max_total: int = 50,
        user_context: bool = True,
    ) -> Dict[str, Any]:
        if not str(user_id).isdigit():
            raise ValueError("user_id must be a numeric X User ID")
        params: Dict[str, Any] = {
            "max_results": min(max(max_total, 5), 100),
            "tweet.fields": DEFAULT_TWEET_FIELDS,
            "expansions": DEFAULT_EXPANSIONS,
            "user.fields": DEFAULT_USER_FIELDS,
        }
        if since_id:
            params["since_id"] = since_id
        return await self.request(
            "GET",
            f"/users/{user_id}/mentions",
            auth="user" if user_context else "app",
            params=params,
        )

    async def get_me(self) -> Dict[str, Any]:
        return await self.request(
            "GET",
            "/users/me",
            auth="user",
            params={
                "user.fields": "id,name,username,description,verified,public_metrics,protected",
            },
        )

    async def collect_thread(self, root_post_id: str, *, max_total: int = 50) -> Dict[str, Any]:
        return await self.recent_search(
            f"conversation_id:{root_post_id} -is:retweet",
            max_total=max_total,
            sort_order="relevancy",
        )

    async def create_reply(
        self,
        *,
        text: str,
        target_post_id: str,
        idempotency_key: str = "",
    ) -> Dict[str, Any]:
        if not text.strip():
            raise ValueError("reply text cannot be empty")
        if len(text) > 280:
            raise ValueError("reply text exceeds 280 characters")
        if not str(target_post_id).isdigit():
            raise ValueError("target_post_id must be a numeric X Post ID")
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        return await self.request(
            "POST",
            "/tweets",
            auth="user",
            json={
                "text": text,
                "reply": {"in_reply_to_tweet_id": str(target_post_id)},
            },
            headers=headers,
        )


def _extract_error(payload: Any, status_code: int) -> tuple[str, str]:
    if isinstance(payload, dict):
        errors = payload.get("errors") or []
        if errors and isinstance(errors[0], dict):
            first = errors[0]
            return (
                str(first.get("detail") or first.get("title") or f"X API returned {status_code}"),
                str(first.get("code") or first.get("type") or status_code),
            )
        return (
            str(payload.get("detail") or payload.get("title") or f"X API returned {status_code}"),
            str(payload.get("code") or payload.get("type") or status_code),
        )
    return f"X API returned {status_code}", str(status_code)


def _int_header(headers: Mapping[str, str], name: str) -> Optional[int]:
    try:
        value = headers.get(name)
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
