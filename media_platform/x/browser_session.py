"""Bounded X browser sessions shared by crawler and operations API."""

from __future__ import annotations

import asyncio
import os
import socket
import subprocess
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
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
_CDP_PORT_MARKER = ".mediacrawler-cdp-port"


@dataclass
class XBrowserRuntime:
    page: Page
    context: BrowserContext
    cdp_url: str = ""
    cdp_manager: Optional[CDPBrowserManager] = None


def x_browser_profile_dir() -> str:
    configured = x_config.X_BROWSER_USER_DATA_DIR.strip()
    if configured:
        return os.path.abspath(os.path.expanduser(configured))
    return os.path.join(os.getcwd(), "browser_data", "x_user_data_dir")


def x_browser_profile_status() -> dict[str, Any]:
    """Return non-secret diagnostics for the dedicated X browser profile."""

    profile_dir = Path(x_browser_profile_dir())
    cookie_candidates = [
        profile_dir / "Default" / "Cookies",
        profile_dir / "Default" / "Network" / "Cookies",
    ]
    if profile_dir.exists():
        cookie_candidates.extend(profile_dir.glob("Profile */Cookies"))
        cookie_candidates.extend(profile_dir.glob("Profile */Network/Cookies"))
    lock_status = _profile_lock_status(profile_dir)
    active_debug_port = _profile_cdp_port(profile_dir)
    return {
        "profile_source": (
            "configured" if x_config.X_BROWSER_USER_DATA_DIR.strip() else "project_default"
        ),
        "profile_dir": str(profile_dir),
        "profile_exists": profile_dir.is_dir(),
        "cookie_store_detected": any(path.is_file() for path in cookie_candidates),
        **lock_status,
        "cdp_mode": bool(x_config.X_BROWSER_USE_CDP),
        "cdp_ready": active_debug_port is not None,
        "connect_existing": bool(active_debug_port or config.CDP_CONNECT_EXISTING),
        "debug_port": int(active_debug_port or config.CDP_DEBUG_PORT),
        "headless": bool(x_config.X_BROWSER_HEADLESS),
        "browser_use_fallback_enabled": bool(
            x_config.X_BROWSER_USE_FALLBACK_ENABLED
            and x_config.X_BROWSER_USE_FALLBACK_COMMAND
        ),
    }


def _profile_lock_status(profile_dir: Path) -> dict[str, bool]:
    lock_path = profile_dir / "SingletonLock"
    lock_detected = any(
        os.path.lexists(profile_dir / name)
        for name in ("SingletonLock", "SingletonSocket", "SingletonCookie")
    )
    profile_in_use = False
    if os.path.lexists(lock_path):
        try:
            target = os.readlink(lock_path)
            pid_text = target.rsplit("-", 1)[-1]
            pid = int(pid_text)
            os.kill(pid, 0)
            profile_in_use = True
        except (OSError, TypeError, ValueError):
            profile_in_use = False
    return {
        "profile_lock_detected": lock_detected,
        "profile_in_use": profile_in_use,
    }


def _profile_cdp_port(profile_dir: Path) -> Optional[int]:
    """Return the live CDP port written by Chrome for this exact profile."""

    candidates: list[int] = []
    for port_file in (
        profile_dir / "DevToolsActivePort",
        profile_dir / _CDP_PORT_MARKER,
    ):
        try:
            port = int(port_file.read_text(encoding="utf-8").splitlines()[0].strip())
        except (OSError, ValueError, IndexError):
            continue
        if 0 < port <= 65535 and port not in candidates:
            candidates.append(port)
    if int(config.CDP_DEBUG_PORT) not in candidates:
        candidates.append(int(config.CDP_DEBUG_PORT))

    for port in candidates:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return port
        except OSError:
            continue
    return None


async def _wait_for_profile_cdp_port(
    profile_dir: Path,
    *,
    timeout_seconds: float = 5.0,
) -> Optional[int]:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while True:
        port = _profile_cdp_port(profile_dir)
        if port is not None:
            return port
        if asyncio.get_running_loop().time() >= deadline:
            return None
        await asyncio.sleep(0.1)


def open_x_login_window() -> dict[str, Any]:
    """Open the dedicated profile with local CDP for login and later reuse."""

    from tools.browser_launcher import BrowserLauncher

    profile_dir = x_browser_profile_dir()
    os.makedirs(profile_dir, exist_ok=True)
    profile_path = Path(profile_dir)
    profile_status = _profile_lock_status(profile_path)
    active_debug_port = _profile_cdp_port(profile_path)
    if profile_status["profile_in_use"]:
        if active_debug_port is not None:
            return {
                "pid": 0,
                "profile_dir": profile_dir,
                "browser_name": "Google Chrome",
                "url": f"{x_config.X_BROWSER_BASE_URL}/home",
                "debug_port": active_debug_port,
                "cdp_ready": True,
                "already_running": True,
            }
        raise XBrowserError(
            "专用 X Profile 已被未开启 CDP 的浏览器占用；请关闭该窗口后重新点击打开",
            error_code="browser_profile_in_use_without_cdp",
            retryable=True,
        )

    launcher = BrowserLauncher()
    browser_path = ""
    if config.CUSTOM_BROWSER_PATH and os.path.isfile(config.CUSTOM_BROWSER_PATH):
        browser_path = config.CUSTOM_BROWSER_PATH
    else:
        detected = launcher.detect_browser_paths()
        if detected:
            browser_path = detected[0]
    if not browser_path:
        raise XBrowserError(
            "No Chrome or Edge browser was found for the X login profile",
            error_code="browser_missing",
            retryable=False,
        )

    launcher._cleanup_singleton_locks(profile_dir)
    url = f"{x_config.X_BROWSER_BASE_URL}/home"
    debug_port = launcher.find_available_port(config.CDP_DEBUG_PORT)
    (profile_path / _CDP_PORT_MARKER).write_text(str(debug_port), encoding="utf-8")
    process = subprocess.Popen(
        [
            browser_path,
            f"--user-data-dir={profile_dir}",
            f"--remote-debugging-port={debug_port}",
            "--remote-debugging-address=127.0.0.1",
            "--no-first-run",
            "--no-default-browser-check",
            "--new-window",
            url,
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return {
        "pid": process.pid,
        "profile_dir": profile_dir,
        "browser_name": os.path.basename(browser_path),
        "url": url,
        "debug_port": debug_port,
        "cdp_ready": False,
        "already_running": False,
    }


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
        profile_dir = Path(x_browser_profile_dir())
        os.makedirs(profile_dir, exist_ok=True)
        profile_status = _profile_lock_status(profile_dir)
        attach_debug_port: Optional[int] = None
        if profile_status["profile_in_use"] and x_config.X_BROWSER_USE_CDP:
            attach_debug_port = await _wait_for_profile_cdp_port(profile_dir)
        if profile_status["profile_in_use"] and attach_debug_port is None:
            raise XBrowserError(
                "专用 X 浏览器仍在运行，但未检测到可连接的 CDP 端口；请关闭后从系统重新打开",
                error_code="browser_profile_in_use_without_cdp",
                retryable=True,
            )
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
        if attach_debug_port is not None:
            cdp_url = f"http://127.0.0.1:{attach_debug_port}"
            try:
                browser = await playwright.chromium.connect_over_cdp(cdp_url)
            except Exception as exc:
                raise XBrowserError(
                    f"无法连接专用 X 浏览器 CDP 端口 {attach_debug_port}",
                    error_code="browser_cdp_connect_failed",
                    retryable=True,
                ) from exc
            context = browser.contexts[0] if browser.contexts else await browser.new_context()
        elif x_config.X_BROWSER_USE_CDP:
            manager = CDPBrowserManager(user_data_dir_override=x_browser_profile_dir())
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
                "user_data_dir": x_browser_profile_dir(),
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
