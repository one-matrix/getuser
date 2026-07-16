"""Bounded X browser sessions shared by crawler and operations API."""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, AsyncIterator, Optional

import config
from config import x_config

from .exception import XBrowserError

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext, Page, Playwright
    from tools.cdp_browser import CDPBrowserManager
else:
    BrowserContext = Page = Playwright = CDPBrowserManager = Any


_BROWSER_LOCK = asyncio.Lock()


@dataclass
class XBrowserRuntime:
    page: Page
    context: BrowserContext
    cdp_url: str = ""
    cdp_manager: Optional[CDPBrowserManager] = None


def _profile_dir() -> str:
    configured = x_config.X_BROWSER_USER_DATA_DIR.strip()
    if configured:
        return os.path.abspath(os.path.expanduser(configured))
    return os.path.join(os.getcwd(), "browser_data", "x_user_data_dir")


@asynccontextmanager
async def open_x_browser() -> AsyncIterator[XBrowserRuntime]:
    """Open one X tab while preventing concurrent control of the same profile."""

    try:
        await asyncio.wait_for(
            _BROWSER_LOCK.acquire(),
            timeout=x_config.X_BROWSER_LOCK_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError as exc:
        raise XBrowserError(
            "X browser is busy; retry after the current collection finishes",
            error_code="browser_busy",
            retryable=True,
        ) from exc

    playwright: Optional[Playwright] = None
    context: Optional[BrowserContext] = None
    page: Optional[Page] = None
    manager: Optional[CDPBrowserManager] = None
    cdp_url = ""
    owns_context = False
    try:
        os.makedirs(_profile_dir(), exist_ok=True)
        try:
            from playwright.async_api import async_playwright
            from tools.cdp_browser import CDPBrowserManager
        except ModuleNotFoundError as exc:
            raise XBrowserError(
                "Playwright is not installed; install the main project dependencies before X browser collection",
                error_code="playwright_missing",
                retryable=False,
            ) from exc

        playwright = await async_playwright().start()
        if x_config.X_BROWSER_USE_CDP:
            manager = CDPBrowserManager(user_data_dir_override=_profile_dir())
            context = await manager.launch_and_connect(
                playwright=playwright,
                playwright_proxy=None,
                user_agent=x_config.X_BROWSER_USER_AGENT or None,
                headless=x_config.X_BROWSER_HEADLESS,
            )
            if manager.debug_port:
                cdp_url = f"http://127.0.0.1:{manager.debug_port}"
        else:
            launch_options = {
                "user_data_dir": _profile_dir(),
                "headless": x_config.X_BROWSER_HEADLESS,
                "viewport": {"width": 1440, "height": 1000},
                "locale": x_config.X_BROWSER_LOCALE,
            }
            if x_config.X_BROWSER_USER_AGENT:
                launch_options["user_agent"] = x_config.X_BROWSER_USER_AGENT
            if config.CUSTOM_BROWSER_PATH and os.path.exists(config.CUSTOM_BROWSER_PATH):
                launch_options["executable_path"] = config.CUSTOM_BROWSER_PATH
            else:
                launch_options["channel"] = "chrome"
            context = await playwright.chromium.launch_persistent_context(**launch_options)
            owns_context = True

        page = await context.new_page()
        page.set_default_timeout(x_config.X_BROWSER_OPERATION_TIMEOUT_SECONDS * 1000)
        yield XBrowserRuntime(
            page=page,
            context=context,
            cdp_url=cdp_url,
            cdp_manager=manager,
        )
    finally:
        if page is not None:
            try:
                await page.close()
            except Exception:
                pass
        if manager is not None and not config.CDP_CONNECT_EXISTING:
            await manager.cleanup()
        elif owns_context and context is not None:
            try:
                await context.close()
            except Exception:
                pass
        elif manager is not None:
            # Do not close a user-owned Chrome context connected through CDP.
            manager.browser_context = None
            manager.browser = None
        if playwright is not None:
            try:
                await playwright.stop()
            except Exception:
                pass
        _BROWSER_LOCK.release()
