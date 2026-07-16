"""Optional browser-use sidecar integration.

The main MediaCrawler environment pins older versions of Pydantic and Pillow
than current browser-use releases. To avoid destabilising the application,
browser-use runs in an optional, separately managed environment and connects to
the same Chrome instance through CDP.
"""

from __future__ import annotations

import asyncio
import json
import shlex
from typing import Any, Dict, Mapping, Optional, Sequence

from config import x_config

from .exception import XBrowserError


RESULT_PREFIX = "X_BROWSER_USE_RESULT="


class BrowserUseFallback:
    """Run the optional browser-use extractor as a bounded subprocess."""

    def __init__(
        self,
        *,
        command: Optional[Sequence[str] | str] = None,
        timeout_seconds: Optional[int] = None,
    ) -> None:
        configured = command if command is not None else x_config.X_BROWSER_USE_FALLBACK_COMMAND
        self.command = (
            shlex.split(configured)
            if isinstance(configured, str)
            else list(configured or [])
        )
        self.timeout_seconds = int(
            timeout_seconds or x_config.X_BROWSER_USE_TIMEOUT_SECONDS
        )

    @property
    def available(self) -> bool:
        return bool(x_config.X_BROWSER_USE_FALLBACK_ENABLED and self.command)

    async def extract(
        self,
        *,
        mode: str,
        url: str,
        cdp_url: str,
        limit: int,
        topic: str = "",
        account_username: str = "",
    ) -> Dict[str, Any]:
        if not self.available:
            return {"items": [], "fallback_used": False}
        if mode not in {"trends", "search", "thread", "mentions", "identity", "post"}:
            raise ValueError(f"unsupported browser-use extraction mode: {mode}")
        if not url.startswith(("https://x.com/", "https://www.x.com/")):
            raise ValueError("browser-use fallback only accepts x.com URLs")
        if not cdp_url.startswith(("http://", "https://", "ws://", "wss://")):
            raise ValueError("a valid CDP URL is required for browser-use fallback")

        request = {
            "mode": mode,
            "url": url,
            "cdp_url": cdp_url,
            "limit": max(1, min(int(limit), 100)),
            "topic": topic,
            "account_username": account_username,
            "model": x_config.X_BROWSER_USE_MODEL,
            "max_steps": x_config.X_BROWSER_USE_MAX_STEPS,
        }
        try:
            process = await asyncio.create_subprocess_exec(
                *self.command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as exc:
            raise XBrowserError(
                f"browser-use sidecar could not start: {exc}",
                error_code="browser_use_start_failed",
                retryable=False,
            ) from exc

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(json.dumps(request).encode("utf-8")),
                timeout=self.timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            process.kill()
            await process.wait()
            raise XBrowserError(
                "browser-use fallback timed out",
                error_code="browser_use_timeout",
                retryable=True,
            ) from exc

        text = stdout.decode("utf-8", errors="replace")
        if process.returncode != 0:
            detail = stderr.decode("utf-8", errors="replace").strip() or text.strip()
            raise XBrowserError(
                f"browser-use fallback failed: {detail[-800:]}",
                error_code="browser_use_failed",
                retryable=True,
            )
        return parse_sidecar_output(text)


def parse_sidecar_output(output: str) -> Dict[str, Any]:
    """Parse the final marked JSON line while ignoring dependency log output."""

    for line in reversed(output.splitlines()):
        if not line.startswith(RESULT_PREFIX):
            continue
        try:
            payload = json.loads(line[len(RESULT_PREFIX) :])
        except json.JSONDecodeError as exc:
            raise XBrowserError(
                "browser-use fallback returned invalid JSON",
                error_code="browser_use_invalid_output",
                retryable=True,
            ) from exc
        if not isinstance(payload, Mapping):
            break
        result = dict(payload)
        result["fallback_used"] = True
        result.setdefault("items", [])
        return result
    raise XBrowserError(
        "browser-use fallback returned no marked result",
        error_code="browser_use_empty_output",
        retryable=True,
    )
