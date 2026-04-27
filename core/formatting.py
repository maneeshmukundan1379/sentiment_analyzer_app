"""
Formatting helpers for UI and sorting.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from core.platforms import PLATFORM_LINK_LABELS, PLATFORM_ORDER, platform_list_text
from core.time_window import lookback_past_text

CENTRAL_TIME = ZoneInfo("America/Chicago")


# Render timestamps consistently for both the UI and the PDF layer.
def format_timestamp(created_utc: float) -> str:
    if not created_utc or created_utc <= 0:
        return "N/A"
    return datetime.fromtimestamp(created_utc, tz=timezone.utc).astimezone(CENTRAL_TIME).strftime("%Y-%m-%d %H:%M %Z")


# Pick the right source-link label for each platform block.
def link_label(platform: str) -> str:
    return PLATFORM_LINK_LABELS.get(platform, "Source Link")


# Convert normalized records into the multiline textbox format shown in Gradio.
def format_records_for_textbox(records: list[dict], keyword: str) -> str:
    if not records:
        return f"No {platform_list_text()} posts/comments found for '{keyword}' in the {lookback_past_text()}."

    blocks: list[str] = []
    for record in records:
        platform = str(record.get("platform") or "Unknown")
        blocks.append(
            "\n".join(
                [
                    f"Platform: {platform}",
                    f"User ID: {record.get('user_id', 'Unknown')}",
                    f"Location: {record.get('location', 'N/A')}",
                    f"Subject: {record.get('subject', '') or 'N/A'}",
                    f"Comment: {record['text']}",
                    f"Sentiment: {record.get('sentiment', 'Unknown')}",
                    f"Date: {format_timestamp(float(record.get('created_utc') or 0))}",
                    f"{link_label(platform)}: {record.get('permalink', '')}",
                ]
            )
        )
    return "\n\n".join(blocks)


# Remove duplicate records while preserving the first occurrence of each id.
def dedupe_records(records: list[dict]) -> list[dict]:
    deduped: list[dict] = []
    seen_ids: set[str] = set()
    for record in records:
        message_id = str(record.get("message_id") or "")
        if not message_id or message_id in seen_ids:
            continue
        deduped.append(record)
        seen_ids.add(message_id)
    return deduped


# Order records by recency first, then by platform and stable id.
def sort_records(records: list[dict]) -> list[dict]:
    platform_rank = {platform: index for index, platform in enumerate(PLATFORM_ORDER)}
    return sorted(
        records,
        key=lambda item: (
            -float(item.get("created_utc") or 0),
            platform_rank.get(str(item.get("platform") or ""), len(platform_rank)),
            str(item.get("message_id") or ""),
        ),
    )


# Summarize how many normalized records came from each platform.
def platform_counts(records: list[dict]) -> Counter:
    return Counter(str(record.get("platform") or "Unknown") for record in records)
