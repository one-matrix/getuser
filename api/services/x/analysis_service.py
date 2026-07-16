"""Deterministic thread analysis used directly or as an LLM fallback."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any, Dict, Iterable, List, Mapping

from .policy_service import character_ngram_similarity, scan_content_risk


PROMPT_VERSION = "x-thread-analysis-v1"
MODEL_VERSION = "deterministic-local-v1"

_POSITIVE = {"good", "great", "love", "helpful", "thanks", "excellent", "喜欢", "很好", "感谢", "有用"}
_NEGATIVE = {"bad", "hate", "broken", "problem", "angry", "worse", "失败", "糟糕", "问题", "生气", "失望"}


def input_hash(posts: Iterable[Mapping[str, Any]]) -> str:
    stable = [
        {
            "id": str(post.get("x_post_id") or post.get("id") or ""),
            "text": str(post.get("text") or ""),
        }
        for post in posts
    ]
    encoded = json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def select_representative_posts(
    posts: Iterable[Mapping[str, Any]],
    *,
    max_samples: int = 25,
    duplicate_threshold: float = 0.86,
) -> List[Dict[str, Any]]:
    candidates = [dict(post) for post in posts if str(post.get("text") or "").strip()]
    candidates.sort(key=_engagement, reverse=True)
    selected: List[Dict[str, Any]] = []
    for post in candidates:
        if any(
            character_ngram_similarity(str(post.get("text") or ""), str(item.get("text") or ""))
            >= duplicate_threshold
            for item in selected
        ):
            continue
        selected.append(post)
        if len(selected) >= max_samples:
            break
    return selected


def analyze_thread(
    posts: Iterable[Mapping[str, Any]],
    *,
    topic: str = "",
    max_samples: int = 25,
) -> Dict[str, Any]:
    all_posts = [dict(post) for post in posts]
    samples = select_representative_posts(all_posts, max_samples=max_samples)
    sentiments = Counter(_sentiment(str(post.get("text") or "")) for post in samples)
    dominant = sentiments.most_common(1)[0][0] if sentiments else "neutral"

    risk_categories: Counter[str] = Counter()
    injection_count = 0
    for post in samples:
        risk = scan_content_risk(str(post.get("text") or ""))
        risk_categories.update(risk["categories"])
        injection_count += int(risk["prompt_injection_signal"])

    viewpoints: List[Dict[str, Any]] = []
    for sentiment in ("negative", "neutral", "positive"):
        group = [post for post in samples if _sentiment(str(post.get("text") or "")) == sentiment]
        if not group:
            continue
        representative = group[0]
        viewpoints.append(
            {
                "viewpoint": _shorten(str(representative.get("text") or ""), 180),
                "sentiment": sentiment,
                "sample_share_estimate": round(len(group) / max(len(samples), 1), 3),
                "representative_post_ids": [
                    str(post.get("x_post_id") or post.get("id") or "") for post in group[:3]
                ],
            }
        )

    questions = [
        _shorten(str(post.get("text") or ""), 180)
        for post in samples
        if "?" in str(post.get("text") or "") or "？" in str(post.get("text") or "")
    ][:5]
    risks = [{"category": name, "sample_count": count} for name, count in risk_categories.most_common()]
    if injection_count:
        risks.append({"category": "prompt_injection_signal", "sample_count": injection_count})

    summary = (
        f"已分析 {len(samples)} 条代表性样本"
        f"（线程内共读取 {len(all_posts)} 条）；样本主导情绪为 {dominant}。"
    )
    recommendation = "monitor_only" if risk_categories else "human_review"
    return {
        "topic": topic,
        "summary": summary,
        "dominant_sentiment": dominant,
        "sentiment_distribution": dict(sentiments),
        "main_viewpoints": viewpoints,
        "common_questions": questions,
        "misinformation_risks": risks,
        "brand_opportunity": "仅在能直接回答用户问题且不需要未经核验事实时参与。",
        "reply_recommendation": recommendation,
        "sample_count": len(samples),
        "total_post_count": len(all_posts),
        "input_content_hash": input_hash(all_posts),
        "model_version": MODEL_VERSION,
        "prompt_version": PROMPT_VERSION,
        "schema_version": "v1",
    }


def _engagement(post: Mapping[str, Any]) -> int:
    metrics = post.get("public_metrics_json") or post.get("public_metrics") or {}
    if isinstance(metrics, str):
        try:
            metrics = json.loads(metrics)
        except ValueError:
            metrics = {}
    return sum(int((metrics or {}).get(key) or 0) for key in ("like_count", "reply_count", "retweet_count", "quote_count"))


def _sentiment(text: str) -> str:
    lowered = text.casefold()
    positive = sum(1 for word in _POSITIVE if word in lowered)
    negative = sum(1 for word in _NEGATIVE if word in lowered)
    if positive > negative:
        return "positive"
    if negative > positive:
        return "negative"
    return "neutral"


def _shorten(text: str, limit: int) -> str:
    normalized = " ".join(text.strip().split())
    return normalized if len(normalized) <= limit else normalized[: limit - 1] + "…"
