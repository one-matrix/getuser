"""Deterministic topic and Post ranking primitives."""

from __future__ import annotations

import math
import time
from typing import Any, Dict, Iterable, List, Mapping


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def minmax_normalize(values: Iterable[float]) -> List[float]:
    items = [float(value or 0) for value in values]
    if not items:
        return []
    low, high = min(items), max(items)
    if high <= low:
        return [0.0 if high == 0 else 1.0 for _ in items]
    return [(value - low) / (high - low) for value in items]


def calculate_hot_score(metrics: Mapping[str, Any]) -> float:
    """Calculate the design-document HotScore using normalized inputs."""

    score = (
        0.25 * clamp(metrics.get("volume_velocity", 0))
        + 0.20 * clamp(metrics.get("rank_velocity", 0))
        + 0.15 * clamp(metrics.get("unique_authors", 0))
        + 0.15 * clamp(metrics.get("reply_scale", 0))
        + 0.10 * clamp(metrics.get("repost_scale", 0))
        + 0.10 * clamp(metrics.get("brand_relevance", 0))
        + 0.05 * clamp(metrics.get("author_quality", 0))
        - clamp(metrics.get("risk_penalty", 0))
    )
    return round(clamp(score), 6)


def calculate_post_score(
    hot_score: float,
    created_at_ms: int,
    *,
    now_ms: int | None = None,
    half_life_hours: float = 8.0,
) -> float:
    now_ms = now_ms or int(time.time() * 1000)
    age_hours = max(0.0, (now_ms - int(created_at_ms or now_ms)) / 3_600_000)
    return round(clamp(hot_score) * math.exp(-age_hours / max(half_life_hours, 0.1)), 6)


def rank_topics(topics: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    ranked: List[Dict[str, Any]] = []
    for topic in topics:
        item = dict(topic)
        item["hot_score"] = calculate_hot_score(item)
        ranked.append(item)
    ranked.sort(key=lambda item: (-item["hot_score"], str(item.get("normalized_name") or "")))
    return ranked
