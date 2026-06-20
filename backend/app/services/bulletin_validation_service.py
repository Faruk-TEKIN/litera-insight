from __future__ import annotations

import re

from backend.app.services.bulletin_candidate_service import BulletinSelection


REQUIRED_SECTIONS = [
    "Editorial Lead",
    "Top Papers",
    "Emerging Trend",
    "Why It Matters",
    "Papers to Watch",
    "Sources",
]


class BulletinValidationService:
    def validate(self, selection: BulletinSelection, cards: list[dict], bulletin: dict) -> dict:
        errors: list[str] = []
        warnings: list[str] = []
        markdown = bulletin.get("full_markdown") or ""
        source_ids = {card["source_id"] for card in cards}
        cited_ids = set(re.findall(r"\[(S\d+)\]", markdown))

        missing_sections = [section for section in REQUIRED_SECTIONS if f"## {section}" not in markdown]
        if missing_sections:
            errors.append(f"Missing required sections: {', '.join(missing_sections)}")
        unknown_citations = sorted(cited_ids - source_ids)
        if unknown_citations:
            errors.append(f"Unknown cited source ids: {', '.join(unknown_citations)}")
        if cards and not cited_ids:
            errors.append("No source citations were found.")
        if len({card["article_id"] for card in cards}) != len(cards):
            errors.append("Duplicate article ids were selected.")
        if cards and "Top Papers" not in missing_sections:
            top_papers_body = _section_body(markdown, "Top Papers")
            top_papers_citations = set(re.findall(r"\[(S\d+)\]", top_papers_body))
            top_papers_titles = [card["title"] for card in cards if card["title"] in top_papers_body]
            if not top_papers_body or (not top_papers_citations.intersection(source_ids) and not top_papers_titles):
                errors.append("Top Papers section is empty.")
        if len(markdown) > 12000:
            errors.append("Bulletin exceeds maximum length.")

        for card in cards:
            if not (selection.week_start.date().isoformat() <= (card.get("published_date") or "") <= selection.week_end.date().isoformat()):
                errors.append(f"Source {card['source_id']} is outside the selected week.")
            if card["title"] not in markdown:
                warnings.append(f"Title for {card['source_id']} is not present in bulletin text.")

        return {
            "valid": not errors,
            "errors": errors,
            "warnings": warnings,
        }


def _section_body(markdown: str, section: str) -> str:
    match = re.search(rf"(?:^|\n)##[ \t]+{re.escape(section)}[ \t]*\n(?P<body>.*?)(?=\n##[ \t]+|\Z)", markdown, re.DOTALL)
    if not match:
        return ""
    return match.group("body").strip()
