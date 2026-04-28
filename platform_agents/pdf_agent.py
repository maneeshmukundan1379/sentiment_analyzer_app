"""
PDF aggregation agent for Sentiment Analyzer.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import re
import tempfile
import unicodedata

from fpdf import FPDF

from core.platforms import PLATFORM_ORDER
from core.formatting import CENTRAL_TIME, format_timestamp, link_label
from core.records import deserialize_records

SENTIMENT_STYLE = {
    "Positive": {"fill": (220, 252, 231), "accent": (22, 101, 52), "text": (20, 83, 45)},
    "Negative": {"fill": (254, 226, 226), "accent": (185, 28, 28), "text": (127, 29, 29)},
    "Neutral": {"fill": (226, 232, 240), "accent": (71, 85, 105), "text": (51, 65, 85)},
    "Mixed": {"fill": (254, 243, 199), "accent": (180, 83, 9), "text": (120, 53, 15)},
    "Unknown": {"fill": (243, 244, 246), "accent": (107, 114, 128), "text": (55, 65, 81)},
}
SENTIMENT_ORDER = ["Positive", "Negative", "Neutral", "Mixed", "Unknown"]
THEME_STOPWORDS = {
    "about",
    "after",
    "again",
    "also",
    "because",
    "being",
    "could",
    "from",
    "have",
    "just",
    "like",
    "more",
    "much",
    "need",
    "only",
    "over",
    "really",
    "still",
    "that",
    "their",
    "there",
    "these",
    "they",
    "this",
    "those",
    "want",
    "were",
    "what",
    "when",
    "where",
    "which",
    "with",
    "would",
    "your",
}


# Normalize text down to PDF-safe ASCII so report generation stays robust.
def _pdf_safe_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    return normalized.encode("ascii", "ignore").decode("ascii")


def _normalize_sentiment(value: object) -> str:
    clean_value = (str(value or "Unknown").strip() or "Unknown").title()
    return clean_value if clean_value in SENTIMENT_STYLE else "Unknown"


def _record_local_datetime(record: dict) -> datetime | None:
    created_utc = float(record.get("created_utc") or 0)
    if created_utc <= 0:
        return None
    return datetime.fromtimestamp(created_utc, tz=timezone.utc).astimezone(CENTRAL_TIME)


def _keyword_terms(keyword: str) -> set[str]:
    return {term.lower() for term in re.findall(r"[A-Za-z][A-Za-z0-9']+", keyword or "")}


def _record_text(record: dict) -> str:
    return " ".join(
        str(record.get(field) or "")
        for field in ("subject", "text", "response", "community", "location")
    )


def _top_themes(records: list[dict], keyword: str = "", limit: int = 8) -> list[tuple[str, int, Counter]]:
    ignored_terms = THEME_STOPWORDS.union(_keyword_terms(keyword))
    theme_counts: Counter = Counter()
    theme_sentiments: dict[str, Counter] = {}

    for record in records:
        sentiment = _normalize_sentiment(record.get("sentiment"))
        unique_terms = {
            token.lower()
            for token in re.findall(r"[A-Za-z][A-Za-z0-9']+", _record_text(record))
            if len(token) >= 4 and token.lower() not in ignored_terms
        }
        for term in unique_terms:
            theme_counts[term] += 1
            theme_sentiments.setdefault(term, Counter())[sentiment] += 1

    return [
        (theme, count, theme_sentiments[theme])
        for theme, count in sorted(theme_counts.items(), key=lambda item: (-item[1], item[0]))[:limit]
    ]


# Compute shared summary totals used by the PDF cover and section summaries.
def _summary_counts(records: list[dict]) -> tuple[int, int, Counter]:
    total_comments = sum(1 for record in records if record.get("kind") == "comment")
    total_posts = sum(1 for record in records if record.get("kind") == "post")
    sentiment_counts = Counter(_normalize_sentiment(record.get("sentiment")) for record in records)
    return total_comments, total_posts, sentiment_counts


def _platforms_in_records(records: list[dict]) -> list[str]:
    present_platforms = {str(record.get("platform") or "Unknown") for record in records}
    ordered_platforms = [platform for platform in PLATFORM_ORDER if platform in present_platforms]
    extra_platforms = sorted(present_platforms.difference(PLATFORM_ORDER))
    return ordered_platforms + extra_platforms


def _top_counter(records: list[dict], key: str, limit: int = 4) -> list[tuple[str, int]]:
    counts = Counter(str(record.get(key) or "N/A") for record in records)
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]


def _sentiment_action(sentiment: str) -> str:
    actions = {
        "Positive": "Amplify or reuse in campaign messaging.",
        "Negative": "Review quickly and route to support or community response.",
        "Neutral": "Monitor for follow-up themes.",
        "Mixed": "Clarify the issue before replying publicly.",
        "Unknown": "Review manually before action.",
    }
    return actions.get(sentiment, actions["Unknown"])


def _action_counts(records: list[dict]) -> Counter:
    return Counter(_sentiment_action(_normalize_sentiment(record.get("sentiment"))) for record in records)


def _render_sentiment_bar(pdf: FPDF, records: list[dict]) -> None:
    _, _, sentiment_counts = _summary_counts(records)
    total = max(len(records), 1)
    bar_x = pdf.l_margin
    bar_y = pdf.get_y()
    bar_w = pdf.w - pdf.l_margin - pdf.r_margin
    bar_h = 8

    pdf.set_fill_color(229, 231, 235)
    pdf.rect(bar_x, bar_y, bar_w, bar_h, style="F")
    cursor_x = bar_x
    for sentiment in SENTIMENT_ORDER:
        count = sentiment_counts.get(sentiment, 0)
        if count <= 0:
            continue
        style = SENTIMENT_STYLE[sentiment]
        segment_w = bar_w * count / total
        pdf.set_fill_color(*style["accent"])
        pdf.rect(cursor_x, bar_y, segment_w, bar_h, style="F")
        cursor_x += segment_w

    pdf.set_y(bar_y + bar_h + 4)
    pdf.set_font("Helvetica", size=8)
    for sentiment in SENTIMENT_ORDER:
        count = sentiment_counts.get(sentiment, 0)
        if count <= 0:
            continue
        style = SENTIMENT_STYLE[sentiment]
        pdf.set_fill_color(*style["accent"])
        pdf.cell(4, 4, "", fill=True)
        pdf.cell(34, 4, _pdf_safe_text(f" {sentiment} {count}"), new_x="RIGHT", new_y="TOP")
    pdf.ln(8)


def _render_horizontal_bar(
    pdf: FPDF,
    label: str,
    count: int,
    max_count: int,
    accent: tuple[int, int, int],
    *,
    label_width: int = 36,
    label_chars: int = 18,
) -> None:
    bar_x = pdf.l_margin + label_width
    bar_y = pdf.get_y() + 1
    bar_w = pdf.w - pdf.l_margin - pdf.r_margin - label_width - 18
    bar_h = 5

    pdf.set_font("Helvetica", size=9)
    pdf.cell(label_width - 2, 7, _pdf_safe_text(label[:label_chars]), new_x="RIGHT", new_y="TOP")
    pdf.set_fill_color(229, 231, 235)
    pdf.rect(bar_x, bar_y, bar_w, bar_h, style="F")
    pdf.set_fill_color(*accent)
    pdf.rect(bar_x, bar_y, bar_w * count / max(max_count, 1), bar_h, style="F")
    pdf.set_xy(bar_x + bar_w + 3, pdf.get_y())
    pdf.cell(12, 7, str(count), align="R", new_x="LMARGIN", new_y="NEXT")


# Render the per-platform summary cards and sentiment breakdown table.
def _render_summary(pdf: FPDF, records: list[dict], title: str) -> None:
    total_comments, total_posts, sentiment_counts = _summary_counts(records)

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, _pdf_safe_text(title), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=10)
    pdf.set_draw_color(225, 230, 240)
    summary_width = (pdf.w - pdf.l_margin - pdf.r_margin - 8) / 3
    summary_items = [
        ("Total Matches", str(len(records)), (13, 39, 92), (255, 255, 255)),
        ("Comments", str(total_comments), (46, 125, 246), (255, 255, 255)),
        ("Posts", str(total_posts), (15, 118, 110), (255, 255, 255)),
    ]
    start_x = pdf.l_margin
    start_y = pdf.get_y()
    box_height = 20
    for idx, (label, value, fill_rgb, text_rgb) in enumerate(summary_items):
        x = start_x + idx * (summary_width + 4)
        pdf.set_xy(x, start_y)
        pdf.set_fill_color(*fill_rgb)
        pdf.rect(x, start_y, summary_width, box_height, style="FD")
        pdf.set_text_color(*text_rgb)
        pdf.set_xy(x, start_y + 4)
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(summary_width, 5, _pdf_safe_text(value), align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.set_xy(x, start_y + 11)
        pdf.set_font("Helvetica", size=9)
        pdf.cell(summary_width, 4, _pdf_safe_text(label), align="C")
        pdf.set_text_color(0, 0, 0)
    pdf.set_y(start_y + box_height + 6)

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Sentiment Breakdown", new_x="LMARGIN", new_y="NEXT")
    _render_sentiment_bar(pdf, records)
    pdf.set_font("Helvetica", size=10)
    for sentiment in SENTIMENT_ORDER:
        count = sentiment_counts.get(sentiment, 0)
        if count == 0:
            continue
        style = SENTIMENT_STYLE[sentiment]
        pdf.set_fill_color(*style["fill"])
        pdf.set_text_color(*style["text"])
        pdf.cell(46, 8, sentiment, border=1, fill=True)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(20, 8, str(count), border=1, align="C")
        pdf.ln(8)
    pdf.set_fill_color(232, 240, 254)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(46, 8, "Total", border=1, fill=True)
    pdf.cell(20, 8, str(len(records)), border=1, align="C")
    pdf.ln(10)


def _render_marketing_insights(pdf: FPDF, records: list[dict]) -> None:
    _, _, sentiment_counts = _summary_counts(records)
    total = max(len(records), 1)
    positive_share = round((sentiment_counts.get("Positive", 0) / total) * 100)
    negative_share = round((sentiment_counts.get("Negative", 0) / total) * 100)
    responses_ready = sum(1 for record in records if str(record.get("response") or "").strip())
    top_locations = _top_counter(records, "location", limit=3)

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Marketing Signals", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=10)

    signals = [
        f"Positive share: {positive_share}% of captured mentions.",
        f"Negative watchlist: {negative_share}% of captured mentions need review.",
        f"Reply opportunities: {responses_ready} AI-suggested responses are ready for the team.",
    ]
    if top_locations:
        location_text = ", ".join(f"{label} ({count})" for label, count in top_locations)
        signals.append(f"Top locations: {location_text}.")

    for signal in signals:
        pdf.multi_cell(0, 6, _pdf_safe_text(f"- {signal}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)


def _render_trend_chart(pdf: FPDF, records: list[dict]) -> None:
    dated_counts: dict[str, Counter] = {}
    for record in records:
        local_dt = _record_local_datetime(record)
        if not local_dt:
            continue
        label = local_dt.strftime("%b %d")
        dated_counts.setdefault(label, Counter())[_normalize_sentiment(record.get("sentiment"))] += 1

    if not dated_counts:
        pdf.set_font("Helvetica", size=10)
        pdf.multi_cell(0, 6, "Trend chart unavailable because records do not include timestamps.")
        pdf.ln(3)
        return

    rows = list(dated_counts.items())[-10:]
    max_total = max(sum(counts.values()) for _, counts in rows)

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Trend Over Time", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=9)
    pdf.cell(0, 5, "Daily mention volume with sentiment color stacked inside each bar.", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    bar_x = pdf.l_margin + 24
    bar_w = pdf.w - pdf.l_margin - pdf.r_margin - 42
    bar_h = 6
    for label, counts in rows:
        total = sum(counts.values())
        y = pdf.get_y() + 1
        pdf.set_font("Helvetica", size=8)
        pdf.cell(22, 8, _pdf_safe_text(label), new_x="RIGHT", new_y="TOP")
        pdf.set_fill_color(229, 231, 235)
        pdf.rect(bar_x, y, bar_w, bar_h, style="F")
        cursor_x = bar_x
        for sentiment in SENTIMENT_ORDER:
            count = counts.get(sentiment, 0)
            if count <= 0:
                continue
            width = (bar_w * total / max_total) * count / total
            pdf.set_fill_color(*SENTIMENT_STYLE[sentiment]["accent"])
            pdf.rect(cursor_x, y, width, bar_h, style="F")
            cursor_x += width
        pdf.set_xy(bar_x + bar_w + 3, pdf.get_y())
        pdf.cell(12, 8, str(total), align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)


def _render_theme_insights(pdf: FPDF, records: list[dict], keyword: str) -> None:
    themes = _top_themes(records, keyword)

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Top Themes and Keywords", new_x="LMARGIN", new_y="NEXT")
    if not themes:
        pdf.set_font("Helvetica", size=10)
        pdf.multi_cell(0, 6, "Theme extraction did not find enough repeated terms.")
        pdf.ln(3)
        return

    max_count = max(count for _, count, _ in themes)
    for theme, count, sentiment_counts in themes:
        dominant_sentiment = sentiment_counts.most_common(1)[0][0]
        accent = SENTIMENT_STYLE[dominant_sentiment]["accent"]
        _render_horizontal_bar(pdf, theme.title(), count, max_count, accent)

    pdf.ln(2)
    pdf.set_font("Helvetica", size=8)
    pdf.multi_cell(
        0,
        5,
        _pdf_safe_text("Bar color reflects the dominant sentiment among mentions containing that theme."),
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(3)


def _render_action_summary(pdf: FPDF, records: list[dict]) -> None:
    action_counts = _action_counts(records)
    max_count = max(action_counts.values(), default=1)

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Recommended Actions Summary", new_x="LMARGIN", new_y="NEXT")
    for action, count in sorted(action_counts.items(), key=lambda item: (-item[1], item[0])):
        accent = (15, 118, 110)
        if "Review quickly" in action:
            accent = SENTIMENT_STYLE["Negative"]["accent"]
        elif "Amplify" in action:
            accent = SENTIMENT_STYLE["Positive"]["accent"]
        elif "Clarify" in action:
            accent = SENTIMENT_STYLE["Mixed"]["accent"]
        _render_horizontal_bar(pdf, action, count, max_count, accent, label_width=76, label_chars=38)
    pdf.ln(2)

    priority_records = [
        record
        for record in records
        if _normalize_sentiment(record.get("sentiment")) in {"Negative", "Mixed"}
    ][:5]
    if priority_records:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 7, "Priority Queue", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", size=9)
        for record in priority_records:
            sentiment = _normalize_sentiment(record.get("sentiment"))
            subject = str(record.get("subject") or record.get("text") or "Untitled mention")
            pdf.multi_cell(
                0,
                5,
                _pdf_safe_text(f"- {sentiment}: {subject[:110]}"),
                new_x="LMARGIN",
                new_y="NEXT",
            )
    pdf.ln(3)


def _render_positive_quotes(pdf: FPDF, records: list[dict]) -> None:
    positive_records = [
        record
        for record in records
        if _normalize_sentiment(record.get("sentiment")) == "Positive" and str(record.get("text") or "").strip()
    ][:5]

    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Top Positive Quotes", new_x="LMARGIN", new_y="NEXT")
    if not positive_records:
        pdf.set_font("Helvetica", size=10)
        pdf.multi_cell(0, 6, "No positive quote candidates were found in this search.")
        pdf.ln(3)
        return

    for record in positive_records:
        quote = str(record.get("text") or "").strip()
        source = f"{record.get('platform', 'Unknown')} | {record.get('user_id', 'Unknown')}"
        pdf.set_fill_color(*SENTIMENT_STYLE["Positive"]["fill"])
        pdf.set_text_color(*SENTIMENT_STYLE["Positive"]["text"])
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(0, 6, _pdf_safe_text(source), fill=True, new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Helvetica", size=10)
        pdf.multi_cell(0, 6, _pdf_safe_text(f'"{quote[:260]}"'), border="LRB", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(3)


def _render_campaign_planning_page(pdf: FPDF, records: list[dict], keyword: str) -> None:
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(0, 10, "Campaign Planning Insights", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    _render_trend_chart(pdf, records)
    _render_theme_insights(pdf, records, keyword)
    _render_action_summary(pdf, records)
    _render_positive_quotes(pdf, records)


# Render the first-page platform count box below the title header.
def _render_cover_platform_counts(pdf: FPDF, records: list[dict]) -> None:
    counts = Counter(str(record.get("platform") or "Unknown") for record in records)
    labels = [(platform, counts.get(platform, 0)) for platform in _platforms_in_records(records)]
    box_x = pdf.l_margin
    box_y = pdf.get_y()
    box_w = pdf.w - pdf.l_margin - pdf.r_margin
    box_h = 24

    pdf.set_draw_color(210, 218, 230)
    pdf.set_fill_color(248, 250, 252)
    pdf.rect(box_x, box_y, box_w, box_h, style="DF", round_corners=True, corner_radius=2)

    pdf.set_xy(box_x + 4, box_y + 3)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(box_w - 8, 5, "Platform Match Counts", align="C", new_x="LMARGIN", new_y="NEXT")

    segment_w = (box_w - 8) / len(labels)
    for index, (label, value) in enumerate(labels):
        current_x = box_x + 4 + index * segment_w
        pdf.set_xy(current_x, box_y + 10)
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(segment_w, 5, str(value), align="C")
        pdf.set_xy(current_x, box_y + 16)
        pdf.set_font("Helvetica", size=9)
        pdf.cell(segment_w, 4, _pdf_safe_text(label), align="C")

    pdf.set_y(box_y + box_h + 6)


# Render each detailed record block in the PDF section body.
def _render_details(pdf: FPDF, records: list[dict]) -> None:
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Detailed Results", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=11)
    for index, record in enumerate(records):
        platform = str(record.get("platform") or "Unknown")
        current_link_label = link_label(platform)
        sentiment = _normalize_sentiment(record.get("sentiment"))
        sentiment_style = SENTIMENT_STYLE[sentiment]
        pdf.set_fill_color(*sentiment_style["accent"])
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(
            0,
            8,
            _pdf_safe_text(f"{platform} | {str(record.get('kind') or 'match').title()} | {sentiment}"),
            border=1,
            fill=True,
            new_x="LMARGIN",
            new_y="NEXT",
        )
        pdf.set_text_color(0, 0, 0)
        pdf.set_font("Helvetica", size=11)
        lines = [
            f"Username: {record.get('user_id', 'Unknown')}",
            f"Location: {record.get('location', 'N/A')}",
            f"Subject: {record.get('subject', '') or 'N/A'}",
            f"Comment: {record.get('text', '')}",
            f"Date: {format_timestamp(float(record.get('created_utc') or 0))}",
            f"Sentiment: {sentiment}",
            f"Recommended Marketing Action: {_sentiment_action(sentiment)}",
            f"{current_link_label}: {record.get('permalink', '')}",
        ]
        response_text = str(record.get("response") or "").strip()
        if response_text:
            lines.insert(-1, f"Suggested Response: {response_text}")
        for line in lines:
            clean_line = _pdf_safe_text(line.strip())
            if not clean_line:
                continue
            if clean_line.startswith(f"{current_link_label}: "):
                url = line.split(f"{current_link_label}: ", 1)[1].strip()
                pdf.set_text_color(0, 102, 204)
                pdf.multi_cell(
                    0,
                    7,
                    _pdf_safe_text(f"{current_link_label}: {url}"),
                    align="L",
                    link=url,
                    new_x="LMARGIN",
                    new_y="NEXT",
                )
                pdf.set_text_color(0, 0, 0)
            else:
                pdf.multi_cell(0, 7, clean_line, align="L", new_x="LMARGIN", new_y="NEXT")
        if index < len(records) - 1:
            y = pdf.get_y() + 1
            pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
            pdf.ln(5)


# Render one platform section on its own page.
def _render_platform_section(pdf: FPDF, platform: str, records: list[dict], *, add_page: bool = True) -> None:
    if add_page:
        pdf.add_page()
    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(0, 10, _pdf_safe_text(platform), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    if not records:
        pdf.set_font("Helvetica", size=11)
        pdf.multi_cell(0, 7, _pdf_safe_text(f"No {platform} matches found for this search."))
        return
    _render_summary(pdf, records, f"{platform} Summary")
    _render_marketing_insights(pdf, records)
    _render_details(pdf, records)


# Build the final PDF file from the serialized search results stored by the frontend.
def generate_pdf_report(records_payload: str, keyword: str = "") -> tuple[str, str | None]:
    records = deserialize_records(records_payload)
    clean_keyword = (keyword or "").strip()
    if not records:
        return "Nothing to export yet. Run a search first.", None

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_fill_color(13, 39, 92)
    pdf.set_text_color(255, 255, 255)
    pdf.rect(pdf.l_margin, 12, pdf.w - pdf.l_margin - pdf.r_margin, 24, style="F")
    pdf.set_xy(pdf.l_margin + 5, 16)
    pdf.set_font("Helvetica", "B", 17)
    title = f'Sentiment Analyzer for "{clean_keyword or "Keyword"}"'
    pdf.cell(
        pdf.w - pdf.l_margin - pdf.r_margin - 10,
        8,
        _pdf_safe_text(title),
        align="C",
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.set_x(pdf.l_margin + 5)
    pdf.set_font("Helvetica", size=10)
    pdf.cell(
        pdf.w - pdf.l_margin - pdf.r_margin - 10,
        6,
        _pdf_safe_text(datetime.now(timezone.utc).astimezone(CENTRAL_TIME).strftime("Generated on %Y-%m-%d %H:%M %Z")),
        align="C",
        new_y="NEXT",
    )
    pdf.set_text_color(0, 0, 0)
    pdf.ln(10)
    _render_cover_platform_counts(pdf, records)
    _render_summary(pdf, records, "Executive Summary")
    _render_marketing_insights(pdf, records)
    _render_campaign_planning_page(pdf, records, clean_keyword)

    for platform in _platforms_in_records(records):
        platform_records = [record for record in records if record.get("platform") == platform]
        _render_platform_section(pdf, platform, platform_records, add_page=True)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
        pdf.output(tmp_file.name)
        pdf_path = tmp_file.name

    return "PDF is ready to download.", pdf_path
