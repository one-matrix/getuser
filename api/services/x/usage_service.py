"""Browser crawl-volume and official write budget primitives."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Mapping

from config import x_config


@dataclass
class BudgetStatus:
    allowed: bool
    used: int
    limit: int
    remaining: int
    alert: bool
    exhausted: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def utc_usage_date() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def evaluate_budget(used: int, limit: int, requested: int = 1, *, alert_ratio: float | None = None) -> BudgetStatus:
    used, limit, requested = max(int(used), 0), max(int(limit), 0), max(int(requested), 0)
    alert_ratio = float(alert_ratio if alert_ratio is not None else x_config.X_BUDGET_ALERT_RATIO)
    if limit == 0:
        return BudgetStatus(True, used, 0, -1, False, False)
    remaining = max(limit - used, 0)
    exhausted = requested > remaining
    return BudgetStatus(
        allowed=not exhausted,
        used=used,
        limit=limit,
        remaining=remaining,
        alert=(used + requested) / limit >= max(0.0, min(alert_ratio, 1.0)),
        exhausted=exhausted,
    )


def configured_budgets() -> Dict[str, int]:
    return {
        "post_reads": int(x_config.X_DAILY_CRAWLED_POST_LIMIT),
        "user_reads": int(x_config.X_DAILY_CRAWLED_PROFILE_LIMIT),
        "writes": int(x_config.X_DAILY_WRITE_BUDGET),
    }


def rate_limit_event(headers: Mapping[str, Any], *, status_code: int, endpoint: str) -> Dict[str, Any]:
    def number(name: str) -> int:
        try:
            return int(headers.get(name) or 0)
        except (TypeError, ValueError):
            return 0

    return {
        "endpoint": endpoint,
        "limit_total": number("x-rate-limit-limit"),
        "remaining": number("x-rate-limit-remaining"),
        "reset_at": number("x-rate-limit-reset") * 1000,
        "last_http_status": int(status_code),
    }
