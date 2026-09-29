from __future__ import annotations

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from .data import WATERSHED_NAME, WATERSHED_DISTRICT


def build_report(path: str, class_stats: dict, change_stats: dict, hotspots: list, evidence_counts: dict):
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("TitleX", parent=styles["Title"], textColor=colors.HexColor("#12406b"))
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], textColor=colors.HexColor("#1e7d32"))
    body = styles["BodyText"]

    doc = SimpleDocTemplate(path, pagesize=A4, topMargin=1.5 * cm, bottomMargin=1.5 * cm)
    story = []

    story.append(Paragraph("GeoWatershed AI — Watershed Decision Report", title_style))
    story.append(Paragraph("SIH 2026 · Problem Statement 26015 · Geospatial Intelligence for Watershed Development", body))
    story.append(Spacer(1, 0.6 * cm))

    story.append(Paragraph("1. Area of Interest", h2))
    story.append(Paragraph(f"<b>Watershed:</b> {WATERSHED_NAME}", body))
    story.append(Paragraph(f"<b>Location:</b> {WATERSHED_DISTRICT}", body))
    story.append(Spacer(1, 0.4 * cm))

    story.append(Paragraph("2. Field Evidence Summary", h2))
    story.append(Paragraph(
        f"{evidence_counts.get('total', 0)} geo-coded images submitted by field teams, "
        f"of which {evidence_counts.get('valid', 0)} passed coordinate/metadata validation "
        f"and {evidence_counts.get('invalid', 0)} were flagged for review.", body))
    story.append(Spacer(1, 0.4 * cm))

    story.append(Paragraph("3. Current Land / Water / Vegetation Composition", h2))
    data = [["Class", "Coverage (%)"]] + [[k, f"{v}%"] for k, v in class_stats.items()]
    t = Table(data, colWidths=[9 * cm, 4 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#12406b")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.4 * cm))

    story.append(Paragraph("4. Change Detection (Before vs. After)", h2))
    story.append(Paragraph(
        f"Net vegetation change: <b>{change_stats.get('veg_change_pct', 0):+.2f}%</b> of AOI area. "
        f"Degraded area detected: <b>{change_stats.get('degraded_pct', 0):.2f}%</b> of AOI area. "
        f"Water extent change: <b>{change_stats.get('water_change_pct', 0):+.2f}%</b>.", body))
    story.append(Spacer(1, 0.4 * cm))

    story.append(Paragraph("5. Priority Intervention Zones (Hotspots)", h2))
    if hotspots:
        rows = [["Rank", "Lat", "Lon", "Severity", "Priority Score", "Recommended Action"]]
        for h in hotspots:
            rows.append([
                h["rank"], f"{h['lat']:.4f}", f"{h['lon']:.4f}",
                f"{h['severity']:.3f}", f"{h['priority_score']:.3f}", h["recommended_action"],
            ])
        t2 = Table(rows, colWidths=[1.3 * cm, 2.3 * cm, 2.3 * cm, 2.3 * cm, 2.8 * cm, 5.5 * cm])
        t2.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#c9622a")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
        ]))
        story.append(t2)
    else:
        story.append(Paragraph("No significant degradation hotspots detected in this analysis window.", body))

    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph("6. Recommendation", h2))
    story.append(Paragraph(
        "Prioritise field verification and watershed interventions (check-dams, contour trenching, "
        "afforestation) at the ranked hotspots above. Re-run this analysis on the next satellite pass "
        "to monitor intervention outcomes over time.", body))

    doc.build(story)
    return path
