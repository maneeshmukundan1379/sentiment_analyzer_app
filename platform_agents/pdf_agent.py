"""
PDF aggregation agent for Sentiment Analyzer.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import tempfile
import unicodedata

from fpdf import FPDF

from core.platforms import PLATFORM_ORDER
from core.formatting import format_timestamp, link_label
from core.records import deserialize_records


# Normalize text down to PDF-safe ASCII so report generation stays robust.
def _pdf_safe_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    return normalized.encode("ascii", "ignore").decode("ascii")


# Compute shared summary totals used by the PDF cover and section summaries.
def _summary_counts(records: list[dict]) -> tuple[int, int, Counter]:
    total_comments = sum(1 for record in records if record.get("kind") == "comment")
    total_posts = sum(1 for record in records if record.get("kind") == "post")
    sentiment_counts = Counter(
        (str(record.get("sentiment") or "Unknown").strip() or "Unknown").title() for record in records
    )
    return total_comments, total_posts, sentiment_counts


def _platforms_in_records(records: list[dict]) -> list[str]:
    present_platforms = {str(record.get("platform") or "Unknown") for record in records}
    ordered_platforms = [platform for platform in PLATFORM_ORDER if platform in present_platforms]
    extra_platforms = sorted(present_platforms.difference(PLATFORM_ORDER))
    return ordered_platforms + extra_platforms


# Render the per-platform summary cards and sentiment breakdown table.
def _render_summary(pdf: FPDF, records: list[dict], title: str) -> None:
    total_comments, total_posts, sentiment_counts = _summary_counts(records)
    sentiment_order = ["Positive", "Negative", "Neutral", "Mixed", "Unknown"]

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
    pdf.cell(0, 8, "Sentiment Breakdown", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=10)
    for sentiment in sentiment_order:
        count = sentiment_counts.get(sentiment, 0)
        if count == 0:
            continue
        pdf.set_fill_color(248, 250, 252)
        pdf.cell(46, 8, sentiment, border=1, fill=True)
        pdf.cell(20, 8, str(count), border=1, align="C")
        pdf.ln(8)
    pdf.set_fill_color(232, 240, 254)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(46, 8, "Total", border=1, fill=True)
    pdf.cell(20, 8, str(len(records)), border=1, align="C")
    pdf.ln(10)


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
        pdf.set_fill_color(245, 247, 251)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(
            0,
            8,
            _pdf_safe_text(f"{platform} | {str(record.get('kind') or 'match').title()} | {record.get('sentiment', 'Unknown')}"),
            border=1,
            fill=True,
            new_x="LMARGIN",
            new_y="NEXT",
        )
        pdf.set_font("Helvetica", size=11)
        lines = [
            f"User ID: {record.get('user_id', 'Unknown')}",
            f"Location: {record.get('location', 'N/A')}",
            f"Subject: {record.get('subject', '') or 'N/A'}",
            f"Comment: {record.get('text', '')}",
            f"Date: {format_timestamp(float(record.get('created_utc') or 0))}",
            f"Sentiment: {record.get('sentiment', 'Unknown')}",
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


# Render one platform section on its own page, or reuse page one for Reddit.
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
    _render_details(pdf, records)


# Build the final PDF file from the serialized search results stored by Gradio.
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
        _pdf_safe_text(datetime.now(timezone.utc).strftime("Generated on %Y-%m-%d %H:%M UTC")),
        align="C",
        new_y="NEXT",
    )
    pdf.set_text_color(0, 0, 0)
    pdf.ln(10)
    _render_cover_platform_counts(pdf, records)

    for index, platform in enumerate(_platforms_in_records(records)):
        platform_records = [record for record in records if record.get("platform") == platform]
        _render_platform_section(pdf, platform, platform_records, add_page=index > 0)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
        pdf.output(tmp_file.name)
        pdf_path = tmp_file.name

    return "PDF is ready to download.", pdf_path
