"""Exceptions raised by the official X API client."""

from __future__ import annotations

from typing import Any, Mapping, Optional


class XApiError(RuntimeError):
    """Base error with enough context for API and worker error handling."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 0,
        error_code: str = "",
        payload: Any = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.payload = payload
        self.retryable = retryable


class XConfigurationError(XApiError):
    """Required X credentials or configuration are missing."""


class XAuthenticationError(XApiError):
    """The supplied application or user token was rejected."""


class XForbiddenError(XApiError):
    """The token is valid but cannot perform the requested operation."""


class XNotFoundError(XApiError):
    """The requested X resource no longer exists or is unavailable."""


class XRateLimitError(XApiError):
    """X rejected a request because the endpoint rate limit was exhausted."""

    def __init__(
        self,
        message: str,
        *,
        reset_at: Optional[int] = None,
        headers: Optional[Mapping[str, str]] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(message, retryable=True, **kwargs)
        self.reset_at = reset_at
        self.headers = dict(headers or {})


class XServerError(XApiError):
    """A retryable X or upstream service failure."""

