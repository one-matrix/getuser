"""Exceptions raised by the X browser reader and official write client."""

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


class XBrowserError(RuntimeError):
    """Base error for deterministic browser collection failures."""

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "browser_error",
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.retryable = retryable


class XBrowserLoginRequired(XBrowserError):
    """The configured browser profile is not logged in to X."""

    def __init__(self, message: str = "X browser session requires login") -> None:
        super().__init__(message, error_code="login_required", retryable=False)


class XBrowserChallengeRequired(XBrowserError):
    """X displayed a CAPTCHA, checkpoint, or account access challenge."""

    def __init__(self, message: str = "X requires a manual browser challenge") -> None:
        super().__init__(message, error_code="challenge_required", retryable=False)


class XBrowserStructureChanged(XBrowserError):
    """The page loaded, but expected public content could not be extracted."""

    def __init__(self, message: str = "X page structure could not be parsed") -> None:
        super().__init__(message, error_code="structure_changed", retryable=True)
