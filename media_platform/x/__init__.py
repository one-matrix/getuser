"""X platform integration with browser reads and controlled official writes.

Exports are lazy so importing ``media_platform.x.client`` from an API service
does not eagerly import the crawler facade back through that same service.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .browser_client import XBrowserClient
    from .client import XWriteApiClient
    from .core import XBrowserCrawler

__all__ = ["XBrowserClient", "XWriteApiClient", "XBrowserCrawler"]


def __getattr__(name: str) -> Any:
    if name == "XBrowserClient":
        from .browser_client import XBrowserClient

        return XBrowserClient
    if name == "XWriteApiClient":
        from .client import XWriteApiClient

        return XWriteApiClient
    if name == "XBrowserCrawler":
        from .core import XBrowserCrawler

        return XBrowserCrawler
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
