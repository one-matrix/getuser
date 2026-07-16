"""browser-use structured extraction sidecar for X pages."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Literal

from browser_use import Agent, Browser, ChatBrowserUse, ChatOpenAI
from pydantic import BaseModel, Field


RESULT_PREFIX = "X_BROWSER_USE_RESULT="


class ExtractedItem(BaseModel):
    kind: Literal["trend", "post", "identity"] = "post"
    name: str = ""
    post_count: int = 0
    post_id: str = ""
    username: str = ""
    display_name: str = ""
    text: str = ""
    lang: str = ""
    created_at: str = ""
    conversation_id: str = ""
    parent_post_id: str = ""
    reply_count: int = 0
    repost_count: int = 0
    like_count: int = 0
    quote_count: int = 0
    view_count: int = 0
    url: str = ""


class ExtractionResult(BaseModel):
    items: list[ExtractedItem] = Field(default_factory=list)
    blocked_reason: str = ""


def _llm(request: dict):
    model = str(request.get("model") or os.getenv("X_BROWSER_USE_MODEL") or "")
    if os.getenv("BROWSER_USE_API_KEY"):
        return ChatBrowserUse(model=model or "bu-2-0")
    api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "browser-use fallback requires BROWSER_USE_API_KEY or LLM_API_KEY/OPENAI_API_KEY"
        )
    kwargs = {"model": model or os.getenv("LLM_MODEL") or "gpt-4.1-mini", "api_key": api_key}
    if os.getenv("LLM_BASE_URL"):
        kwargs["base_url"] = os.getenv("LLM_BASE_URL")
    return ChatOpenAI(**kwargs)


def _task(request: dict) -> str:
    mode = request["mode"]
    limit = int(request.get("limit") or 20)
    return f"""
Open {request["url"]} in the existing authenticated browser and extract at most {limit}
visible X items for mode={mode}. Return only the structured schema.

Rules:
- Read only. Never like, repost, follow, reply, publish, type credentials, or change settings.
- Never attempt to solve CAPTCHA, account-access, or security challenges. If one appears,
  return no items and set blocked_reason.
- For trends return kind=trend, name, post_count when visible, and url.
- For posts return the numeric post_id from /status/<id>, author username/display name,
  text, timestamp, language, metrics, conversation/parent IDs when visible, and URL.
- For identity return one kind=identity item for the currently logged-in account.
- Do not invent missing values. Scroll only enough to reach the requested limit.
""".strip()


async def run() -> None:
    request = json.loads(sys.stdin.read())
    browser = Browser(
        cdp_url=request["cdp_url"],
        allowed_domains=["x.com", "www.x.com"],
        keep_alive=True,
        enable_default_extensions=False,
    )
    agent = Agent(
        task=_task(request),
        llm=_llm(request),
        browser=browser,
        output_model_schema=ExtractionResult,
        use_vision="auto",
        calculate_cost=True,
    )
    history = await agent.run(max_steps=max(2, min(int(request.get("max_steps") or 8), 20)))
    final = history.final_result()
    result = ExtractionResult.model_validate_json(final) if final else ExtractionResult()
    print(f"{RESULT_PREFIX}{result.model_dump_json()}", flush=True)


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
