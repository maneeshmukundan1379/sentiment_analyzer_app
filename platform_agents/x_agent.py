"""
X.com search agent for Sentiment Analyzer.
"""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlparse

import requests

from core.config import X_API_BASE_URL, X_BEARER_TOKEN
from core.records import make_record
from core.platforms import X_PLATFORM
from core.text_utils import clean_text, contains_exact_keyword
from core.time_window import cutoff_utc_timestamp
from core.web_search import combined_text_search, path_parts

# Keep the latest X warning so the UI can describe when fallback was used.
_LAST_WARNING: str | None = None


# Pull the account handle out of a canonical X/Twitter status URL.
def _parse_username_from_x_url(url: str) -> str:
    parts = path_parts(url)
    return f"@{parts[0]}" if parts else "Unknown"


# Expose the latest X warning to the orchestration layer.
def get_last_warning() -> str | None:
    return _LAST_WARNING


# Normalize hostnames so mobile and www variants share one validation path.
def _normalized_x_host(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.").removeprefix("mobile.")


# Accept only genuine X/Twitter status links as valid post URLs.
def _is_x_status_url(url: str) -> bool:
    parsed = urlparse(url)
    host = _normalized_x_host(url)
    if host not in {"x.com", "twitter.com"}:
        return False

    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 3:
        return False
    if parts[1] != "status":
        return False
    return parts[2].isdigit()


# Convert X API timestamps into UTC epoch seconds for shared formatting.
def _parse_api_timestamp(created_at: str) -> float:
    raw = (created_at or "").strip()
    if not raw:
        return 0
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc).timestamp()
    except ValueError:
        return 0


# Treat replied-to tweets as comments in the normalized result model.
def _looks_like_reply(tweet: dict) -> bool:
    if tweet.get("in_reply_to_user_id"):
        return True
    for item in tweet.get("referenced_tweets") or []:
        if str(item.get("type") or "") == "replied_to":
            return True
    return False


# Build a stable X permalink from the username and tweet id.
def _canonical_x_permalink(username: str, tweet_id: str) -> str:
    handle = (username or "").lstrip("@").strip()
    if not handle or not tweet_id:
        return ""
    return f"https://x.com/{handle}/status/{tweet_id}"


# Map raw X API payloads into the shared app record format.
def _map_x_api_tweet(tweet: dict, users_by_id: dict[str, dict]) -> dict | None:
    tweet_id = str(tweet.get("id") or "").strip()
    text = clean_text(str(tweet.get("text") or ""))
    if not tweet_id or not text:
        return None

    author_id = str(tweet.get("author_id") or "")
    user = users_by_id.get(author_id, {})
    username = str(user.get("username") or "").strip()
    user_id = f"@{username}" if username else "Unknown"
    subject = text[:140] or f"Post by {user_id}"

    return make_record(
        platform=X_PLATFORM,
        message_id=f"x_{tweet_id}",
        kind="comment" if _looks_like_reply(tweet) else "post",
        created_utc=_parse_api_timestamp(str(tweet.get("created_at") or "")),
        user_id=user_id,
        community=user_id if user_id != "Unknown" else "",
        subject=subject,
        text=text,
        permalink=_canonical_x_permalink(username, tweet_id),
        location_hint=str(user.get("location") or ""),
    )


# Query the official X recent-search API and normalize exact keyword matches.
def _search_x_with_api(keyword: str, cutoff_utc: float) -> list[dict]:
    if not X_BEARER_TOKEN:
        return []

    records: list[dict] = []
    seen_ids: set[str] = set()
    next_token: str | None = None
    seen_tokens: set[str | None] = set()
    safe_keyword = keyword.replace('"', '\\"')
    query = f'"{safe_keyword}" -is:retweet'
    start_time = datetime.fromtimestamp(cutoff_utc, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    while next_token not in seen_tokens:
        seen_tokens.add(next_token)
        params = {
            "query": query,
            "max_results": 100,
            "start_time": start_time,
            "tweet.fields": "created_at,author_id,conversation_id,in_reply_to_user_id,referenced_tweets",
            "expansions": "author_id",
            "user.fields": "username,location,name",
        }
        if next_token:
            params["next_token"] = next_token

        with requests.get(
            f"{X_API_BASE_URL}/tweets/search/recent",
            headers={"Authorization": f"Bearer {X_BEARER_TOKEN}"},
            params=params,
            timeout=30,
        ) as response:
            response.raise_for_status()
            payload = response.json()
        tweets = payload.get("data") or []
        if not tweets:
            break

        users = payload.get("includes", {}).get("users") or []
        users_by_id = {str(user.get("id") or ""): user for user in users}

        for tweet in tweets:
            record = _map_x_api_tweet(tweet, users_by_id)
            if record is None:
                continue
            if record["created_utc"] and record["created_utc"] < cutoff_utc:
                continue
            if not contains_exact_keyword(record["text"], keyword):
                continue
            if not _is_x_status_url(record["permalink"]):
                continue
            if record["message_id"] in seen_ids:
                continue
            records.append(record)
            seen_ids.add(record["message_id"])

        next_token = payload.get("meta", {}).get("next_token")
        if not next_token:
            break

    return records


# Fall back to public search results and keep only strict status links.
def _search_x_with_duckduckgo(keyword: str) -> list[dict]:
    results: list[dict] = []
    seen_ids: set[str] = set()
    queries = [
        f'site:x.com "{keyword}"',
        f'site:twitter.com "{keyword}"',
        f'"{keyword}" "x.com"',
        f'"{keyword}" "twitter.com"',
    ]
    for item in combined_text_search(queries):
        url = str(item.get("href") or "")
        if not _is_x_status_url(url):
            continue
        text = clean_text(str(item.get("body") or ""))
        subject = clean_text(str(item.get("title") or ""))
        combined = clean_text(subject, text)
        if not url or not combined or not contains_exact_keyword(combined, keyword):
            continue
        message_id = f"x_web_{url}"
        if message_id in seen_ids:
            continue
        username = _parse_username_from_x_url(url)
        results.append(
            make_record(
                platform=X_PLATFORM,
                message_id=message_id,
                kind="post",
                created_utc=0,
                user_id=username,
                community=username,
                subject=subject[:140],
                text=text or subject,
                permalink=url,
            )
        )
        seen_ids.add(message_id)
    return results


# Prefer the official X API and only fall back to public search when necessary.
def search_keyword(keyword: str) -> list[dict]:
    global _LAST_WARNING

    clean_keyword = (keyword or "").strip()
    if not clean_keyword:
        raise ValueError(f"Enter a keyword to search {X_PLATFORM}.")

    _LAST_WARNING = None
    cutoff_utc = cutoff_utc_timestamp()
    results: list[dict] = []
    api_error: str | None = None

    if X_BEARER_TOKEN:
        try:
            results = _search_x_with_api(clean_keyword, cutoff_utc)
        except Exception as exc:
            api_error = str(exc)
            results = []
    else:
        api_error = "X API unavailable because X_BEARER_TOKEN is not configured"

    if not results:
        results = _search_x_with_duckduckgo(clean_keyword)
        if results and api_error:
            _LAST_WARNING = f"{api_error}; used public X status-link fallback"
        elif api_error:
            _LAST_WARNING = f"{api_error}; public X status-link fallback returned no matches"

    return results
