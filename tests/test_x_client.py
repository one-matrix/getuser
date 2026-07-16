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
