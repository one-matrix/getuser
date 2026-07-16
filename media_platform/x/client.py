"""Official X API client restricted to controlled write operations.

All X reads are performed by :mod:`media_platform.x.browser_client`. Keeping
the write client separate makes accidental paid GET requests easy to detect in
review and tests.
"""

from __future__ import annotations

import inspect
import os
from typing import Any, Awaitable, Callable, Dict, Mapping, Optional

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


ResponseObserver = Callable[[Dict[str, Any]], Optional[Awaitable[None]]]


class XWriteApiClient:
    """Small user-context client that only permits official X write calls."""

    def __init__(
        self,
        *,
        user_access_token: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 30.0,
        http_client: Optional[httpx.AsyncClient] = None,
        response_observer: Optional[ResponseObserver] = None,
    ) -> None:
        self.user_access_token = (
            user_access_token
            or os.getenv("X_ACCESS_TOKEN", "")
            or os.getenv("X_USER_ACCESS_TOKEN", "")
        ).strip()
        configured_base = (
            base_url or os.getenv("X_WRITE_API_BASE_URL") or os.getenv("X_API_BASE_URL", "https://api.x.com")
        ).rstrip("/")
        self.base_url = configured_base if configured_base.endswith("/2") else f"{configured_base}/2"
        self.timeout = timeout
        self._client = http_client or httpx.AsyncClient(timeout=timeout)
        self._owns_client = http_client is None
        self.response_observer = response_observer

    async def __aenter__(self) -> "XWriteApiClient":
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

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
        json: Any = None,
        headers: Optional[Mapping[str, str]] = None,
    ) -> Dict[str, Any]:
        if method.upper() != "POST":
            raise XConfigurationError(
                "XWriteApiClient rejects read operations; use XBrowserClient",
                error_code="read_operation_disabled",
            )
        if not self.user_access_token:
            raise XConfigurationError(
                "X user access token is not configured",
                error_code="credentials_missing",
            )
        request_headers = {
            "Authorization": f"Bearer {self.user_access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "MediaCrawler-X-Controlled-Write/1.0",
        }
        if headers:
            request_headers.update(headers)

        url = path if path.startswith("http") else f"{self.base_url}/{path.lstrip('/')}"
        try:
            response = await self._client.request(
                "POST",
                url,
                json=json,
                headers=request_headers,
                timeout=self.timeout,
            )
        except httpx.TimeoutException as exc:
            raise XServerError(
                "X write request timed out",
                error_code="timeout",
                retryable=True,
            ) from exc
        except httpx.RequestError as exc:
            raise XServerError(
                f"X write network error: {exc}",
                error_code="network_error",
                retryable=True,
            ) from exc

        await self._observe(response, path, "POST")
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
