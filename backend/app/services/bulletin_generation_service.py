from __future__ import annotations

import json

from backend.app.services.bulletin_candidate_service import BulletinSelection
from backend.app.services.ollama_service import OllamaServiceError, get_ollama_service


GENERATION_VERSION = "weeks_best_v1"
PROMPT_VERSION = "weeks_best_editor_v1"


class BulletinGenerationService:
    def __init__(self, use_llm: bool = False):
        self.use_llm = use_llm
        self.ollama = get_ollama_service()

    def generate(self, selection: BulletinSelection, cards: list[dict], top_count: int = 5) -> dict:
        top_cards = cards[:top_count]
        watch_cards = cards[top_count:]
        markdown = ""
        if self.use_llm and cards:
            try:
                markdown = self.ollama.generate(_writer_prompt(selection, top_cards, watch_cards)).strip()
            except (OllamaServiceError, RuntimeError):
                markdown = ""
        if not markdown:
            markdown = _deterministic_markdown(selection, top_cards, watch_cards)

        return {
            "title": f"Week's Best - {selection.selection_label}",
            "editorial_lead": _editorial_lead(top_cards),
            "emerging_trend": _emerging_trend(top_cards),
            "why_it_matters": _why_it_matters(selection, top_cards),
            "papers_to_watch": [
                {
                    "source_id": card["source_id"],
                    "article_id": card["article_id"],
                    "title": card["title"],
                    "summary": card["one_sentence_summary"],
                }
                for card in watch_cards
            ],
            "full_markdown": markdown,
        }


def _writer_prompt(selection: BulletinSelection, top_cards: list[dict], watch_cards: list[dict]) -> str:
    return f"""
You are an academic bulletin editor.

Write a concise weekly academic bulletin using only the provided paper cards.

Rules:
- Use only the provided paper cards.
- Do not invent papers, links, authors, methods, results, or claims.
- Every important claim must cite one or more source IDs such as [S1].
- The Editorial Lead and Emerging Trend sections must cite multiple sources when making synthesis claims.
- Keep the tone academic, clear, concise, and newspaper-like.
- Avoid hype words such as "revolutionary", "groundbreaking", or "game-changing".
- Preserve exact paper titles.
- If evidence is limited, say so clearly.

Required structure:
# Week's Best - {selection.selection_label}

**Date range:** {selection.week_start.date().isoformat()} - {selection.week_end.date().isoformat()}

## Editorial Lead
...

## Top Papers
...

## Emerging Trend
...

## Why It Matters
...

## Papers to Watch
...

## Sources
...

Paper cards:
{json.dumps({"top_papers": top_cards, "papers_to_watch": watch_cards}, ensure_ascii=False, indent=2)}
""".strip()


def _deterministic_markdown(selection: BulletinSelection, top_cards: list[dict], watch_cards: list[dict]) -> str:
    lines = [
        f"# Week's Best - {selection.selection_label}",
        "",
        f"**Date range:** {selection.week_start.date().isoformat()} - {selection.week_end.date().isoformat()}",
        "",
        "## Editorial Lead",
        "",
        _editorial_lead(top_cards),
        "",
        "## Top Papers",
        "",
    ]
    for index, card in enumerate(top_cards, start=1):
        lines.extend(
            [
                f"### {index}. {card['title']}",
                "",
                f"{card['one_sentence_summary']} [{card['source_id']}]",
                "",
            ]
        )
    lines.extend(["## Emerging Trend", "", _emerging_trend(top_cards), "", "## Why It Matters", "", _why_it_matters(selection, top_cards), ""])
    lines.extend(["## Papers to Watch", ""])
    if watch_cards:
        for card in watch_cards:
            lines.append(f"- **{card['title']}** - {card['one_sentence_summary']} [{card['source_id']}]")
    else:
        lines.append("- No additional papers to watch were selected for this week.")
    lines.extend(["", "## Sources", ""])
    for card in [*top_cards, *watch_cards]:
        authors = ", ".join(card.get("authors") or ["Unknown authors"])
        locator = card.get("doi") or card.get("pdf_url") or card.get("url") or "No DOI or URL"
        date = card.get("published_date") or "Unknown date"
        lines.append(f"[{card['source_id']}] {card['title']} - {authors} - {card.get('source') or 'Unknown source'} - {date} - {locator}")
    return "\n".join(lines).strip()


def _editorial_lead(cards: list[dict]) -> str:
    if not cards:
        return "No eligible papers were found for this selected week."
    citations = "".join(f"[{card['source_id']}]" for card in cards[: min(3, len(cards))])
    return (
        f"This week's selected papers emphasize {cards[0]['title']} and related work across "
        f"{len(cards)} source-grounded studies. The selection is based on publication date, metadata quality, "
        f"topic relevance, and diversity rather than citations alone. {citations}"
    )


def _emerging_trend(cards: list[dict]) -> str:
    if len(cards) < 2:
        return "The selected week has limited activity, so trend claims should be treated cautiously."
    citations = "".join(f"[{card['source_id']}]" for card in cards[: min(4, len(cards))])
    return (
        "A shared pattern is the combination of method development with evaluation or application-oriented evidence. "
        f"The papers point to incremental, source-specific progress rather than a single broad field-wide shift. {citations}"
    )


def _why_it_matters(selection: BulletinSelection, cards: list[dict]) -> str:
    if not cards:
        return "No bulletin can be produced without eligible source papers."
    citations = "".join(f"[{card['source_id']}]" for card in cards[: min(3, len(cards))])
    return (
        f"For {selection.selection_label}, these papers are useful because they surface concrete problems, proposed methods, "
        f"and reported evidence from the selected week in one auditable source list. {citations}"
    )
