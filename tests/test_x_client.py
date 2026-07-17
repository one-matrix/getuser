import json

import httpx
import pytest

from media_platform.x.browser_client import XBrowserClient, _parse_count
from media_platform.x.browser_use_fallback import parse_sidecar_output
from media_platform.x.client import XWriteApiClient
from media_platform.x.exception import (
    XBrowserChallengeRequired,
    XConfigurationError,
)


class FakePage:
    def __init__(self, *, posts=None, trends=None, url="https://x.com/home"):
        self.posts = posts or []
        self.trends = trends or []
        self.url = url
        self.visited = []

    async def goto(self, url, **kwargs):
        self.url = url
        self.visited.append(url)

    async def evaluate(self, script):
        if "article[data-testid" in script:
            return self.posts
        if 'data-testid="trend"' in script:
            return self.trends
        if "SideNav_AccountSwitcher_Button" in script:
            return {"href": "/brandbot", "labels": ["Brand", "@brandbot"]}
        return None


class LazyPostLocator:
    def __init__(self, page, selector):
        self.page = page
        self.selector = selector

    @property
    def first(self):
        return self

    def filter(self, **kwargs):
        return self

    async def wait_for(self, **kwargs):
        if 'article[data-testid="tweet"]' in self.selector and self.page.posts:
            return
        raise RuntimeError("not visible")

    async def count(self):
        if self.selector == "button":
            return int(self.page.retry_available)
        return 0

    async def click(self, **kwargs):
        self.page.retry_clicks += 1
        self.page.posts = list(self.page.retry_posts)


class LazyPostPage(FakePage):
    def __init__(self, *, retry_posts=None, reload_posts=None):
        super().__init__(posts=[])
        self.retry_posts = retry_posts or []
        self.reload_posts = reload_posts or []
        self.retry_available = bool(retry_posts)
        self.retry_clicks = 0
        self.reloads = 0

    def locator(self, selector):
        return LazyPostLocator(self, selector)

    async def reload(self, **kwargs):
        self.reloads += 1
        self.posts = list(self.reload_posts)


class FakeCreateTweetResponse:
    status = 200
    url = "https://x.com/i/api/graphql/test/CreateTweet"

    class Request:
        method = "POST"

    request = Request()

    async def json(self):
        return {"data": {"create_tweet": {"tweet_results": {"result": {"rest_id": "2099000000000000001"}}}}}


class ReplyLocator:
    def __init__(self, page, kind):
        self.page = page
        self.kind = kind

    @property
    def first(self):
        return self

    @property
    def last(self):
        return self

    def nth(self, index):
        return self

    def locator(self, selector):
        if self.kind == "article" and 'data-testid="reply"' in selector:
            return ReplyLocator(self.page, "reply")
        if self.kind == "dialog" and "tweetTextarea_0" in selector:
            return ReplyLocator(self.page, "composer")
        if self.kind == "dialog" and "tweetButton" in selector:
            return ReplyLocator(self.page, "submit")
        if self.kind == "inline_scope" and "public-DraftEditorPlaceholder-inner" in selector:
            return ReplyLocator(self.page, "inline_prompt")
        if self.kind == "inline_scope" and (
            "tweetTextarea_0" in selector or 'role="textbox"' in selector
        ):
            return ReplyLocator(self.page, "inline_composer")
        if self.kind == "toast" and "/status/" in selector:
            return ReplyLocator(self.page, "toast_link")
        return ReplyLocator(self.page, "other")

    async def count(self):
        return int(self.kind in {
            "article",
            "reply",
            "dialog",
            "composer",
            "submit",
            "inline_scope",
            "inline_prompt",
            "inline_composer",
            "inline_submit",
        })

    async def wait_for(self, **kwargs):
        if self.kind == "inline_composer" and not self.page.inline_editor_visible:
            raise RuntimeError("inline editor is not active")
        return None

    async def click(self, **kwargs):
        if self.kind == "reply":
            self.page.reply_clicks += 1
            self.page.composer_visible = True
        if self.kind == "submit":
            self.page.composer_visible = False
            for callback in self.page.response_callbacks:
                callback(FakeCreateTweetResponse())
        if self.kind == "inline_submit":
            for callback in self.page.response_callbacks:
                callback(FakeCreateTweetResponse())
        if self.kind in {"inline_scope", "inline_prompt"}:
            self.page.inline_prompt_clicks += 1
            self.page.inline_editor_visible = True

    async def fill(self, value, **kwargs):
        self.page.filled_text = value

    async def is_enabled(self):
        return True

    async def is_visible(self):
        if self.kind in {"dialog", "composer", "submit"}:
            return self.page.composer_visible
        if self.kind in {"inline_scope", "inline_prompt", "inline_submit"}:
            return self.page.inline_visible
        if self.kind == "inline_composer":
            return self.page.inline_editor_visible
        return False

    async def inner_text(self):
        return ""

    async def get_attribute(self, name):
        return None


class ReplyPage(FakePage):
    def __init__(self):
        super().__init__(posts=[_raw_post("2077921225230426406")])
        self.composer_visible = False
        self.filled_text = ""
        self.reply_clicks = 0
        self.response_callbacks = []
        self.inline_visible = False
        self.inline_editor_visible = False
        self.inline_prompt_clicks = 0

    def locator(self, selector):
        if 'article[data-testid="tweet"]' in selector:
            return ReplyLocator(self, "article")
        if 'div[role="dialog"]' in selector:
            return ReplyLocator(self, "dialog")
        if 'tweetTextarea_0' in selector:
            return ReplyLocator(self, "composer")
        if 'tweetButton' in selector:
            return ReplyLocator(self, "submit")
        if 'data-testid="toast"' in selector:
            return ReplyLocator(self, "toast")
        return ReplyLocator(self, "other")

    def on(self, event, callback):
        if event == "response":
            self.response_callbacks.append(callback)

    def remove_listener(self, event, callback):
        if callback in self.response_callbacks:
            self.response_callbacks.remove(callback)


class InlineReplyPage(ReplyPage):
    def __init__(self):
        super().__init__()
        self.inline_visible = True

    def locator(self, selector):
        if 'div[role="dialog"]' in selector:
            return ReplyLocator(self, "dialog")
        if 'tweetTextarea_0_label' in selector:
            return ReplyLocator(self, "inline_scope")
        if 'tweetTextarea_0' in selector:
            return ReplyLocator(self, "inline_composer")
        if 'tweetButtonInline' in selector:
            return ReplyLocator(self, "inline_submit")
        return super().locator(selector)


class BareInlineReplyPage(ReplyPage):
    """X variant with the editable textbox but without its label wrapper."""

    def __init__(self):
        super().__init__()
        self.inline_visible = True
        self.inline_editor_visible = True

    def locator(self, selector):
        if 'div[role="dialog"]' in selector:
            return ReplyLocator(self, "dialog")
        if 'tweetTextarea_0_label' in selector:
            return ReplyLocator(self, "other")
        if 'tweetTextarea_0' in selector or 'role="textbox"' in selector:
            return ReplyLocator(self, "inline_composer")
        if 'tweetButtonInline' in selector:
            return ReplyLocator(self, "inline_submit")
        return super().locator(selector)


@pytest.mark.asyncio
async def test_browser_client_searches_x_page_without_api_request(monkeypatch):
    from config import x_config

    monkeypatch.setattr(x_config, "X_BROWSER_PAGE_SETTLE_MS", 0)
    monkeypatch.setattr(x_config, "X_BROWSER_SCROLL_DELAY_MS", 0)
    monkeypatch.setattr(x_config, "X_BROWSER_MAX_SCROLLS", 1)
    page = FakePage(
        posts=[
            {
                "href": "/author/status/1900000000000000001",
                "user_href": "/author",
                "display_name": "Author",
                "text": "Post about #MediaCrawler by @brandbot",
                "lang": "en",
                "created_at": "2026-07-16T08:00:00Z",
                "reply_metric": "1 reply",
                "repost_metric": "2 reposts",
                "like_metric": "3 likes",
                "view_metric": "1.2K views",
                "group_label": "",
            }
        ]
    )
    result = await XBrowserClient(page).search_topic("MediaCrawler", max_total=5)
    assert page.visited[0].startswith("https://x.com/search?")
    assert result["meta"]["source"] == "browser"
    assert result["data"][0]["id"] == "1900000000000000001"
    assert result["data"][0]["public_metrics"]["view_count"] == 1200
    assert result["includes"]["users"][0]["username"] == "author"


@pytest.mark.asyncio
async def test_browser_client_recovers_from_x_retry_screen(monkeypatch):
    from config import x_config

    monkeypatch.setattr(x_config, "X_BROWSER_PAGE_SETTLE_MS", 0)
    monkeypatch.setattr(x_config, "X_BROWSER_POST_RENDER_WAIT_MS", 0)
    monkeypatch.setattr(x_config, "X_BROWSER_POST_RELOAD_WAIT_MS", 0)
    monkeypatch.setattr(x_config, "X_BROWSER_SCROLL_DELAY_MS", 0)
    monkeypatch.setattr(x_config, "X_BROWSER_MAX_SCROLLS", 1)
    page = LazyPostPage(retry_posts=[_raw_post("2077921225230426406")])

    result = await XBrowserClient(page).collect_thread(
        "2077921225230426406",
        max_total=5,
    )

    assert result["meta"]["result_count"] == 1
    assert page.retry_clicks == 1
    assert page.reloads == 0


@pytest.mark.asyncio
async def test_browser_client_reloads_once_when_retry_button_is_missing(monkeypatch):
    from config import x_config

    monkeypatch.setattr(x_config, "X_BROWSER_PAGE_SETTLE_MS", 0)
    monkeypatch.setattr(x_config, "X_BROWSER_POST_RENDER_WAIT_MS", 0)
    monkeypatch.setattr(x_config, "X_BROWSER_POST_RELOAD_WAIT_MS", 0)
    monkeypatch.setattr(x_config, "X_BROWSER_SCROLL_DELAY_MS", 0)
    monkeypatch.setattr(x_config, "X_BROWSER_MAX_SCROLLS", 1)
    page = LazyPostPage(reload_posts=[_raw_post("2077921225230426406")])

    result = await XBrowserClient(page).collect_thread(
        "2077921225230426406",
        max_total=5,
    )

    assert result["meta"]["result_count"] == 1
    assert page.retry_clicks == 0
    assert page.reloads == 1


@pytest.mark.asyncio
async def test_browser_client_extracts_trends_and_identity(monkeypatch):
    from config import x_config

    monkeypatch.setattr(x_config, "X_BROWSER_PAGE_SETTLE_MS", 0)
    page = FakePage(
        trends=[
            {"name": "#AI", "href": "/search?q=%23AI", "volume": "12.5K posts"},
            {"name": "Product News", "href": "/search?q=Product", "volume": ""},
        ]
    )
    client = XBrowserClient(page)
    trends = await client.get_trends(1, max_trends=2, region_name="Profile default")
    identity = await client.get_current_identity()
    assert trends["data"][0]["tweet_count"] == 12_500
    assert trends["data"][0]["browser_region"] == "Profile default"
    assert identity["id"] == "web:brandbot"
    assert identity["username"] == "brandbot"


@pytest.mark.asyncio
async def test_browser_client_publishes_reply_with_logged_in_composer(monkeypatch):
    from config import x_config

    monkeypatch.setattr(x_config, "X_BROWSER_PAGE_SETTLE_MS", 0)
    monkeypatch.setattr(x_config, "X_BROWSER_INLINE_COMPOSER_WAIT_MS", 0)
    page = ReplyPage()

    result = await XBrowserClient(page).publish_reply(
        target_post_id="2077921225230426406",
        text="Thanks for sharing this update.",
    )

    assert page.filled_text == "Thanks for sharing this update."
    assert result["data"]["id"] == "2099000000000000001"
    assert result["meta"]["source"] == "browser"
    assert result["meta"]["confirmation"] == "create_tweet_response"


@pytest.mark.asyncio
async def test_browser_client_reuses_open_target_reply_dialog_without_clicking_mask(monkeypatch):
    from config import x_config

    monkeypatch.setattr(x_config, "X_BROWSER_PAGE_SETTLE_MS", 0)
    page = ReplyPage()
    page.composer_visible = True

    result = await XBrowserClient(page).publish_reply(
        target_post_id="2077921225230426406",
        text="Use the open reply dialog.",
    )

    assert page.reply_clicks == 0
    assert page.filled_text == "Use the open reply dialog."
    assert result["data"]["id"] == "2099000000000000001"


@pytest.mark.asyncio
async def test_browser_client_prefers_permalink_inline_reply_editor(monkeypatch):
    from config import x_config

    monkeypatch.setattr(x_config, "X_BROWSER_PAGE_SETTLE_MS", 0)
    page = InlineReplyPage()

    result = await XBrowserClient(page).publish_reply(
        target_post_id="2077921225230426406",
        text="Use the faster inline reply editor.",
    )

    assert page.reply_clicks == 0
    assert page.inline_prompt_clicks == 1
    assert page.filled_text == "Use the faster inline reply editor."
    assert result["data"]["id"] == "2099000000000000001"
    assert result["meta"]["composer_surface"] == "inline"


@pytest.mark.asyncio
async def test_browser_client_supports_inline_editor_without_prompt_wrapper(monkeypatch):
    from config import x_config

    monkeypatch.setattr(x_config, "X_BROWSER_PAGE_SETTLE_MS", 0)
    monkeypatch.setattr(x_config, "X_BROWSER_INLINE_COMPOSER_WAIT_MS", 0)
    page = BareInlineReplyPage()

    result = await XBrowserClient(page).publish_reply(
        target_post_id="2077921225230426406",
        text="Use the compatible bare inline editor.",
    )

    assert page.reply_clicks == 0
    assert page.inline_prompt_clicks == 0
    assert page.filled_text == "Use the compatible bare inline editor."
    assert result["meta"]["composer_surface"] == "inline"


@pytest.mark.asyncio
async def test_browser_client_stops_on_manual_challenge(monkeypatch):
    from config import x_config

    monkeypatch.setattr(x_config, "X_BROWSER_PAGE_SETTLE_MS", 0)
    page = FakePage(url="https://x.com/account/access")

    async def challenge_goto(url, **kwargs):
        page.url = "https://x.com/account/access"

    page.goto = challenge_goto
    with pytest.raises(XBrowserChallengeRequired):
        await XBrowserClient(page).search_topic("MediaCrawler")


@pytest.mark.asyncio
async def test_write_client_create_reply_requires_user_context_and_exact_payload():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["authorization"] = request.headers.get("authorization")
        seen["payload"] = json.loads(request.content)
        return httpx.Response(201, json={"data": {"id": "999", "text": "Thanks"}})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = XWriteApiClient(
        user_access_token="user-token",
        http_client=http_client,
    )
    result = await client.create_reply(text="Thanks", target_post_id="123")
    assert result["data"]["id"] == "999"
    assert seen["method"] == "POST"
    assert seen["authorization"] == "Bearer user-token"
    assert seen["payload"] == {
        "text": "Thanks",
        "reply": {"in_reply_to_tweet_id": "123"},
    }
    await http_client.aclose()


@pytest.mark.asyncio
async def test_write_client_rejects_all_read_operations():
    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200))
    )
    client = XWriteApiClient(user_access_token="token", http_client=http_client)
    with pytest.raises(XConfigurationError, match="rejects read operations"):
        await client.request("GET", "/tweets/123")
    await http_client.aclose()


def test_browser_count_and_sidecar_output_parsing():
    assert _parse_count("1.5M posts") == 1_500_000
    assert _parse_count("2.3万 帖子") == 23_000
    payload = parse_sidecar_output(
        'dependency log\nX_BROWSER_USE_RESULT={"items":[{"kind":"trend","name":"AI"}]}'
    )
    assert payload["fallback_used"] is True
    assert payload["items"][0]["name"] == "AI"


def _raw_post(post_id):
    return {
        "href": f"/author/status/{post_id}",
        "user_href": "/author",
        "display_name": "Author",
        "text": "Thread post",
        "lang": "en",
        "created_at": "2026-07-17T08:00:00Z",
        "reply_metric": "1 reply",
        "repost_metric": "2 reposts",
        "like_metric": "3 likes",
        "view_metric": "100 views",
        "group_label": "",
    }
