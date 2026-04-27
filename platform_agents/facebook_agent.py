"""
Facebook pages and groups search agent for Sentiment Analyzer.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from core.platforms import FACEBOOK_PLATFORM
from core.records import make_facebook_comment_record, make_facebook_record, make_record
from core.text_utils import clean_text, contains_exact_keyword
from core.time_window import cutoff_utc_timestamp
from core.web_search import combined_text_search, path_parts

try:
    from facebook_scraper import get_posts
except ImportError:  # pragma: no cover - optional dependency
    get_posts = None


# Try browser-backed cookies first, then a public fallback path.
def _facebook_cookie_candidates() -> list[object | None]:
    return ["from_browser", None]


def _close_post_stream(post_stream: object) -> None:
    close = getattr(post_stream, "close", None)
    if callable(close):
        close()


# Limit discovery and scraping to Facebook-owned hosts.
def _is_facebook_url(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return host.endswith("facebook.com") or host.endswith("fb.com")


# Pull a group slug or id from a discovered Facebook group URL.
def _parse_group_name_from_facebook_url(url: str) -> str:
    parts = path_parts(url)
    if "groups" in parts:
        group_index = parts.index("groups")
        if group_index + 1 < len(parts):
            return parts[group_index + 1]
    return "Facebook"


# Pull a page identifier from a discovered Facebook page URL.
def _parse_page_name_from_facebook_url(url: str) -> str:
    parts = path_parts(url)
    if not parts:
        return "Facebook Page"
    if parts[0] == "profile.php":
        return urlparse(url).query or "Facebook Page"
    return parts[0]


# Extract the group id or slug needed for facebook-scraper group requests.
def _extract_facebook_group_id(url: str) -> str:
    parts = path_parts(url)
    if "groups" not in parts:
        return ""
    group_index = parts.index("groups")
    if group_index + 1 >= len(parts):
        return ""
    candidate = parts[group_index + 1].strip()
    if candidate.lower() in {"posts", "about", "members", "media", "files", "events"}:
        return ""
    return candidate


# Extract the page account id or slug for facebook-scraper page requests.
def _extract_facebook_page_id(url: str) -> str:
    parts = path_parts(url)
    if not parts or "groups" in parts:
        return ""
    first = parts[0].strip()
    if not first:
        return ""
    if first.lower() in {
        "posts",
        "about",
        "people",
        "photo",
        "photos",
        "watch",
        "videos",
        "events",
        "marketplace",
        "reel",
        "reels",
        "share",
        "hashtag",
        "search",
        "login",
        "plugins",
        "business",
        "help",
        "privacy",
        "stories",
    }:
        return ""
    return first


# Walk scraped Facebook comments and keep only keyword-matching comments and replies.
def _extract_matching_facebook_comments(
    post: dict,
    keyword: str,
    community_name: str,
    seen_ids: set[str],
) -> list[dict]:
    results: list[dict] = []
    subject = clean_text(str(post.get("title") or ""), str(post.get("text") or ""), str(post.get("post_text") or ""))[:140]
    post_url = str(post.get("post_url") or "")
    stack = list(post.get("comments_full") or [])

    while stack:
        comment = stack.pop(0)
        if not isinstance(comment, dict):
            continue
        text = clean_text(
            str(comment.get("comment_text") or ""),
            str(comment.get("text") or ""),
            str(comment.get("body") or ""),
        )
        if text and contains_exact_keyword(text, keyword):
            record = make_facebook_comment_record(
                comment,
                source_id=community_name,
                community_name=community_name,
                post_url=post_url,
                subject=subject,
            )
            if record is not None and record["message_id"] not in seen_ids:
                results.append(record)
                seen_ids.add(record["message_id"])
        replies = comment.get("replies") or comment.get("comments") or comment.get("comment_replies") or []
        if isinstance(replies, list):
            stack.extend(reply for reply in replies if isinstance(reply, dict))

    return results


# Turn relative snippet phrases like "1h" or "2 days" into timestamps.
def _parse_relative_time_to_timestamp(*parts: str) -> float:
    text = " ".join(part for part in parts if part).lower()
    if not text:
        return 0

    if "yesterday" in text:
        return (datetime.now(timezone.utc) - timedelta(days=1)).timestamp()

    match = re.search(
        r"\b(\d+)\s*(m|min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days|w|week|weeks)\b",
        text,
    )
    if match is None:
        return 0

    amount = int(match.group(1))
    unit = match.group(2)
    if unit.startswith(("m", "min")):
        delta = timedelta(minutes=amount)
    elif unit.startswith(("h", "hr", "hour")):
        delta = timedelta(hours=amount)
    elif unit.startswith(("d", "day")):
        delta = timedelta(days=amount)
    else:
        delta = timedelta(weeks=amount)
    return (datetime.now(timezone.utc) - delta).timestamp()


# Discover candidate Facebook groups and pages from public search results.
def _discover_facebook_entities(keyword: str) -> tuple[list[str], list[str]]:
    query_results = combined_text_search(
        [
            f'site:facebook.com/groups "{keyword}"',
            f'site:facebook.com "{keyword}"',
            f'"{keyword}" site:facebook.com',
        ]
    )
    discovered_groups: list[str] = []
    discovered_pages: list[str] = []
    seen_groups: set[str] = set()
    seen_pages: set[str] = set()

    for item in query_results:
        url = str(item.get("href") or "")
        if not _is_facebook_url(url):
            continue

        group_id = _extract_facebook_group_id(url)
        if group_id and group_id not in seen_groups:
            discovered_groups.append(group_id)
            seen_groups.add(group_id)

        page_id = _extract_facebook_page_id(url)
        if page_id and page_id not in seen_pages:
            discovered_pages.append(page_id)
            seen_pages.add(page_id)

    return discovered_groups, discovered_pages


# Scrape discovered Facebook groups and include matching posts plus matching comments.
def _search_discovered_facebook_groups(keyword: str, cutoff_utc: float, group_ids: list[str]) -> list[dict]:
    if get_posts is None or not group_ids:
        return []

    results: list[dict] = []
    seen_ids: set[str] = set()
    for group_id in group_ids:
        for cookies in _facebook_cookie_candidates():
            try:
                post_kwargs = {"group": group_id}
                if cookies is not None:
                    post_kwargs["cookies"] = cookies
                post_kwargs["options"] = {"comments": True}
                post_stream = get_posts(**post_kwargs)
            except Exception:
                continue
            try:
                for post in post_stream:
                    community_name = str(post.get("page_name") or post.get("group") or group_id or "Facebook Group")
                    record = make_facebook_record(post, group_id, "Facebook Group")
                    if record is not None:
                        if (not record["created_utc"] or record["created_utc"] >= cutoff_utc) and contains_exact_keyword(
                            record["text"], keyword
                        ):
                            if record["message_id"] not in seen_ids:
                                results.append(record)
                                seen_ids.add(record["message_id"])
                    results.extend(_extract_matching_facebook_comments(post, keyword, community_name, seen_ids))
            finally:
                _close_post_stream(post_stream)
            if results:
                break
    return results


# Scrape discovered Facebook pages and include matching posts plus matching comments.
def _search_discovered_facebook_pages(keyword: str, cutoff_utc: float, page_ids: list[str]) -> list[dict]:
    if get_posts is None or not page_ids:
        return []

    results: list[dict] = []
    seen_ids: set[str] = set()
    for page_id in page_ids:
        for cookies in _facebook_cookie_candidates():
            try:
                post_kwargs = {"account": page_id}
                if cookies is not None:
                    post_kwargs["cookies"] = cookies
                post_kwargs["options"] = {"comments": True}
                post_stream = get_posts(**post_kwargs)
            except Exception:
                continue
            try:
                for post in post_stream:
                    community_name = str(post.get("page_name") or post.get("group") or page_id or "Facebook Page")
                    record = make_facebook_record(post, page_id, "Facebook Page")
                    if record is not None:
                        if (not record["created_utc"] or record["created_utc"] >= cutoff_utc) and contains_exact_keyword(
                            record["text"], keyword
                        ):
                            if record["message_id"] not in seen_ids:
                                results.append(record)
                                seen_ids.add(record["message_id"])
                    results.extend(_extract_matching_facebook_comments(post, keyword, community_name, seen_ids))
            finally:
                _close_post_stream(post_stream)
            if results:
                break
    return results


# Fall back to public web discovery when scraper-based Facebook access returns nothing.
def _search_facebook_with_web_discovery(keyword: str) -> list[dict]:
    results: list[dict] = []
    seen_ids: set[str] = set()
    for item in combined_text_search(
        [
            f'site:facebook.com/groups "{keyword}"',
            f'site:facebook.com "{keyword}"',
            f'"{keyword}" site:facebook.com',
        ]
    ):
        url = str(item.get("href") or "")
        if not _is_facebook_url(url):
            continue
        subject = clean_text(str(item.get("title") or ""))
        text = clean_text(str(item.get("body") or ""))
        combined = clean_text(subject, text)
        if not url or not combined or not contains_exact_keyword(combined, keyword):
            continue
        message_id = f"fb_web_{url}"
        if message_id in seen_ids:
            continue
        community_name = (
            _parse_group_name_from_facebook_url(url)
            if "/groups/" in url
            else _parse_page_name_from_facebook_url(url)
        )
        results.append(
            make_record(
                platform=FACEBOOK_PLATFORM,
                message_id=message_id,
                kind="comment" if re.search(r"\b(via|comment|comments?)\b", combined.lower()) else "post",
                created_utc=_parse_relative_time_to_timestamp(
                    str(item.get("body") or ""),
                    str(item.get("title") or ""),
                ),
                user_id="Unknown",
                community=community_name,
                subject=subject[:140],
                text=text or subject,
                permalink=url,
            )
        )
        seen_ids.add(message_id)
    return results


# Prefer scraper-based Facebook discovery, then fall back to public web snippets.
def search_keyword(keyword: str) -> list[dict]:
    clean_keyword = (keyword or "").strip()
    if not clean_keyword:
        raise ValueError(f"Enter a keyword to search {FACEBOOK_PLATFORM}.")

    cutoff_utc = cutoff_utc_timestamp()
    group_ids, page_ids = _discover_facebook_entities(clean_keyword)
    records = _search_discovered_facebook_groups(clean_keyword, cutoff_utc, group_ids)
    records.extend(_search_discovered_facebook_pages(clean_keyword, cutoff_utc, page_ids))
    if records:
        return records
    return _search_facebook_with_web_discovery(clean_keyword)
