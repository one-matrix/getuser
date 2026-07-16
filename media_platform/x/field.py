"""Field mapping and query helpers for X API v2 payloads."""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional


SELF_SERVE_QUERY_LIMIT = 512
_HASHTAG_RE = re.compile(r"^#[\w\u0080-\uffff]{1,100}$", re.UNICODE)
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]+")


def normalize_topic_name(value: str) -> str:
    """Normalize a trend name for local deduplication without changing display text."""

    value = _CONTROL_RE.sub(" ", value or "")
    value = " ".join(value.strip().split())
    return value.casefold()


def build_topic_query(
    topic: str,
    *,
    lang: Optional[str] = None,
    include_replies: bool = True,
    max_length: int = SELF_SERVE_QUERY_LIMIT,
) -> str:
    """Build a literal recent-search query without accepting injected operators.

    A simple hashtag remains a hashtag query. Every other topic is encoded as an
    exact phrase, so strings such as ``foo) OR from:someone`` remain data rather
    than executable X search syntax.
    """

    cleaned = _CONTROL_RE.sub(" ", topic or "")
    cleaned = " ".join(cleaned.strip().split())
    if not cleaned:
        raise ValueError("topic cannot be empty")
    if len(cleaned) > 220:
        raise ValueError("topic is too long")

    if _HASHTAG_RE.fullmatch(cleaned):
        term = cleaned
    else:
        escaped = cleaned.replace("\\", "\\\\").replace('"', '\\"')
        term = f'"{escaped}"'

    filters = ["-is:retweet"]
    if not include_replies:
        filters.append("-is:reply")
    if lang:
        normalized_lang = lang.strip().lower()
        if not re.fullmatch(r"[a-z]{2,3}(?:-[a-z0-9]{2,8})?", normalized_lang):
            raise ValueError("invalid language code")
        filters.append(f"lang:{normalized_lang}")

    query = " ".join([term, *filters])
    if len(query) > max_length:
        raise ValueError(f"query exceeds {max_length} characters")
    return query


def _to_iso_string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return str(value)


def _to_timestamp_ms(value: Any) -> int:
    if value is None or value == "":
        return 0
    if isinstance(value, (int, float)):
        number = int(value)
        return number if number > 10_000_000_000 else number * 1000
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return 0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


def map_trend(trend: Mapping[str, Any], *, rank: int, region_id: Any = None) -> Dict[str, Any]:
    name = str(trend.get("trend_name") or trend.get("name") or "").strip()
    count = trend.get("tweet_count")
    return {
        "name": name,
        "display_name": name,
        "normalized_name": normalize_topic_name(name),
        "region_id": region_id,
        "rank": rank,
        "tweet_count": int(count or 0),
        "discussion_count": int(count or 0),
        "raw_payload_json": dict(trend),
    }


def _parent_post_id(references: Iterable[Mapping[str, Any]]) -> str:
    for reference in references:
        if reference.get("type") == "replied_to":
            return str(reference.get("id") or "")
    return ""


def map_post(
    post: Mapping[str, Any],
    *,
    users_by_id: Optional[Mapping[str, Mapping[str, Any]]] = None,
    source_topic_id: Any = None,
    source_query: str = "",
) -> Dict[str, Any]:
    """Map an X Post object to the internal storage vocabulary."""

    users_by_id = users_by_id or {}
    author_id = str(post.get("author_id") or "")
    author = users_by_id.get(author_id, {})
    references = list(post.get("referenced_tweets") or [])
    metrics = dict(post.get("public_metrics") or {})
    now_ms = int(time.time() * 1000)
    created_at = _to_timestamp_ms(post.get("created_at"))
    post_type = "post"
    if any(reference.get("type") == "replied_to" for reference in references):
        post_type = "reply"
    elif any(reference.get("type") == "quoted" for reference in references):
        post_type = "quote"
    elif any(reference.get("type") == "retweeted" for reference in references):
        post_type = "repost"
    return {
        "x_post_id": str(post.get("id") or ""),
        "author_x_user_id": author_id,
        "author_username": str(author.get("username") or ""),
        "author_display_name": str(author.get("name") or ""),
        "text": str(post.get("text") or ""),
        "lang": str(post.get("lang") or ""),
        "created_at_x": created_at,
        "conversation_id": str(post.get("conversation_id") or post.get("id") or ""),
        "parent_post_id": _parent_post_id(references),
        "post_type": post_type,
        "referenced_tweets_json": references,
        "public_metrics_json": metrics,
        "possibly_sensitive": bool(post.get("possibly_sensitive", False)),
        "reply_settings": str(post.get("reply_settings") or ""),
        "entities_json": dict(post.get("entities") or {}),
        "source_topic_id": source_topic_id,
        "source_query": source_query,
        "raw_payload_json": dict(post),
        "compliance_status": "active",
        "last_hydrated_at": now_ms,
        "created_at": now_ms,
        "updated_at": now_ms,
    }


def included_users(payload: Mapping[str, Any]) -> Dict[str, Mapping[str, Any]]:
    users: List[Mapping[str, Any]] = list((payload.get("includes") or {}).get("users") or [])
    return {str(user.get("id") or ""): user for user in users if user.get("id")}


def rebuild_conversation_tree(posts: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Return a deterministic nested tree using replied-to references."""

    nodes: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    for post in posts:
        post_id = str(post.get("x_post_id") or post.get("id") or "")
        if not post_id:
            continue
        node = dict(post)
        node["children"] = []
        nodes[post_id] = node
        order.append(post_id)

    roots: List[Dict[str, Any]] = []
    for post_id in order:
        node = nodes[post_id]
        parent_id = str(node.get("parent_post_id") or "")
        if parent_id and parent_id in nodes and parent_id != post_id:
            nodes[parent_id]["children"].append(node)
        else:
            roots.append(node)

    def sort_children(node: Dict[str, Any]) -> None:
        node["children"].sort(
            key=lambda item: (str(item.get("created_at_x") or ""), str(item.get("x_post_id") or ""))
        )
        for child in node["children"]:
            sort_children(child)

    for root in roots:
        sort_children(root)
    roots.sort(key=lambda item: (str(item.get("created_at_x") or ""), str(item.get("x_post_id") or "")))
    return roots


def compute_reply_eligibility(
    target_post: Mapping[str, Any],
    *,
    account_username: str,
    account_post_ids: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    """Compute the X self-serve reply eligibility and preserve the evidence."""

    username = account_username.strip().lstrip("@").casefold()
    entities = target_post.get("entities_json") or target_post.get("entities") or {}
    if isinstance(entities, str):
        entities = {}
    mentions = list((entities or {}).get("mentions") or [])
    mentioned = any(str(item.get("username") or "").casefold() == username for item in mentions)

    own_posts = {str(post_id) for post_id in (account_post_ids or [])}
    references = target_post.get("referenced_tweets_json") or target_post.get("referenced_tweets") or []
    if isinstance(references, str):
        references = []
    quoted_own_post_ids = [
        str(item.get("id") or "")
        for item in references
        if item.get("type") == "quoted" and str(item.get("id") or "") in own_posts
    ]
    eligible = bool(username and (mentioned or quoted_own_post_ids))
    return {
        "eligible": eligible,
        "explicit_mention": mentioned,
        "quoted_account_post_ids": quoted_own_post_ids,
        "account_username": username,
        "rule": "target_author_mentioned_account_or_quoted_account_post",
    }
