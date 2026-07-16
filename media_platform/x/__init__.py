"""X platform integration based exclusively on the official X API.

Exports are lazy so importing ``media_platform.x.client`` from an API service
does not eagerly import the crawler facade back through that same service.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .client import XApiClient
    from .core import XOfficialApiCrawler

__all__ = ["XApiClient", "XOfficialApiCrawler"]


def __getattr__(name: str) -> Any:
    if name == "XApiClient":
        from .client import XApiClient

        return XApiClient
    if name == "XOfficialApiCrawler":
        from .core import XOfficialApiCrawler

        return XOfficialApiCrawler
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
