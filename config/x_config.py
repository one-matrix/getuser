# -*- coding: utf-8 -*-
"""X official API configuration.

X integration intentionally uses only the official API. Browser automation,
cookies, CDP, proxy rotation, and other non-API access methods are not used.
All write-related switches default to the safest state.
"""

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


X_API_BASE_URL = os.getenv("X_API_BASE_URL", "https://api.x.com")
X_BEARER_TOKEN = os.getenv("X_BEARER_TOKEN", "")
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

X_TRENDS_INTERVAL_SECONDS = _env_int("X_TRENDS_INTERVAL_SECONDS", 900)
X_MENTIONS_INTERVAL_SECONDS = _env_int("X_MENTIONS_INTERVAL_SECONDS", 180)
X_DEFAULT_WOEID = _env_int("X_DEFAULT_WOEID", 1)
X_MAX_TOPICS_PER_CYCLE = _env_int("X_MAX_TOPICS_PER_CYCLE", 5)
X_MAX_POSTS_PER_TOPIC = _env_int("X_MAX_POSTS_PER_TOPIC", 50)
X_MAX_REPLIES_PER_THREAD = _env_int("X_MAX_REPLIES_PER_THREAD", 25)

X_DAILY_POST_READ_BUDGET = _env_int("X_DAILY_POST_READ_BUDGET", 5000)
X_DAILY_USER_READ_BUDGET = _env_int("X_DAILY_USER_READ_BUDGET", 1000)
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

# Initial read-only regions. Operators can add or override regions in the DB.
# WOEID 1 represents worldwide.
X_DEFAULT_REGIONS = [
    {
        "region_name": "Worldwide",
        "woeid": X_DEFAULT_WOEID,
        "language": "en",
        "poll_interval": X_TRENDS_INTERVAL_SECONDS,
        "enabled": True,
    }
]
