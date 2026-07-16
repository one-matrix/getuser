import json

import httpx
import pytest

from media_platform.x.client import XApiClient
from media_platform.x.exception import (
    XConfigurationError,
    XForbiddenError,
    XRateLimitError,
)


@pytest.mark.asyncio
async def test_x_client_uses_official_endpoint_and_maps_trends():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["authorization"] = request.headers.get("authorization")
        return httpx.Response(
            200,
            json={"data": [{"trend_name": "#AI", "tweet_count": 10}]},
            headers={
                "x-rate-limit-limit": "75",
                "x-rate-limit-remaining": "74",
                "x-rate-limit-reset": "1784160000",
            },
        )

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    client = XApiClient(
        bearer_token="app-token",
        base_url="https://api.x.com",
        http_client=http_client,
    )
    result = await client.get_trends(1)
    assert result["data"][0]["trend_name"] == "#AI"
    assert seen["url"].startswith("https://api.x.com/2/trends/by/woeid/1")
    assert seen["authorization"] == "Bearer app-token"
    await http_client.aclose()


@pytest.mark.asyncio
async def test_x_client_create_reply_requires_user_context_and_exact_payload():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["authorization"] = request.headers.get("authorization")
        seen["payload"] = json.loads(request.content)
        return httpx.Response(201, json={"data": {"id": "999", "text": "Thanks"}})

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    client = XApiClient(
        bearer_token="app-token",
        user_access_token="user-token",
        http_client=http_client,
    )
    result = await client.create_reply(text="Thanks", target_post_id="123")
    assert result["data"]["id"] == "999"
    assert seen["authorization"] == "Bearer user-token"
    assert seen["payload"] == {
        "text": "Thanks",
        "reply": {"in_reply_to_tweet_id": "123"},
    }
    await http_client.aclose()


@pytest.mark.asyncio
async def test_x_client_missing_credentials_is_clear_configuration_error():
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200)))
    client = XApiClient(bearer_token="", user_access_token="", http_client=http_client)
    client.bearer_token = ""
    with pytest.raises(XConfigurationError, match="X_BEARER_TOKEN"):
        await client.get_trends(1)
    await http_client.aclose()


@pytest.mark.asyncio
async def test_x_client_maps_403_and_429():
    responses = iter(
        [
            httpx.Response(403, json={"title": "Forbidden", "detail": "scope missing"}),
            httpx.Response(
                429,
                json={"title": "Too Many Requests"},
                headers={"x-rate-limit-reset": "1784160000"},
            ),
        ]
    )
    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: next(responses))
    )
    client = XApiClient(bearer_token="token", http_client=http_client)
    with pytest.raises(XForbiddenError, match="scope missing"):
        await client.get_trends(1)
    with pytest.raises(XRateLimitError) as raised:
        await client.get_trends(1)
    assert raised.value.reset_at == 1784160000
    await http_client.aclose()
