# -*- coding: utf-8 -*-
"""X browser collection and controlled official-write configuration."""

import os


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


# Official API is retained only for OAuth and the final controlled write.
X_API_BASE_URL = os.getenv("X_API_BASE_URL", "https://api.x.com")
X_WRITE_API_BASE_URL = os.getenv("X_WRITE_API_BASE_URL", X_API_BASE_URL)
X_CLIENT_ID = os.getenv("X_CLIENT_ID", "")
X_CLIENT_SECRET = os.getenv("X_CLIENT_SECRET", "")
X_REDIRECT_URI = os.getenv("X_REDIRECT_URI", "")
X_ACCESS_TOKEN = os.getenv("X_ACCESS_TOKEN", "")
X_REFRESH_TOKEN = os.getenv("X_REFRESH_TOKEN", "")

TOKEN_ENCRYPTION_KEY = os.getenv("TOKEN_ENCRYPTION_KEY", "")
X_OAUTH_STATE_TTL_SECONDS = _env_int("X_OAUTH_STATE_TTL_SECONDS", 600)

X_READ_ENABLED = _env_bool("X_READ_ENABLED", True)
X_WRITE_ENABLED = _env_bool("X_WRITE_ENABLED", False)
X_AUTO_REPLY_ENABLED = _env_bool("X_AUTO_REPLY_ENABLED", False)
X_GLOBAL_KILL_SWITCH = _env_bool("X_GLOBAL_KILL_SWITCH", True)
X_REQUIRE_HUMAN_REVIEW = _env_bool("X_REQUIRE_HUMAN_REVIEW", True)

# Browser read path. The X profile is dedicated to collection and should be
# logged in manually; no CAPTCHA or account challenge bypass is attempted.
X_BROWSER_BASE_URL = os.getenv("X_BROWSER_BASE_URL", "https://x.com").rstrip("/")
X_BROWSER_USE_CDP = _env_bool("X_BROWSER_USE_CDP", True)
X_BROWSER_HEADLESS = _env_bool("X_BROWSER_HEADLESS", False)
X_BROWSER_USER_DATA_DIR = os.getenv("X_BROWSER_USER_DATA_DIR", "")
X_BROWSER_USER_AGENT = os.getenv("X_BROWSER_USER_AGENT", "")
X_BROWSER_LOCALE = os.getenv("X_BROWSER_LOCALE", "en-US")
X_BROWSER_OPERATION_TIMEOUT_SECONDS = _env_int(
    "X_BROWSER_OPERATION_TIMEOUT_SECONDS",
    90,
)
X_BROWSER_LOCK_TIMEOUT_SECONDS = _env_int("X_BROWSER_LOCK_TIMEOUT_SECONDS", 120)
X_BROWSER_PAGE_SETTLE_MS = _env_int("X_BROWSER_PAGE_SETTLE_MS", 2500)
X_BROWSER_POST_RENDER_WAIT_MS = _env_int("X_BROWSER_POST_RENDER_WAIT_MS", 8000)
X_BROWSER_POST_RELOAD_WAIT_MS = _env_int("X_BROWSER_POST_RELOAD_WAIT_MS", 12000)
X_BROWSER_INLINE_COMPOSER_WAIT_MS = _env_int(
    "X_BROWSER_INLINE_COMPOSER_WAIT_MS",
    12000,
)
X_BROWSER_SCROLL_DELAY_MS = _env_int("X_BROWSER_SCROLL_DELAY_MS", 1200)
X_BROWSER_MAX_SCROLLS = _env_int("X_BROWSER_MAX_SCROLLS", 8)

# Optional selector-recovery sidecar. It is off by default because every
# browser-use run consumes LLM resources and current browser-use dependencies
# conflict with this project's pinned application environment.
X_BROWSER_USE_FALLBACK_ENABLED = _env_bool(
    "X_BROWSER_USE_FALLBACK_ENABLED",
    False,
)
X_BROWSER_USE_FALLBACK_COMMAND = os.getenv(
    "X_BROWSER_USE_FALLBACK_COMMAND",
    "",
)
X_BROWSER_USE_MODEL = os.getenv("X_BROWSER_USE_MODEL", "")
X_BROWSER_USE_MAX_STEPS = _env_int("X_BROWSER_USE_MAX_STEPS", 8)
X_BROWSER_USE_TIMEOUT_SECONDS = _env_int("X_BROWSER_USE_TIMEOUT_SECONDS", 180)

X_TRENDS_INTERVAL_SECONDS = _env_int("X_TRENDS_INTERVAL_SECONDS", 900)
X_MENTIONS_INTERVAL_SECONDS = _env_int("X_MENTIONS_INTERVAL_SECONDS", 180)
X_DEFAULT_WOEID = _env_int("X_DEFAULT_WOEID", 1)
X_MAX_TOPICS_PER_CYCLE = _env_int("X_MAX_TOPICS_PER_CYCLE", 5)
X_MAX_POSTS_PER_TOPIC = _env_int("X_MAX_POSTS_PER_TOPIC", 50)
X_MAX_REPLIES_PER_THREAD = _env_int("X_MAX_REPLIES_PER_THREAD", 25)

X_DAILY_CRAWLED_POST_LIMIT = _env_int(
    "X_DAILY_CRAWLED_POST_LIMIT",
    _env_int("X_DAILY_POST_READ_BUDGET", 5000),
)
X_DAILY_CRAWLED_PROFILE_LIMIT = _env_int(
    "X_DAILY_CRAWLED_PROFILE_LIMIT",
    _env_int("X_DAILY_USER_READ_BUDGET", 1000),
)
# Compatibility aliases for existing database/UI vocabulary.
X_DAILY_POST_READ_BUDGET = X_DAILY_CRAWLED_POST_LIMIT
X_DAILY_USER_READ_BUDGET = X_DAILY_CRAWLED_PROFILE_LIMIT
X_DAILY_WRITE_BUDGET = _env_int("X_DAILY_WRITE_BUDGET", 20)
try:
    X_BUDGET_ALERT_RATIO = float(os.getenv("X_BUDGET_ALERT_RATIO", "0.8"))
except (TypeError, ValueError):
    X_BUDGET_ALERT_RATIO = 0.8

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "")
LLM_TIMEOUT_SECONDS = _env_int("LLM_TIMEOUT_SECONDS", 60)
LLM_MAX_RETRIES = _env_int("LLM_MAX_RETRIES", 2)

PROCESS_ROLE = os.getenv("PROCESS_ROLE", "all").strip().lower()

# Browser trends follow the location/content setting of the logged-in profile.
# ``woeid`` is retained only for compatibility with the existing schema.
X_DEFAULT_REGIONS = [
    {
        "region_name": "Worldwide",
        "woeid": X_DEFAULT_WOEID,
        "language": "en",
        "poll_interval": X_TRENDS_INTERVAL_SECONDS,
        "enabled": True,
    }
]
