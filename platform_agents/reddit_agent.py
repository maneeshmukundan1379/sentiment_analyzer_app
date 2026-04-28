"""
Reddit search agent for Sentiment Analyzer.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
import re
from urllib.parse import urlparse

import requests

from core.config import (
    REDDIT_COMMENT_TREE_WORKERS,
    REDDIT_USER_AGENT,
)
from core.platforms import REDDIT_PLATFORM
from core.records import make_record, make_reddit_comment_record, make_reddit_post_record
from core.text_utils import clean_text, contains_exact_keyword
from core.time_window import cutoff_utc_timestamp, reddit_time_filter
from core.web_search import combined_text_search, path_parts


# Fetch Reddit listing JSON with a stable user agent and timeout.
def _reddit_get_json(url: str, params: dict | None = None) -> dict:
    with requests.get(
        url,
        params=params or {},
        headers={
            "User-Agent": REDDIT_USER_AGENT,
            "Accept": "application/json,text/plain,*/*",
            "Accept-Language": "en-US,en;q=0.9",
        },
        timeout=30,
    ) as response:
        response.raise_for_status()
        return response.json()


def _is_reddit_url(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return host.endswith("reddit.com")


def _reddit_permalink(url: str) -> str:
    parsed = urlparse(url)
    return f"https://www.reddit.com{parsed.path}"


def _reddit_submission_permalink(url: str) -> str:
    """Map a comment or post URL to the parent submission (strip trailing comment id)."""
    p = _reddit_permalink(url)
    parts = path_parts(p)
    if "comments" in parts and len(parts) >= 6:
        return f"https://www.reddit.com/{'/'.join(parts[:5])}/"
    return p


def _reddit_kind(url: str) -> str:
    parts = path_parts(url)
    return "comment" if "comments" in parts and len(parts) >= 6 else "post"


def _reddit_subreddit_from_path(url: str) -> str:
    parts = path_parts(_reddit_permalink(url))
    if len(parts) >= 2 and parts[0] == "r":
        return f"r/{parts[1]}"
    return ""


def _reddit_username_from_serp(title: str, body: str) -> str:
    """Best-effort author from search title/snippet (web fallback when JSON is blocked)."""
    combined = f"{title}\n{body}"
    for pattern in (
        r"(?:Posted by|posted by)\s+[uU]/([\w\-]{2,40})\b",
        r"\b[uU]/([\w\-]{2,40})\b",
        r"reddit\.com/user/([\w\-]{2,40})\b",
    ):
        match = re.search(pattern, combined, re.IGNORECASE)
        if match:
            return match.group(1)
    return "Unknown"


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


# Fall back to time-filtered public web snippets when Reddit blocks cloud JSON requests.
def _search_reddit_with_web_discovery(keyword: str) -> list[dict]:
    results: list[dict] = []
    # Track any permalink we already emit (per-link); also mark submission URL when
    # we return a post so a later result for the same thread does not duplicate it.
    seen_urls: set[str] = set()
    seen_post_urls: set[str] = set()
    for item in combined_text_search(
        [
            f'site:reddit.com/r "{keyword}"',
            f'"{keyword}" site:reddit.com',
            f'site:reddit.com/r/*/comments "{keyword}"',
        ]
    ):
        url = str(item.get("href") or "")
        if not _is_reddit_url(url):
            continue
        permalink = _reddit_permalink(url)
        if permalink in seen_urls:
            continue
        subject = clean_text(str(item.get("title") or ""))
        text = clean_text(str(item.get("body") or ""), subject)
        if not text or not contains_exact_keyword(text, keyword):
            continue
        sub_url = _reddit_submission_permalink(permalink)
        kind = _reddit_kind(permalink)
        created_utc = _parse_relative_time_to_timestamp(
            str(item.get("body") or ""),
            str(item.get("title") or ""),
        )
        community = _reddit_subreddit_from_path(permalink) or "Reddit"
        user_from_serp = _reddit_username_from_serp(subject, text)

        def _add_row(
            *,
            row_permalink: str,
            kind_val: str,
            body_text: str,
            subj: str,
        ) -> None:
            results.append(
                make_record(
                    platform=REDDIT_PLATFORM,
                    message_id=f"reddit_web_{row_permalink}",
                    kind=kind_val,
                    created_utc=created_utc,
                    user_id=user_from_serp,
                    community=community,
                    subject=subj[:140],
                    text=body_text,
                    permalink=row_permalink,
                )
            )
            seen_urls.add(row_permalink)
            if kind_val == "post":
                seen_post_urls.add(row_permalink)

        if kind == "post":
            if sub_url in seen_post_urls:
                continue
            _add_row(
                row_permalink=sub_url,
                kind_val="post",
                body_text=text,
                subj=subject,
            )
            continue

        # Comment hit: if the result title (usually the post title in SERP) matches,
        # also return a submission row for the same thread; JSON API may be blocked.
        if sub_url not in seen_post_urls and contains_exact_keyword(subject, keyword):
            _add_row(
                row_permalink=sub_url,
                kind_val="post",
                body_text=clean_text(subject) or text,
                subj=subject,
            )
        if permalink in seen_urls:
            continue
        _add_row(
            row_permalink=permalink,
            kind_val="comment",
            body_text=text,
            subj=subject,
        )
    return results


# Search Reddit submissions globally and keep only recent keyword matches.
def _search_posts(keyword: str, cutoff_utc: float) -> list[dict]:
    records: list[dict] = []
    after: str | None = None
    seen_ids: set[str] = set()
    seen_after_tokens: set[str | None] = set()
    while after not in seen_after_tokens:
        seen_after_tokens.add(after)
        payload = _reddit_get_json(
            "https://www.reddit.com/search.json",
            params={
                "q": keyword,
                "sort": "new",
                "t": reddit_time_filter(),
                "type": "link",
                "raw_json": 1,
                "after": after,
            },
        )
        children = payload.get("data", {}).get("children", [])
        if not children:
            break
        for child in children:
            if child.get("kind") != "t3":
                continue
            data = child.get("data", {})
            created_utc = float(data.get("created_utc") or 0)
            if created_utc < cutoff_utc:
                continue
            body = clean_text(str(data.get("title") or ""), str(data.get("selftext") or ""))
            if not body or not contains_exact_keyword(body, keyword):
                continue
            message_id = f"t3_{data.get('id')}"
            if message_id in seen_ids:
                continue
            records.append(make_reddit_post_record(data, body))
            seen_ids.add(message_id)
        after = payload.get("data", {}).get("after")
        if not after:
            break
    return records


# Search Reddit's global comment index and keep both comments and submission fallbacks.
def _search_comments_globally(keyword: str, cutoff_utc: float) -> tuple[list[dict], list[dict]]:
    comments: list[dict] = []
    fallback_posts: list[dict] = []
    seen_comment_ids: set[str] = set()
    seen_post_ids: set[str] = set()
    after: str | None = None
    seen_after_tokens: set[str | None] = set()
    while after not in seen_after_tokens:
        seen_after_tokens.add(after)
        payload = _reddit_get_json(
            "https://www.reddit.com/search.json",
            params={
                "q": keyword,
                "sort": "new",
                "t": reddit_time_filter(),
                "type": "comment",
                "raw_json": 1,
                "after": after,
            },
        )
        children = payload.get("data", {}).get("children", [])
        if not children:
            break
        for child in children:
            kind = child.get("kind")
            data = child.get("data", {})
            created_utc = float(data.get("created_utc") or 0)
            if created_utc < cutoff_utc:
                continue
            if kind == "t1":
                body = clean_text(str(data.get("body") or ""))
                if not body or not contains_exact_keyword(body, keyword):
                    continue
                message_id = f"t1_{data.get('id')}"
                if message_id in seen_comment_ids:
                    continue
                comments.append(make_reddit_comment_record(data, body))
                seen_comment_ids.add(message_id)
            elif kind == "t3":
                body = clean_text(str(data.get("title") or ""), str(data.get("selftext") or ""))
                if not body or not contains_exact_keyword(body, keyword):
                    continue
                message_id = f"t3_{data.get('id')}"
                if message_id in seen_post_ids:
                    continue
                fallback_posts.append(make_reddit_post_record(data, body))
                seen_post_ids.add(message_id)
        after = payload.get("data", {}).get("after")
        if not after:
            break
    return comments, fallback_posts


# Walk nested Reddit comment nodes recursively to collect matching replies.
def _extract_matching_comments_from_nodes(nodes: list[dict], keyword: str, cutoff_utc: float, subject: str) -> list[dict]:
    matches: list[dict] = []
    for child in nodes:
        if child.get("kind") != "t1":
            continue
        data = child.get("data", {})
        body = clean_text(str(data.get("body") or ""))
        created_utc = float(data.get("created_utc") or 0)
        if body and created_utc >= cutoff_utc and contains_exact_keyword(body, keyword):
            matches.append(make_reddit_comment_record(data, body, subject))

        replies = data.get("replies")
        if isinstance(replies, dict):
            reply_nodes = replies.get("data", {}).get("children", [])
            matches.extend(_extract_matching_comments_from_nodes(reply_nodes, keyword, cutoff_utc, subject))
    return matches


# Fetch a post's comment tree and return only recent keyword-matching comments.
def _extract_matching_comments(post_permalink: str, keyword: str, cutoff_utc: float, subject: str) -> list[dict]:
    listing = _reddit_get_json(
        f"https://www.reddit.com{post_permalink}.json",
        params={"sort": "new", "raw_json": 1},
    )
    if len(listing) < 2:
        return []
    return _extract_matching_comments_from_nodes(
        listing[1].get("data", {}).get("children", []), keyword, cutoff_utc, subject
    )


# Combine Reddit post and comment discovery into one normalized result set.
def search_keyword(keyword: str) -> list[dict]:
    clean_keyword = (keyword or "").strip()
    if not clean_keyword:
        raise ValueError("Enter a keyword to search Reddit.")

    cutoff_utc = cutoff_utc_timestamp()
    all_records: list[dict] = []
    seen_ids: set[str] = set()
    try:
        posts = _search_posts(clean_keyword, cutoff_utc)
        global_comments, fallback_posts = _search_comments_globally(clean_keyword, cutoff_utc)
    except requests.HTTPError as exc:
        response = getattr(exc, "response", None)
        if response is not None and response.status_code == 403:
            return _search_reddit_with_web_discovery(clean_keyword)
        raise

    records_for_comment_trees: list[dict] = []
    for record in posts + fallback_posts:
        if record["message_id"] not in seen_ids:
            all_records.append(record)
            seen_ids.add(record["message_id"])
            records_for_comment_trees.append(record)

    max_workers = max(1, min(REDDIT_COMMENT_TREE_WORKERS, len(records_for_comment_trees)))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for record in records_for_comment_trees:
            post_path = record["permalink"].replace("https://www.reddit.com", "")
            futures[
                executor.submit(
                    _extract_matching_comments,
                    post_path,
                    clean_keyword,
                    cutoff_utc,
                    record.get("subject", ""),
                )
            ] = record
        for future in as_completed(futures):
            try:
                comments = future.result()
                for comment in comments:
                    if comment["message_id"] not in seen_ids:
                        all_records.append(comment)
                        seen_ids.add(comment["message_id"])
            except Exception:
                continue

    for comment in global_comments:
        if comment["message_id"] not in seen_ids:
            all_records.append(comment)
            seen_ids.add(comment["message_id"])

    return all_records
