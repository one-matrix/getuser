"""Deterministic browser client for X reads and explicit operator writes."""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Mapping, Optional
from urllib.parse import quote

from config import x_config

from .browser_use_fallback import BrowserUseFallback
from .exception import (
    XBrowserChallengeRequired,
    XBrowserLoginRequired,
    XBrowserStructureChanged,
)
from .field import build_topic_query

if TYPE_CHECKING:
    from playwright.async_api import Page
else:
    Page = Any


_STATUS_RE = re.compile(r"/([^/?#]+)/status/(\d+)")
_RESERVED_PATHS = {
    "home",
    "explore",
    "notifications",
    "messages",
    "search",
    "settings",
    "i",
    "compose",
}

_EXTRACT_POSTS_SCRIPT = r"""
() => Array.from(document.querySelectorAll('article[data-testid="tweet"]')).map((article) => {
  const statusLinks = Array.from(article.querySelectorAll('a[href*="/status/"]'));
  const time = article.querySelector('time');
  const timeLink = time && time.closest('a[href*="/status/"]');
  const statusLink = timeLink || statusLinks.find((link) => /\/status\/\d+/.test(link.getAttribute('href') || ''));
  const href = statusLink ? statusLink.getAttribute('href') || '' : '';
  const textNode = article.querySelector('[data-testid="tweetText"]');
  const userName = article.querySelector('[data-testid="User-Name"]');
  const userLinks = userName ? Array.from(userName.querySelectorAll('a[href^="/"]')) : [];
  const userHref = (userLinks.find((link) => /^\/[^/]+$/.test(link.getAttribute('href') || '')) || {}).getAttribute?.('href') || '';
  const displayName = userName ? (userName.querySelector('span')?.textContent || '') : '';
  const metric = (testId) => {
    const node = article.querySelector(`[data-testid="${testId}"]`);
    if (!node) return '';
    return node.getAttribute('aria-label') || node.textContent || '';
  };
  const group = article.querySelector('[role="group"]');
  return {
    href,
    user_href: userHref,
    display_name: displayName,
    text: textNode ? textNode.textContent || '' : '',
    lang: textNode ? textNode.getAttribute('lang') || '' : '',
    created_at: time ? time.getAttribute('datetime') || '' : '',
    reply_metric: metric('reply'),
    repost_metric: metric('retweet'),
    like_metric: metric('like'),
    view_metric: metric('analytics'),
    group_label: group ? group.getAttribute('aria-label') || '' : '',
  };
})
"""

_EXTRACT_TRENDS_SCRIPT = r"""
() => {
  const candidates = Array.from(document.querySelectorAll(
    '[data-testid="trend"], [data-testid="trendItem"], a[href*="/search?q="]'
  ));
  const seen = new Set();
  const items = [];
  for (const node of candidates) {
    const container = node.closest('[data-testid="trend"], [data-testid="trendItem"]') || node;
    const link = container.matches('a') ? container : container.querySelector('a[href*="/search?q="]');
    const href = link ? link.getAttribute('href') || '' : '';
    const textParts = (container.innerText || '')
      .split('\n')
      .map((part) => part.trim())
      .filter(Boolean);
    if (textParts.some((part) => /Promoted by|推广$/i.test(part))) continue;
    const contentParts = textParts.filter((part) =>
      part !== '·'
      && !/^\d+$/.test(part)
      && !/(Only on X|Trending in|Entertainment · Trending|Food · Trending|Sports · Trending|What.s happening|趋势|流行)$/i.test(part)
      && !/^Trending with\b/i.test(part)
      && !/^[\d.,]+\s*[KMB万亿]?\s*(posts?|帖子)$/i.test(part)
    );
    const name = contentParts[contentParts.length - 1] || '';
    if (!name || seen.has(name)) continue;
    seen.add(name);
    const volume = textParts.find((part) => /[\d.,]+\s*[KMB万亿]?\s*(posts?|帖子)/i.test(part)) || '';
    items.push({ name, href, volume });
  }
  return items;
}
"""

_EXTRACT_IDENTITY_SCRIPT = r"""
() => {
  const button = document.querySelector('[data-testid="SideNav_AccountSwitcher_Button"]');
  const links = button ? Array.from(button.querySelectorAll('a[href^="/"]')) : [];
  const profileLink = document.querySelector('a[data-testid="AppTabBar_Profile_Link"]');
  const href = profileLink?.getAttribute('href')
    || (links.find((link) => /^\/[^/]+$/.test(link.getAttribute('href') || '')) || {}).getAttribute?.('href')
    || '';
  const spans = button ? Array.from(button.querySelectorAll('span')).map((node) => (node.textContent || '').trim()).filter(Boolean) : [];
  return { href, labels: spans };
}
"""


class XBrowserClient:
    """Use a logged-in X browser without calling X API read endpoints."""

    def __init__(
        self,
        page: Page,
        *,
        cdp_url: str = "",
        fallback: Optional[BrowserUseFallback] = None,
    ) -> None:
        self.page = page
        self.cdp_url = cdp_url
        self.fallback = fallback or BrowserUseFallback()

    async def get_trends(
        self,
        woeid: int | str = 1,
        *,
        max_trends: int = 20,
        region_name: str = "",
    ) -> Dict[str, Any]:
        url = f"{x_config.X_BROWSER_BASE_URL}/explore/tabs/trending"
        await self._goto(url, require_login=True)
        await self._ensure_trends_rendered()
        items = await self._evaluate(_EXTRACT_TRENDS_SCRIPT)
        normalized = [
            {
                "trend_name": str(item.get("name") or "").strip(),
                "tweet_count": _parse_count(item.get("volume")),
                "source_url": (
                    _absolute_url(str(item.get("href") or ""))
                    or (
                        f"{x_config.X_BROWSER_BASE_URL}/search"
                        f"?q={quote(str(item.get('name') or ''), safe='')}&src=trend_click"
                    )
                ),
                "browser_region": region_name,
                "legacy_woeid": str(woeid),
            }
            for item in (items or [])
            if str(item.get("name") or "").strip()
        ][:max_trends]
        if not normalized:
            fallback = await self._fallback(
                mode="trends",
                url=url,
                limit=max_trends,
            )
            normalized = [
                {
                    "trend_name": str(item.get("name") or "").strip(),
                    "tweet_count": int(item.get("post_count") or 0),
                    "source_url": str(item.get("url") or ""),
                    "browser_region": region_name,
                    "legacy_woeid": str(woeid),
                }
                for item in fallback
                if str(item.get("name") or "").strip()
            ][:max_trends]
        if not normalized:
            raise XBrowserStructureChanged("X trends page returned no extractable topics")
        return {"data": normalized, "meta": {"source": "browser", "result_count": len(normalized)}}

    async def _ensure_trends_rendered(self) -> None:
        """Wait for X's lazy Explore timeline and reselect Trending if needed."""

        if not hasattr(self.page, "locator"):
            return
        trends = self.page.locator('[data-testid="trend"], [data-testid="trendItem"]')
        try:
            await trends.first.wait_for(state="visible", timeout=6_000)
            return
        except Exception:
            pass
        try:
            tab = self.page.locator('a[role="tab"][href="/explore/tabs/trending"]')
            if await tab.count():
                await tab.first.click()
            await trends.first.wait_for(state="visible", timeout=10_000)
        except Exception:
            return

    async def search_topic(
        self,
        topic: str,
        *,
        lang: Optional[str] = None,
        max_total: int = 50,
    ) -> Dict[str, Any]:
        query = build_topic_query(topic, lang=lang)
        url = (
            f"{x_config.X_BROWSER_BASE_URL}/search"
            f"?q={quote(query, safe='')}&src=typed_query&f=live"
        )
        posts = await self._collect_posts(url, max_total=max_total, require_login=True)
        return _payload(posts, query=query)

    async def lookup_post(self, post_id: str) -> Dict[str, Any]:
        if not str(post_id).isdigit():
            raise ValueError("post_id must be a numeric X Post ID")
        url = f"{x_config.X_BROWSER_BASE_URL}/i/web/status/{post_id}"
        posts = await self._collect_posts(url, max_total=1, require_login=False)
        exact = next((item for item in posts if str(item.get("id")) == str(post_id)), None)
        if exact is None:
            raise XBrowserStructureChanged(f"X post {post_id} was not found in the browser")
        payload = _payload([exact])
        payload["data"] = exact
        return payload

    async def collect_thread(self, root_post_id: str, *, max_total: int = 50) -> Dict[str, Any]:
        if not str(root_post_id).isdigit():
            raise ValueError("root_post_id must be a numeric X Post ID")
        url = f"{x_config.X_BROWSER_BASE_URL}/i/web/status/{root_post_id}"
        posts = await self._collect_posts(url, max_total=max_total, require_login=False)
        for post in posts:
            post["conversation_id"] = str(root_post_id)
            if str(post.get("id")) != str(root_post_id) and not post.get("referenced_tweets"):
                post["referenced_tweets"] = [{"type": "replied_to", "id": str(root_post_id)}]
        return _payload(posts)

    async def get_mentions(
        self,
        username: str,
        *,
        since_id: str = "",
        max_total: int = 50,
    ) -> Dict[str, Any]:
        normalized_username = username.strip().lstrip("@")
        if not normalized_username:
            raise ValueError("account username is required for browser mentions")
        url = f"{x_config.X_BROWSER_BASE_URL}/notifications/mentions"
        posts = await self._collect_posts(url, max_total=max_total, require_login=True)
        if since_id and since_id.isdigit():
            posts = [
                post
                for post in posts
                if str(post.get("id") or "").isdigit() and int(post["id"]) > int(since_id)
            ]
        return _payload(posts[:max_total])

    async def get_current_identity(self) -> Dict[str, Any]:
        url = f"{x_config.X_BROWSER_BASE_URL}/home"
        await self._goto(url, require_login=True)
        raw = await self._evaluate(_EXTRACT_IDENTITY_SCRIPT)
        username = _username_from_href(str((raw or {}).get("href") or ""))
        labels = [str(value) for value in (raw or {}).get("labels") or []]
        if not username:
            fallback = await self._fallback(mode="identity", url=url, limit=1)
            item = fallback[0] if fallback else {}
            username = str(item.get("username") or "").lstrip("@")
            display_name = str(item.get("display_name") or "")
        else:
            display_name = next(
                (label for label in labels if label and not label.startswith("@") and label != username),
                "",
            )
        if not username:
            raise XBrowserStructureChanged("could not identify the logged-in X account")
        return {
            "id": f"web:{username.casefold()}",
            "username": username,
            "name": display_name,
            "source": "browser_profile",
        }

    async def publish_reply(self, *, target_post_id: str, text: str) -> Dict[str, Any]:
        """Publish one explicitly confirmed reply with the logged-in browser.

        This method intentionally uses the visible X composer instead of an X
        API token.  It never attempts to bypass a login or account challenge,
        and it only clicks the reply action inside the exact target article.
        """

        post_id = str(target_post_id).strip()
        final_text = " ".join(str(text or "").strip().split())
        if not post_id.isdigit():
            raise ValueError("target_post_id must be a numeric X Post ID")
        if not final_text:
            raise ValueError("reply text cannot be empty")
        if len(final_text) > 280:
            raise ValueError("reply text exceeds 280 characters")
        if not hasattr(self.page, "locator"):
            raise XBrowserStructureChanged("X browser page does not support interactive reply controls")

        url = f"{x_config.X_BROWSER_BASE_URL}/i/web/status/{post_id}"
        await self._goto(url, require_login=True)
        await self._ensure_posts_rendered(require_login=True)

        article = self.page.locator(
            f'article[data-testid="tweet"]:has(a[href*="/status/{post_id}"])'
        ).first
        if await article.count() == 0:
            raise XBrowserStructureChanged(f"X target post {post_id} is not visible in the browser")
        reply_button = article.locator('[data-testid="reply"]').first
        if await reply_button.count() == 0:
            raise XBrowserStructureChanged("X target post reply button was not found")

        async def visible_locator(container: Any, selector: str) -> Any:
            try:
                candidates = container.locator(selector)
                count = await candidates.count()
                for index in range(count - 1, -1, -1):
                    candidate = candidates.nth(index) if hasattr(candidates, "nth") else candidates.last
                    if await candidate.is_visible():
                        return candidate
            except Exception:
                pass
            return None

        async def wait_visible_locator(
            container: Any,
            selector: str,
            timeout_ms: int,
        ) -> Any:
            deadline = asyncio.get_running_loop().time() + max(0, timeout_ms) / 1000
            while True:
                candidate = await visible_locator(container, selector)
                if candidate is not None:
                    return candidate
                if asyncio.get_running_loop().time() >= deadline:
                    return None
                await asyncio.sleep(0.1)

        target_dialog_selector = f'div[role="dialog"]:has(a[href*="/status/{post_id}"])'
        target_dialog = await visible_locator(self.page, target_dialog_selector)
        dialog = target_dialog
        composer = None
        submit = None
        composer_surface = "dialog"

        if target_dialog is not None:
            composer = await visible_locator(
                target_dialog,
                '[data-testid="tweetTextarea_0"][contenteditable="true"]',
            )
            submit = await visible_locator(
                target_dialog,
                '[data-testid="tweetButton"], [data-testid="tweetButtonInline"]',
            )
        else:
            # X permalink pages expose a faster inline "Post your reply"
            # editor. Activate the visible prompt first, then resolve the
            # editable textbox inside that exact composer. Looking up the
            # textbox globally can select another dormant X composer.
            inline_scope = await wait_visible_locator(
                self.page,
                '[data-testid="tweetTextarea_0_label"]:has-text("Post your reply")',
                x_config.X_BROWSER_INLINE_COMPOSER_WAIT_MS,
            )
            if inline_scope is not None:
                inline_prompt = await visible_locator(
                    inline_scope,
                    '.public-DraftEditorPlaceholder-inner:text-is("Post your reply")',
                )
                try:
                    focus_target = inline_prompt if inline_prompt is not None else inline_scope
                    await focus_target.click(timeout=3_000)
                except Exception:
                    # The editor can already be focused and remove its
                    # placeholder between discovery and the click.
                    pass
                inline_editor = inline_scope.locator(
                    '[data-testid="tweetTextarea_0"][contenteditable="true"], '
                    '[role="textbox"][contenteditable="true"][aria-label="Post text"]'
                ).last
                try:
                    await inline_editor.wait_for(
                        state="visible",
                        timeout=x_config.X_BROWSER_INLINE_COMPOSER_WAIT_MS,
                    )
                except Exception:
                    inline_editor = None
                inline_composer = inline_editor
            else:
                # Compatibility fallback for X variants that omit the label
                # wrapper while still exposing an inline editable textbox.
                inline_composer = await visible_locator(
                    self.page,
                    '[data-testid="tweetTextarea_0"][contenteditable="true"], '
                    '[role="textbox"][contenteditable="true"][aria-label="Post text"]',
                )
            inline_submit = await visible_locator(
                self.page,
                '[data-testid="tweetButtonInline"]',
            )
            if inline_composer is not None and inline_submit is not None:
                composer = inline_composer
                submit = inline_submit
                composer_surface = "inline"

        if composer is None:
            try:
                await reply_button.click(timeout=5_000)
            except Exception as exc:
                # X can finish opening the modal while Playwright is still
                # reporting the underlying page mask as a pointer interceptor.
                target_dialog = await visible_locator(self.page, target_dialog_selector)
                generic_dialog = await visible_locator(self.page, 'div[role="dialog"]')
                if target_dialog is None and generic_dialog is None:
                    raise XBrowserStructureChanged(
                        "X reply button is blocked by another page overlay; close the open X dialog and retry"
                    ) from exc
            dialog_candidate = self.page.locator('div[role="dialog"]').last
            try:
                await dialog_candidate.wait_for(state="visible", timeout=8_000)
            except Exception as exc:
                raise XBrowserStructureChanged("X reply dialog did not open") from exc
            dialog = (
                await visible_locator(self.page, target_dialog_selector)
                or await visible_locator(self.page, 'div[role="dialog"]')
            )
            if dialog is None:
                raise XBrowserStructureChanged("X reply dialog did not remain visible")
            composer = await visible_locator(
                dialog,
                '[data-testid="tweetTextarea_0"][contenteditable="true"]',
            )
            submit = await visible_locator(
                dialog,
                '[data-testid="tweetButton"], [data-testid="tweetButtonInline"]',
            )

        if composer is None:
            raise XBrowserStructureChanged("X reply composer was not found in the active editor")
        try:
            await composer.wait_for(state="visible", timeout=8_000)
            await composer.fill(final_text, timeout=8_000)
        except Exception as exc:
            await self._raise_page_state(require_login=True)
            raise XBrowserStructureChanged("X reply composer did not become editable") from exc

        if submit is None:
            raise XBrowserStructureChanged("X reply submit button was not found")
        try:
            await submit.wait_for(state="visible", timeout=5_000)
            if hasattr(submit, "is_enabled") and not await submit.is_enabled():
                raise XBrowserStructureChanged("X reply submit button is disabled")
        except XBrowserStructureChanged:
            raise
        except Exception as exc:
            raise XBrowserStructureChanged("X reply submit button is not ready") from exc

        captured_responses: List[Any] = []

        def capture_create_tweet(response: Any) -> None:
            request = getattr(response, "request", None)
            method = str(getattr(request, "method", "") or "").upper()
            response_url = str(getattr(response, "url", "") or "")
            if method == "POST" and "CreateTweet" in response_url:
                captured_responses.append(response)

        can_observe_responses = hasattr(self.page, "on")
        if can_observe_responses:
            self.page.on("response", capture_create_tweet)
        try:
            await submit.click(timeout=10_000)
            toast_text = ""
            toast_href = ""
            composer_closed = False
            for _ in range(24):
                if captured_responses:
                    break
                toast = self.page.locator('[data-testid="toast"]').last
                try:
                    if await toast.count() and await toast.is_visible():
                        toast_text = str(await toast.inner_text() or "")
                        toast_link = toast.locator('a[href*="/status/"]').last
                        if await toast_link.count():
                            toast_href = str(await toast_link.get_attribute("href") or "")
                        break
                except Exception:
                    pass
                try:
                    composer_closed = not await composer.is_visible()
                except Exception:
                    composer_closed = False
                if composer_closed:
                    break
                await asyncio.sleep(0.25)

            response_status = 0
            response_payload: Any = {}
            if captured_responses:
                response = captured_responses[-1]
                response_status = int(getattr(response, "status", 0) or 0)
                try:
                    response_payload = await response.json()
                except Exception:
                    response_payload = {}
                if response_status >= 400:
                    raise XBrowserStructureChanged(
                        f"X browser reply request failed with HTTP {response_status}"
                    )

            created_post_id = _created_post_id(response_payload)
            if not created_post_id:
                created_post_id = _post_id_from_href(toast_href)
            success_text = bool(
                re.search(r"(?:sent|posted|published|已发送|已发布|发送成功)", toast_text, re.I)
            )
            if not (captured_responses or created_post_id or success_text or composer_closed):
                raise XBrowserStructureChanged(
                    "X reply was submitted but the browser did not expose a success confirmation; inspect the open browser before retrying"
                )
            return {
                "data": {"id": created_post_id, "text": final_text},
                "meta": {
                    "source": "browser",
                    "target_post_id": post_id,
                    "composer_surface": composer_surface,
                    "http_status": response_status,
                    "confirmation": (
                        "create_tweet_response"
                        if captured_responses
                        else "toast"
                        if (created_post_id or success_text)
                        else "composer_closed"
                    ),
                },
            }
        finally:
            if can_observe_responses and hasattr(self.page, "remove_listener"):
                self.page.remove_listener("response", capture_create_tweet)

    async def _collect_posts(
        self,
        url: str,
        *,
        max_total: int,
        require_login: bool,
    ) -> List[Dict[str, Any]]:
        await self._goto(url, require_login=require_login)
        await self._ensure_posts_rendered(require_login=require_login)
        collected: Dict[str, Dict[str, Any]] = {}
        stagnant_rounds = 0
        for _ in range(max(1, x_config.X_BROWSER_MAX_SCROLLS)):
            raw_items = await self._evaluate(_EXTRACT_POSTS_SCRIPT)
            before = len(collected)
            for raw in raw_items or []:
                post = _normalize_extracted_post(raw)
                if post.get("id"):
                    collected[str(post["id"])] = post
            if len(collected) >= max_total:
                break
            stagnant_rounds = stagnant_rounds + 1 if len(collected) == before else 0
            if stagnant_rounds >= 2:
                break
            await self._evaluate("window.scrollBy(0, Math.max(window.innerHeight * 0.85, 700))")
            await asyncio.sleep(x_config.X_BROWSER_SCROLL_DELAY_MS / 1000)

        posts = list(collected.values())[:max_total]
        if not posts:
            fallback_items = await self._fallback(
                mode=_mode_from_url(url),
                url=url,
                limit=max_total,
            )
            posts = [
                _normalize_fallback_post(item)
                for item in fallback_items
                if item.get("post_id") or item.get("id")
            ][:max_total]
        if not posts:
            await self._raise_page_state(require_login=require_login)
            raise XBrowserStructureChanged(
                "X post timeline did not render after waiting, retrying, and reloading once"
            )
        return posts

    async def _ensure_posts_rendered(self, *, require_login: bool) -> None:
        """Recover once from X's lazy timeline and transient Retry screen."""

        if not hasattr(self.page, "locator"):
            return

        articles = self.page.locator('article[data-testid="tweet"]')

        async def wait_for_article(timeout_ms: int) -> bool:
            try:
                await articles.first.wait_for(state="visible", timeout=timeout_ms)
                return True
            except Exception:
                return False

        if await wait_for_article(x_config.X_BROWSER_POST_RENDER_WAIT_MS):
            return

        await self._raise_page_state(require_login=require_login)
        retry_text = re.compile(
            r"^\s*(?:Retry|Try again|Reload|重试|再试一次|重新加载)\s*$",
            flags=re.I,
        )
        try:
            retry_button = self.page.locator("button").filter(has_text=retry_text)
            if await retry_button.count():
                await retry_button.first.click(timeout=3_000)
                if await wait_for_article(x_config.X_BROWSER_POST_RELOAD_WAIT_MS):
                    return
        except Exception:
            # X changes its transient error button frequently; the bounded reload
            # below is the deterministic recovery path when it cannot be clicked.
            pass

        try:
            await self.page.reload(wait_until="domcontentloaded")
            await asyncio.sleep(x_config.X_BROWSER_PAGE_SETTLE_MS / 1000)
            await self._raise_page_state(require_login=require_login)
            await wait_for_article(x_config.X_BROWSER_POST_RELOAD_WAIT_MS)
        except (XBrowserChallengeRequired, XBrowserLoginRequired):
            raise
        except Exception:
            return

    async def _goto(self, url: str, *, require_login: bool) -> None:
        try:
            await self.page.goto(url, wait_until="domcontentloaded")
        except Exception as exc:
            raise XBrowserStructureChanged(
                f"X browser navigation failed for {url}: {exc}"
            ) from exc
        await asyncio.sleep(x_config.X_BROWSER_PAGE_SETTLE_MS / 1000)
        await self._raise_page_state(require_login=require_login)

    async def _raise_page_state(self, *, require_login: bool) -> None:
        current_url = str(self.page.url or "")
        lowered = current_url.casefold()
        if any(marker in lowered for marker in ("/account/access", "/i/flow/challenge", "captcha")):
            raise XBrowserChallengeRequired(
                "X displayed a security challenge; complete it manually in the browser before retrying"
            )
        if "/i/flow/login" in lowered:
            raise XBrowserLoginRequired(
                "X browser profile is not logged in; open the configured Chrome profile and sign in"
            )
        if require_login and hasattr(self.page, "locator"):
            try:
                login_count = await self.page.locator(
                    'a[href="/login"], [data-testid="loginButton"], '
                    '[data-testid="LoginForm_Login_Button"]'
                ).count()
            except Exception:
                login_count = 0
            if login_count:
                raise XBrowserLoginRequired(
                    "X browser profile is not logged in; open the configured Chrome profile and sign in"
                )

    async def _evaluate(self, script: str) -> Any:
        try:
            return await self.page.evaluate(script)
        except XBrowserStructureChanged:
            raise
        except Exception as exc:
            raise XBrowserStructureChanged(
                f"X page script evaluation failed: {exc}"
            ) from exc

    async def _fallback(self, *, mode: str, url: str, limit: int) -> List[Dict[str, Any]]:
        if not self.cdp_url or not self.fallback.available:
            return []
        payload = await self.fallback.extract(
            mode=mode,
            url=url,
            cdp_url=self.cdp_url,
            limit=limit,
        )
        return [dict(item) for item in payload.get("items") or [] if isinstance(item, Mapping)]


def _payload(posts: Iterable[Mapping[str, Any]], *, query: str = "") -> Dict[str, Any]:
    data = [dict(item) for item in posts]
    users: Dict[str, Dict[str, Any]] = {}
    for post in data:
        author_id = str(post.get("author_id") or "")
        username = str(post.pop("_author_username", "") or "")
        display_name = str(post.pop("_author_display_name", "") or "")
        if author_id:
            users[author_id] = {
                "id": author_id,
                "username": username,
                "name": display_name,
            }
    return {
        "data": data,
        "includes": {"users": list(users.values())},
        "meta": {"source": "browser", "result_count": len(data)},
        "query": query,
    }


def _normalize_extracted_post(raw: Mapping[str, Any]) -> Dict[str, Any]:
    match = _STATUS_RE.search(str(raw.get("href") or ""))
    if not match:
        return {}
    username, post_id = match.groups()
    username = _username_from_href(str(raw.get("user_href") or "")) or username
    text = str(raw.get("text") or "").strip()
    entities = {
        "mentions": [{"username": value} for value in re.findall(r"@([A-Za-z0-9_]{1,15})", text)],
        "hashtags": [{"tag": value} for value in re.findall(r"#([\w\u0080-\uffff]+)", text)],
    }
    metrics = {
        "reply_count": _parse_metric(raw.get("reply_metric"), raw.get("group_label"), 0),
        "retweet_count": _parse_metric(raw.get("repost_metric"), raw.get("group_label"), 1),
        "like_count": _parse_metric(raw.get("like_metric"), raw.get("group_label"), 2),
        "quote_count": 0,
        "view_count": _parse_count(raw.get("view_metric")),
    }
    return {
        "id": post_id,
        "author_id": f"web:{username.casefold()}",
        "_author_username": username,
        "_author_display_name": str(raw.get("display_name") or ""),
        "text": text,
        "lang": str(raw.get("lang") or ""),
        "created_at": str(raw.get("created_at") or ""),
        "conversation_id": post_id,
        "public_metrics": metrics,
        "referenced_tweets": [],
        "entities": entities,
        "source_url": _absolute_url(str(raw.get("href") or "")),
        "browser_collected_at": datetime.now(timezone.utc).isoformat(),
    }


def _normalize_fallback_post(raw: Mapping[str, Any]) -> Dict[str, Any]:
    username = str(raw.get("username") or "").strip().lstrip("@")
    post_id = str(raw.get("post_id") or raw.get("id") or "")
    return {
        "id": post_id,
        "author_id": f"web:{username.casefold()}" if username else "",
        "_author_username": username,
        "_author_display_name": str(raw.get("display_name") or ""),
        "text": str(raw.get("text") or ""),
        "lang": str(raw.get("lang") or ""),
        "created_at": str(raw.get("created_at") or ""),
        "conversation_id": str(raw.get("conversation_id") or post_id),
        "public_metrics": {
            "reply_count": int(raw.get("reply_count") or 0),
            "retweet_count": int(raw.get("repost_count") or raw.get("retweet_count") or 0),
            "like_count": int(raw.get("like_count") or 0),
            "quote_count": int(raw.get("quote_count") or 0),
            "view_count": int(raw.get("view_count") or 0),
        },
        "referenced_tweets": (
            [{"type": "replied_to", "id": str(raw["parent_post_id"])}]
            if raw.get("parent_post_id")
            else []
        ),
        "entities": {
            "mentions": [{"username": value} for value in re.findall(r"@([A-Za-z0-9_]{1,15})", str(raw.get("text") or ""))],
            "hashtags": [{"tag": value} for value in re.findall(r"#([\w\u0080-\uffff]+)", str(raw.get("text") or ""))],
        },
        "source_url": str(raw.get("url") or ""),
        "browser_use_fallback": True,
    }


def _parse_metric(primary: Any, group_label: Any, position: int) -> int:
    parsed = _parse_count(primary)
    if parsed:
        return parsed
    numbers = re.findall(r"[\d.,]+\s*[KMB万亿]?", str(group_label or ""), flags=re.I)
    return _parse_count(numbers[position]) if len(numbers) > position else 0


def _parse_count(value: Any) -> int:
    text = str(value or "").strip().replace(",", "")
    match = re.search(r"(\d+(?:\.\d+)?)\s*([KMB万亿]?)", text, flags=re.I)
    if not match:
        return 0
    number = float(match.group(1))
    multiplier = {
        "": 1,
        "K": 1_000,
        "M": 1_000_000,
        "B": 1_000_000_000,
        "万": 10_000,
        "亿": 100_000_000,
    }.get(match.group(2).upper(), 1)
    return int(number * multiplier)


def _created_post_id(payload: Any) -> str:
    """Extract the created tweet ID from X's browser CreateTweet response."""

    if isinstance(payload, Mapping):
        for key in ("rest_id", "id_str"):
            value = str(payload.get(key) or "")
            if value.isdigit():
                return value
        for key in ("tweet_results", "create_tweet", "result", "data"):
            if key in payload:
                found = _created_post_id(payload[key])
                if found:
                    return found
        for value in payload.values():
            found = _created_post_id(value)
            if found:
                return found
    elif isinstance(payload, list):
        for value in payload:
            found = _created_post_id(value)
            if found:
                return found
    return ""


def _post_id_from_href(href: str) -> str:
    match = _STATUS_RE.search(str(href or ""))
    return match.group(2) if match else ""


def _username_from_href(href: str) -> str:
    candidate = href.strip().split("?", 1)[0].strip("/")
    if not candidate or "/" in candidate or candidate.casefold() in _RESERVED_PATHS:
        return ""
    return candidate.lstrip("@")


def _absolute_url(href: str) -> str:
    if href.startswith("http"):
        return href
    return f"{x_config.X_BROWSER_BASE_URL}{href}" if href.startswith("/") else ""


def _mode_from_url(url: str) -> str:
    if "/notifications/mentions" in url:
        return "mentions"
    if "/search?" in url:
        return "search"
    if "/status/" in url:
        return "thread"
    return "post"
