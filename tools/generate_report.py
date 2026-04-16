#!/usr/bin/env python3
"""
Step 3: Generate a ranked shortlist PDF report from .tmp/scores.json.

Usage:
    python tools/generate_report.py
    python tools/generate_report.py --scores .tmp/scores.json --out output/

Output: output/shortlist_YYYY-MM-DD.pdf
"""
import argparse
import json
import sys
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

SCORES_FILE = Path(".tmp/scores.json")
OUTPUT_DIR = Path("output")

# ── colour palette ────────────────────────────────────────────────────────────

PRIMARY = colors.HexColor("#1A56DB")
LIGHT_BLUE = colors.HexColor("#EBF5FB")
DARK_TEXT = colors.HexColor("#1F2937")
MID_TEXT = colors.HexColor("#4B5563")
LIGHT_GREY = colors.HexColor("#F3F4F6")
BORDER = colors.HexColor("#D1D5DB")

REC_COLORS = {
    "STRONG_YES": colors.HexColor("#065F46"),   # dark green
    "YES": colors.HexColor("#1E40AF"),          # blue
    "MAYBE": colors.HexColor("#92400E"),        # amber
    "NO": colors.HexColor("#991B1B"),           # red
}

REC_BG = {
    "STRONG_YES": colors.HexColor("#D1FAE5"),
    "YES": colors.HexColor("#DBEAFE"),
    "MAYBE": colors.HexColor("#FEF3C7"),
    "NO": colors.HexColor("#FEE2E2"),
}

# ── styles ────────────────────────────────────────────────────────────────────

def build_styles():
    base = getSampleStyleSheet()
    s = {}
    s["title"] = ParagraphStyle(
        "title", parent=base["Title"],
        fontSize=22, textColor=PRIMARY, alignment=TA_CENTER,
        spaceAfter=4,
    )
    s["subtitle"] = ParagraphStyle(
        "subtitle", parent=base["Normal"],
        fontSize=11, textColor=MID_TEXT, alignment=TA_CENTER,
        spaceAfter=16,
    )
    s["section"] = ParagraphStyle(
        "section", parent=base["Heading2"],
        fontSize=13, textColor=PRIMARY,
        spaceBefore=14, spaceAfter=6,
    )
    s["body"] = ParagraphStyle(
        "body", parent=base["Normal"],
        fontSize=9, textColor=DARK_TEXT,
        leading=14,
    )
    s["small"] = ParagraphStyle(
        "small", parent=base["Normal"],
        fontSize=8, textColor=MID_TEXT,
        leading=11,
    )
    s["cand_name"] = ParagraphStyle(
        "cand_name", parent=base["Heading1"],
        fontSize=15, textColor=PRIMARY,
        spaceBefore=0, spaceAfter=2,
    )
    s["label"] = ParagraphStyle(
        "label", parent=base["Normal"],
        fontSize=8, textColor=MID_TEXT,
        leading=11,
    )
    return s


# ── score bar ─────────────────────────────────────────────────────────────────

def score_bar(score: int, width_cm: float = 5.0) -> Table:
    """Render a horizontal bar representing score/100."""
    bar_w = width_cm * cm
    fill_w = bar_w * score / 100
    empty_w = bar_w - fill_w
    colour = (
        colors.HexColor("#065F46") if score >= 80
        else colors.HexColor("#1E40AF") if score >= 65
        else colors.HexColor("#92400E") if score >= 50
        else colors.HexColor("#991B1B")
    )
    data = [["", ""]]
    t = Table(data, colWidths=[fill_w, max(empty_w, 0.1)], rowHeights=[0.35 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), colour),
        ("BACKGROUND", (1, 0), (1, 0), BORDER),
        ("LINEABOVE", (0, 0), (-1, -1), 0, colors.white),
        ("LINEBELOW", (0, 0), (-1, -1), 0, colors.white),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return t


# ── pages ─────────────────────────────────────────────────────────────────────

def summary_table(scores: list, styles: dict) -> list:
    """Return flowables for the summary ranking table."""
    elements = [Paragraph("Candidate Rankings", styles["section"])]

    headers = ["Rank", "Candidate", "Score", "Recommendation", "Email"]
    header_row = [Paragraph(f"<b>{h}</b>", styles["label"]) for h in headers]
    rows = [header_row]

    for i, s in enumerate(scores, 1):
        name = s.get("candidate_name") or s.get("source_file", "Unknown")
        rec = s.get("recommendation", "—")
        rec_cell = Paragraph(
            f'<font color="{REC_COLORS.get(rec, DARK_TEXT).hexval()}">'
            f"<b>{rec}</b></font>",
            styles["body"],
        )
        rows.append([
            Paragraph(str(i), styles["body"]),
            Paragraph(name, styles["body"]),
            Paragraph(f"<b>{s.get('overall_score', 0)}</b>", styles["body"]),
            rec_cell,
            Paragraph(s.get("email") or "—", styles["small"]),
        ])

    col_w = [1 * cm, 5.5 * cm, 1.8 * cm, 3 * cm, 5 * cm]
    t = Table(rows, colWidths=col_w, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GREY]),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(t)
    return elements


def candidate_page(s: dict, rank: int, styles: dict) -> list:
    """Return flowables for one candidate's detail page."""
    elements = [PageBreak()]

    name = s.get("candidate_name") or s.get("source_file", "Unknown")
    rec = s.get("recommendation", "—")
    score = s.get("overall_score", 0)

    # Header block
    elements.append(Paragraph(f"#{rank}  {name}", styles["cand_name"]))
    contact = "  |  ".join(filter(None, [s.get("email"), s.get("phone"), s.get("source_file")]))
    elements.append(Paragraph(contact, styles["small"]))
    elements.append(Spacer(1, 0.3 * cm))

    # Score + recommendation side by side
    rec_colour = REC_COLORS.get(rec, DARK_TEXT)
    rec_bg = REC_BG.get(rec, LIGHT_GREY)

    header_data = [[
        Paragraph(f"<b>Overall Score: {score}/100</b>", styles["body"]),
        Paragraph(
            f'<font color="{rec_colour.hexval()}"><b>{rec}</b></font>',
            ParagraphStyle("rec", fontSize=11, alignment=TA_CENTER, leading=14),
        ),
    ]]
    ht = Table(header_data, colWidths=[10 * cm, 6 * cm])
    ht.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), LIGHT_BLUE),
        ("BACKGROUND", (1, 0), (1, 0), rec_bg),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
        ("LINEAFTER", (0, 0), (0, 0), 0.5, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    elements.append(ht)
    elements.append(Spacer(1, 0.4 * cm))

    # Dimension score bars
    elements.append(Paragraph("Dimension Scores", styles["section"]))
    dim_labels = {
        "skills_match": "Skills Match",
        "experience": "Experience",
        "education": "Education",
        "communication": "Communication",
        "overall_fit": "Overall Fit",
    }
    dim_scores = s.get("dimension_scores", {})
    dim_rows = []
    for key, label in dim_labels.items():
        dim_val = dim_scores.get(key, 0)
        dim_rows.append([
            Paragraph(label, styles["body"]),
            score_bar(dim_val, width_cm=6),
            Paragraph(f"<b>{dim_val}</b>", styles["body"]),
        ])

    dim_table = Table(dim_rows, colWidths=[3.5 * cm, 6 * cm, 1.5 * cm])
    dim_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, LIGHT_GREY]),
    ]))
    elements.append(dim_table)
    elements.append(Spacer(1, 0.4 * cm))

    # Strengths & concerns
    strengths = s.get("strengths", [])
    concerns = s.get("concerns", [])

    sc_data = [[
        [Paragraph("<b>Strengths</b>", styles["body"])]
        + [Paragraph(f"• {st}", styles["body"]) for st in strengths],
        [Paragraph("<b>Concerns</b>", styles["body"])]
        + [Paragraph(f"• {cn}", styles["body"]) for cn in concerns],
    ]]
    sc_table = Table(sc_data, colWidths=[8 * cm, 8 * cm])
    sc_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#F0FDF4")),
        ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#FFF7ED")),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
        ("LINEAFTER", (0, 0), (0, 0), 0.5, BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    elements.append(sc_table)
    elements.append(Spacer(1, 0.4 * cm))

    # Summary narrative
    summary = s.get("summary", "")
    if summary:
        elements.append(Paragraph("Summary", styles["section"]))
        elements.append(Paragraph(summary, styles["body"]))

    elements.append(HRFlowable(width="100%", thickness=0.5, color=BORDER, spaceAfter=6))
    return elements


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a ranked shortlist PDF from scores JSON."
    )
    parser.add_argument(
        "--scores", default=str(SCORES_FILE),
        help=f"Path to scores JSON (default: {SCORES_FILE})"
    )
    parser.add_argument(
        "--out", default=str(OUTPUT_DIR),
        help=f"Output directory (default: {OUTPUT_DIR})"
    )
    parser.add_argument(
        "--job", default="config/job_description.json",
        help="Path to job_description.json (for report title)"
    )
    args = parser.parse_args()

    scores_path = Path(args.scores)
    if not scores_path.exists():
        print(f"ERROR: {scores_path} not found. Run score_candidates.py first.", file=sys.stderr)
        sys.exit(1)

    scores = json.loads(scores_path.read_text(encoding="utf-8"))
    if not scores:
        print("No scores found in file.", file=sys.stderr)
        sys.exit(1)

    job_title = "Open Role"
    job_path = Path(args.job)
    if job_path.exists():
        job_title = json.loads(job_path.read_text(encoding="utf-8")).get("role_title", job_title)

    output_dir = Path(args.out)
    output_dir.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    pdf_path = output_dir / f"shortlist_{today}.pdf"

    styles = build_styles()

    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    story = []

    # Cover / summary
    story.append(Spacer(1, 1 * cm))
    story.append(Paragraph("Resume Screening Report", styles["title"]))
    story.append(Paragraph(f"Role: {job_title}  ·  {today}  ·  {len(scores)} candidate(s)", styles["subtitle"]))
    story.append(HRFlowable(width="100%", thickness=1, color=PRIMARY, spaceAfter=12))
    story += summary_table(scores, styles)

    # Per-candidate detail pages
    for i, s in enumerate(scores, 1):
        story += candidate_page(s, i, styles)

    doc.build(story)
    print(f"Report saved: {pdf_path}")


if __name__ == "__main__":
    main()
