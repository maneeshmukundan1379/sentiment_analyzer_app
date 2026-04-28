"""
Normalized social record helpers.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from core.platforms import FACEBOOK_PLATFORM, REDDIT_PLATFORM, X_PLATFORM
from core.text_utils import clean_text


# Build the normalized record shape used across the whole app.
def make_record(
    *,
    platform: str,
    message_id: str,
    kind: str,
    created_utc: float,
    user_id: str,
    community: str,
    subject: str,
    text: str,
    permalink: str,
    location_hint: str = "",
) -> dict:
    return {
        "message_id": message_id,
        "platform": platform,
        "kind": kind,
        "created_utc": float(created_utc or 0),
        "user_id": user_id or "Unknown",
        "community": community or "",
        "subject": subject or "",
        "text": text,
        "permalink": permalink or "",
        "location_hint": location_hint or "",
        "sentiment": "Unknown",
        "location": "N/A",
        "response": "",
    }


def _reddit_display_author(data: dict) -> str:
    """Prefer Reddit username string over internal author_fullname (t2_*)."""
    author = data.get("author")
    if isinstance(author, str) and author.strip() and author.strip() != "[deleted]":
        return author.strip()
    fullname = data.get("author_fullname")
    if isinstance(fullname, str) and fullname.strip():
        return fullname.strip()
    return "[deleted]"


# Normalize Reddit submission payloads into the shared record format.
def make_reddit_post_record(data: dict, body: str) -> dict:
    subject = clean_text(str(data.get("title") or ""))
    return make_record(
        platform=REDDIT_PLATFORM,
        message_id=f"t3_{data.get('id')}",
        kind="post",
        created_utc=float(data.get("created_utc") or 0),
        user_id=_reddit_display_author(data),
        community=str(data.get("subreddit_name_prefixed") or ""),
        subject=subject,
        text=body,
        permalink=f"https://www.reddit.com{data.get('permalink', '')}",
        location_hint=str(data.get("author_flair_text") or ""),
    )


# Normalize Reddit comment payloads into the shared record format.
def make_reddit_comment_record(data: dict, body: str, subject: str = "") -> dict:
    clean_subject = clean_text(subject or str(data.get("link_title") or ""))
    return make_record(
        platform=REDDIT_PLATFORM,
        message_id=f"t1_{data.get('id')}",
        kind="comment",
        created_utc=float(data.get("created_utc") or 0),
        user_id=_reddit_display_author(data),
        community=str(data.get("subreddit_name_prefixed") or ""),
        subject=clean_subject,
        text=body,
        permalink=f"https://www.reddit.com{data.get('permalink', '')}",
        location_hint=str(data.get("author_flair_text") or ""),
    )


# Normalize X API or scraper records into the shared record format.
def make_x_record(tweet: object, text: str, created_utc: float) -> dict:
    user = getattr(tweet, "user", None)
    username = getattr(user, "username", "") or "unknown"
    location_hint = getattr(user, "location", "") or ""
    raw_subject = getattr(tweet, "renderedContent", "") or getattr(tweet, "rawContent", "") or text
    subject = clean_text(raw_subject)[:140] or f"Post by @{username}"
    kind = "comment" if getattr(tweet, "inReplyToTweetId", None) else "post"
    return make_record(
        platform=X_PLATFORM,
        message_id=f"x_{getattr(tweet, 'id', '')}",
        kind=kind,
        created_utc=created_utc,
        user_id=f"@{username}",
        community=f"@{username}",
        subject=subject,
        text=text,
        permalink=str(getattr(tweet, "url", "") or ""),
        location_hint=location_hint,
    )


# Convert datetime objects from scraper payloads into UTC timestamps.
def _timestamp_from_datetime(value: object) -> float:
    if not isinstance(value, datetime):
        return 0
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).timestamp()


# Normalize Facebook post payloads from scraper output.
def make_facebook_record(post: dict, source_id: str, community_fallback: str = "Facebook") -> dict | None:
    text = clean_text(
        str(post.get("text") or ""),
        str(post.get("post_text") or ""),
        str(post.get("shared_text") or ""),
    )
    if not text:
        return None

    timestamp = float(post.get("timestamp") or 0)
    if not timestamp:
        timestamp = _timestamp_from_datetime(post.get("time"))

    username = str(post.get("username") or post.get("user_id") or "Unknown")
    post_url = str(post.get("post_url") or "")
    community_name = str(post.get("page_name") or post.get("group") or source_id or community_fallback)
    subject = clean_text(str(post.get("title") or ""), text[:140])[:140]
    post_id = str(post.get("post_id") or post_url or username)

    return make_record(
        platform=FACEBOOK_PLATFORM,
        message_id=f"fb_{post_id}",
        kind="post",
        created_utc=timestamp,
        user_id=username,
        community=community_name,
        subject=subject,
        text=text,
        permalink=post_url,
    )


# Normalize Facebook comment payloads so comments can be handled like other records.
def make_facebook_comment_record(
    comment: dict,
    source_id: str,
    community_name: str,
    post_url: str = "",
    subject: str = "",
) -> dict | None:
    text = clean_text(
        str(comment.get("comment_text") or ""),
        str(comment.get("text") or ""),
        str(comment.get("body") or ""),
    )
    if not text:
        return None

    timestamp = float(comment.get("comment_timestamp") or comment.get("timestamp") or 0)
    if not timestamp:
        timestamp = _timestamp_from_datetime(comment.get("comment_time"))
    if not timestamp:
        timestamp = _timestamp_from_datetime(comment.get("time"))

    user_id = str(
        comment.get("commenter_name")
        or comment.get("author_name")
        or comment.get("username")
        or comment.get("commenter_id")
        or comment.get("author_id")
        or "Unknown"
    )
    comment_url = str(comment.get("comment_url") or comment.get("permalink") or post_url or "")
    comment_id = str(comment.get("comment_id") or comment_url or user_id)

    return make_record(
        platform=FACEBOOK_PLATFORM,
        message_id=f"fb_comment_{comment_id}",
        kind="comment",
        created_utc=timestamp,
        user_id=user_id,
        community=community_name or source_id,
        subject=clean_text(subject or text[:140])[:140],
        text=text,
        permalink=comment_url,
    )


# Serialize normalized records for storage in Gradio state.
def serialize_records(records: list[dict]) -> str:
    return json.dumps(records, ensure_ascii=False)


# Recover normalized records from the serialized Gradio payload.
def deserialize_records(payload: str) -> list[dict]:
    raw = (payload or "").strip()
    if not raw:
        return []
    data = json.loads(raw)
    return data if isinstance(data, list) else []
