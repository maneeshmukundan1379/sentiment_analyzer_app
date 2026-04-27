"""
Configuration helpers for Sentiment Analyzer.
"""

from __future__ import annotations

import os

from core.env import load_app_env

# Load environment variables before computing module-level settings.
load_app_env()

# Keep shared HTTP identity and runtime switches in one place.
REDDIT_USER_AGENT = (
    os.getenv("REDDIT_USER_AGENT")
    or "Mozilla/5.0 (compatible; sentiment-analyzer-app/1.0; +https://github.com/maneeshmukundan1379/sentiment_analyzer_app)"
).strip()


# Parse integer environment values while falling back safely on bad input.
def safe_int_env(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


# Accept only positive integer overrides for optional limits.
def optional_positive_int_env(name: str) -> int | None:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value > 0 else None


# Expose the effective app configuration as module-level constants.
LOOKBACK_DAYS = 7
REDDIT_COMMENT_TREE_WORKERS = safe_int_env("REDDIT_COMMENT_TREE_WORKERS", 5)
AI_BATCH_SIZE = safe_int_env("AI_BATCH_SIZE", 20)
AI_BATCH_WORKERS = safe_int_env("AI_BATCH_WORKERS", 3)
X_API_BASE_URL = (os.getenv("X_API_BASE_URL") or "https://api.x.com/2").strip().rstrip("/")
X_BEARER_TOKEN = (os.getenv("X_BEARER_TOKEN") or "").strip()
