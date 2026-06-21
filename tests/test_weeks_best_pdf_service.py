from io import BytesIO

from pypdf import PdfReader
import pytest

from backend.app.services.weeks_best_pdf_service import WeeksBestPdfError, WeeksBestPdfService


def _payload():
    return {
        "status": "validated",
        "selection_type": "cluster",
        "selection_id": "42",
        "selection_label": "Graph Neural Networks",
        "week_start": "2026-06-08",
        "week_end": "2026-06-14",
        "title": "Week's Best - Graph Neural Networks",
        "editorial_lead": "This week highlights graph learning papers [S1][S2].",
        "emerging_trend": "The shared pattern is careful evaluation across graph tasks [S1].",
        "why_it_matters": "These papers provide auditable evidence for the selected topic [S1].",
        "paper_cards": [
            {
                "source_id": "S1",
                "article_id": 100,
                "title": "Robust Graph Neural Networks for Scientific Discovery",
                "one_sentence_summary": "A concise summary of the paper contribution.",
                "authors": ["Ada Lovelace", "Alan Turing"],
                "published_date": "2026-06-10",
            }
        ],
        "papers_to_watch": [
            {
                "source_id": "S2",
                "article_id": 101,
                "title": "Efficient Graph Representation Learning",
                "summary": "A useful follow-up paper to monitor.",
            }
        ],
        "sources": [
            {
                "source_id": "S1",
                "article_id": 100,
                "title": "Robust Graph Neural Networks for Scientific Discovery",
                "authors": ["Ada Lovelace", "Alan Turing"],
                "published_date": "2026-06-10",
                "source_name": "arXiv",
                "doi": "10.1234/example",
            }
        ],
        "metadata": {
            "selected_count": 1,
            "candidate_count": 12,
            "generated_at": "2026-06-15T09:00:00",
        },
    }


def test_weeks_best_pdf_renderer_outputs_readable_pdf():
    filename, pdf_bytes = WeeksBestPdfService().render(_payload())

    assert filename == "weeks_best_cluster_42_2026-06-08_2026-06-14.pdf"
    assert pdf_bytes.startswith(b"%PDF")

    reader = PdfReader(BytesIO(pdf_bytes))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)

    assert "Week's Best Bulletin" in text
    assert "Graph Neural Networks" in text
    assert "Robust Graph Neural Networks for Scientific Discovery" in text
    assert "10.1234/example" in text


def test_weeks_best_pdf_renderer_rejects_non_validated_payload():
    with pytest.raises(WeeksBestPdfError):
        WeeksBestPdfService().render({"status": "failed"})
