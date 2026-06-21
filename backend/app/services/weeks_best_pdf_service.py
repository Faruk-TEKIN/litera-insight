from __future__ import annotations

from datetime import datetime
from html import escape
from io import BytesIO
from pathlib import Path
import re

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


class WeeksBestPdfError(ValueError):
    pass


class WeeksBestPdfService:
    def render(self, bulletin_payload: dict) -> tuple[str, bytes]:
        if bulletin_payload.get("status") != "validated":
            raise WeeksBestPdfError("Only validated Week's Best bulletins can be rendered as PDF.")

        buffer = BytesIO()
        filename = self.filename(bulletin_payload)
        font_regular, font_bold = _register_fonts()
        styles = _styles(font_regular, font_bold)

        document = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=1.65 * cm,
            leftMargin=1.65 * cm,
            topMargin=1.55 * cm,
            bottomMargin=1.5 * cm,
            title=bulletin_payload.get("title") or "Week's Best Bulletin",
            author="AcademicAI",
        )
        story = self._story(bulletin_payload, styles)
        document.build(
            story,
            onFirstPage=self._footer,
            onLaterPages=self._footer,
        )
        return filename, buffer.getvalue()

    def filename(self, bulletin_payload: dict) -> str:
        raw = "_".join(
            [
                "weeks_best",
                str(bulletin_payload.get("selection_type") or "topic"),
                str(bulletin_payload.get("selection_id") or "selection"),
                str(bulletin_payload.get("week_start") or "start"),
                str(bulletin_payload.get("week_end") or "end"),
            ]
        )
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw).strip("_")
        return f"{safe}.pdf"

    def _story(self, payload: dict, styles: dict[str, ParagraphStyle]) -> list:
        metadata = payload.get("metadata") or {}
        generated_at = _format_datetime(metadata.get("generated_at"))
        paper_cards = payload.get("paper_cards") or []
        sources = payload.get("sources") or []
        papers_to_watch = payload.get("papers_to_watch") or []

        story: list = [
            Paragraph("Week's Best Bulletin", styles["kicker"]),
            Paragraph(_text(payload.get("selection_label") or payload.get("title") or "Selected topic"), styles["title"]),
            Paragraph(
                _text(f"{payload.get('week_start') or 'Unknown start'} - {payload.get('week_end') or 'Unknown end'}"),
                styles["subtitle"],
            ),
            Spacer(1, 0.3 * cm),
            self._metadata_table(payload, metadata, generated_at, styles),
            Spacer(1, 0.45 * cm),
            HRFlowable(width="100%", thickness=0.7, color=colors.HexColor("#d1d5db")),
            Spacer(1, 0.35 * cm),
            *_section("Editorial Lead", payload.get("editorial_lead"), styles),
            *_section("Emerging Trend", payload.get("emerging_trend"), styles),
            *_section("Why It Matters", payload.get("why_it_matters"), styles),
        ]

        if paper_cards:
            story.extend([Paragraph("Top Papers", styles["section"]), Spacer(1, 0.12 * cm)])
            for index, card in enumerate(paper_cards[:5], start=1):
                story.extend(self._paper_card(index, card, styles))

        story.extend([Paragraph("Papers to Watch", styles["section"]), Spacer(1, 0.12 * cm)])
        if papers_to_watch:
            for item in papers_to_watch:
                story.append(
                    Paragraph(
                        f"<b>{_text(item.get('title'))}</b><br/>{_text(item.get('summary'))} {_citation(item.get('source_id'))}",
                        styles["body"],
                    )
                )
                story.append(Spacer(1, 0.12 * cm))
        else:
            story.append(Paragraph("No additional papers to watch were selected for this week.", styles["body"]))

        story.append(PageBreak())
        story.append(Paragraph("Sources", styles["titleSmall"]))
        story.append(Spacer(1, 0.2 * cm))
        if sources:
            for source in sources:
                story.extend(self._source_entry(source, styles))
        else:
            story.append(Paragraph("No source metadata is available for this bulletin.", styles["body"]))
        return story

    def _metadata_table(self, payload: dict, metadata: dict, generated_at: str, styles: dict[str, ParagraphStyle]) -> Table:
        data = [
            ["Selection", _text(payload.get("selection_label") or "Unknown")],
            ["Date range", _text(f"{payload.get('week_start')} - {payload.get('week_end')}")],
            ["Selected papers", str(metadata.get("selected_count") or len(payload.get("paper_cards") or []))],
            ["Candidates reviewed", str(metadata.get("candidate_count") or 0)],
            ["Generated", generated_at],
        ]
        table = Table(
            [[Paragraph(label, styles["metaLabel"]), Paragraph(value, styles["metaValue"])] for label, value in data],
            colWidths=[3.5 * cm, 12.0 * cm],
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                    ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#d1d5db")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e5e7eb")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        return table

    def _paper_card(self, index: int, card: dict, styles: dict[str, ParagraphStyle]) -> list:
        title = _text(card.get("title") or f"Paper {index}")
        summary = _text(card.get("one_sentence_summary") or card.get("summary") or "")
        authors = ", ".join(card.get("authors") or ["Unknown authors"])
        published = card.get("published_date") or "Unknown date"
        source_id = card.get("source_id")
        return [
            Paragraph(f"{index}. {title} {_citation(source_id)}", styles["paperTitle"]),
            Paragraph(_text(summary), styles["body"]),
            Paragraph(_text(f"{authors} - {published}"), styles["muted"]),
            Spacer(1, 0.22 * cm),
        ]

    def _source_entry(self, source: dict, styles: dict[str, ParagraphStyle]) -> list:
        authors = ", ".join(source.get("authors") or ["Unknown authors"])
        locator = source.get("doi") or source.get("pdf_url") or source.get("external_url") or "No DOI or URL"
        title = source.get("title") or "Untitled source"
        source_id = source.get("source_id") or "S?"
        metadata = " - ".join(
            [
                authors,
                source.get("source_name") or "Unknown source",
                source.get("published_date") or "Unknown date",
            ]
        )
        return [
            Paragraph(f"[{_text(source_id)}] {_text(title)}", styles["sourceTitle"]),
            Paragraph(_text(metadata), styles["muted"]),
            Paragraph(_text(locator), styles["url"]),
            Spacer(1, 0.18 * cm),
        ]

    @staticmethod
    def _footer(canvas, document) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(document.leftMargin, 0.85 * cm, "AcademicAI - Week's Best Bulletin")
        canvas.drawRightString(A4[0] - document.rightMargin, 0.85 * cm, f"Page {document.page}")
        canvas.restoreState()


def _section(title: str, body: str | None, styles: dict[str, ParagraphStyle]) -> list:
    return [
        Paragraph(title, styles["section"]),
        Spacer(1, 0.12 * cm),
        Paragraph(_paragraph_text(body or "No content available."), styles["body"]),
        Spacer(1, 0.32 * cm),
    ]


def _register_fonts() -> tuple[str, str]:
    candidates = [
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ("/Library/Fonts/Arial Unicode.ttf", "/Library/Fonts/Arial Unicode.ttf"),
        ("/System/Library/Fonts/Supplemental/Arial Unicode.ttf", "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
    ]
    for regular_path, bold_path in candidates:
        if Path(regular_path).exists() and Path(bold_path).exists():
            pdfmetrics.registerFont(TTFont("AcademicSans", regular_path))
            pdfmetrics.registerFont(TTFont("AcademicSans-Bold", bold_path))
            return "AcademicSans", "AcademicSans-Bold"
    return "Helvetica", "Helvetica-Bold"


def _styles(font_regular: str, font_bold: str) -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "kicker": ParagraphStyle(
            "Kicker",
            parent=base["Normal"],
            fontName=font_bold,
            fontSize=9,
            leading=11,
            textColor=colors.HexColor("#059669"),
            alignment=TA_CENTER,
            spaceAfter=6,
        ),
        "title": ParagraphStyle(
            "Title",
            parent=base["Title"],
            fontName=font_bold,
            fontSize=20,
            leading=25,
            textColor=colors.HexColor("#0f172a"),
            alignment=TA_CENTER,
            spaceAfter=8,
        ),
        "titleSmall": ParagraphStyle(
            "TitleSmall",
            parent=base["Heading1"],
            fontName=font_bold,
            fontSize=18,
            leading=22,
            textColor=colors.HexColor("#0f172a"),
        ),
        "subtitle": ParagraphStyle(
            "Subtitle",
            parent=base["Normal"],
            fontName=font_regular,
            fontSize=10,
            leading=13,
            textColor=colors.HexColor("#475569"),
            alignment=TA_CENTER,
        ),
        "section": ParagraphStyle(
            "Section",
            parent=base["Heading2"],
            fontName=font_bold,
            fontSize=13,
            leading=16,
            textColor=colors.HexColor("#065f46"),
            spaceBefore=8,
        ),
        "paperTitle": ParagraphStyle(
            "PaperTitle",
            parent=base["Heading3"],
            fontName=font_bold,
            fontSize=10.5,
            leading=13,
            textColor=colors.HexColor("#111827"),
            spaceBefore=4,
        ),
        "sourceTitle": ParagraphStyle(
            "SourceTitle",
            parent=base["Normal"],
            fontName=font_bold,
            fontSize=9.2,
            leading=11.5,
            textColor=colors.HexColor("#111827"),
        ),
        "body": ParagraphStyle(
            "Body",
            parent=base["BodyText"],
            fontName=font_regular,
            fontSize=9.7,
            leading=13.2,
            textColor=colors.HexColor("#1f2937"),
            spaceAfter=5,
        ),
        "muted": ParagraphStyle(
            "Muted",
            parent=base["Normal"],
            fontName=font_regular,
            fontSize=8.2,
            leading=10.5,
            textColor=colors.HexColor("#64748b"),
        ),
        "url": ParagraphStyle(
            "Url",
            parent=base["Normal"],
            fontName=font_regular,
            fontSize=7.7,
            leading=9.5,
            textColor=colors.HexColor("#2563eb"),
            splitLongWords=True,
        ),
        "metaLabel": ParagraphStyle(
            "MetaLabel",
            parent=base["Normal"],
            fontName=font_bold,
            fontSize=8.5,
            leading=10,
            textColor=colors.HexColor("#475569"),
        ),
        "metaValue": ParagraphStyle(
            "MetaValue",
            parent=base["Normal"],
            fontName=font_regular,
            fontSize=8.5,
            leading=10,
            textColor=colors.HexColor("#111827"),
        ),
    }


def _text(value: object) -> str:
    return escape(str(value or "").strip())


def _paragraph_text(value: object) -> str:
    return _text(value).replace("\n", "<br/>")


def _citation(source_id: object) -> str:
    return f"[{_text(source_id)}]" if source_id else ""


def _format_datetime(value: object) -> str:
    if not value:
        return "Unknown"
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)
