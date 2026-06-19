from __future__ import annotations

import re

from backend.app.services.bulletin_scoring_service import ScoredBulletinCandidate


class BulletinCardService:
    def cards(self, selected: list[ScoredBulletinCandidate]) -> list[dict]:
        return [self.card(candidate, index) for index, candidate in enumerate(selected, start=1)]

    def card(self, candidate: ScoredBulletinCandidate, index: int) -> dict:
        article = candidate.article
        abstract = _clean(article.abstract_text)
        sentences = _sentences(abstract)
        source_id = f"S{index}"
        return {
            "article_id": article.id,
            "source_id": source_id,
            "title": article.title,
            "authors": _authors(article.authors),
            "published_date": article.publish_date.date().isoformat() if article.publish_date else None,
            "source": article.source,
            "category": article.primary_category,
            "cluster_id": article.cluster_id,
            "main_problem": sentences[0] if sentences else "Not specified",
            "proposed_method": _find_method_sentence(sentences),
            "key_contribution": sentences[1] if len(sentences) > 1 else (sentences[0] if sentences else "Not specified"),
            "evidence_or_result": _find_result_sentence(sentences),
            "limitations_or_uncertainty": "Not specified",
            "one_sentence_summary": sentences[0] if sentences else f"{article.title}.",
            "keywords": _keywords(article),
            "doi": article.doi,
            "pdf_url": article.pdf_url,
            "url": article.url,
            "score": {
                "relevance": candidate.relevance_score,
                "centrality": candidate.centrality_score,
                "quality": candidate.quality_score,
                "citation": candidate.citation_score,
                "recency": candidate.recency_score,
                "novelty": candidate.novelty_score,
                "source_quality": candidate.source_quality_score,
                "final": candidate.final_score,
            },
        }


def _clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [part.strip() for part in parts if len(part.strip()) >= 30][:5]


def _find_method_sentence(sentences: list[str]) -> str:
    markers = ("propose", "present", "introduce", "method", "approach", "framework", "model")
    for sentence in sentences:
        if any(marker in sentence.lower() for marker in markers):
            return sentence
    return "Not specified"


def _find_result_sentence(sentences: list[str]) -> str:
    markers = ("result", "show", "demonstrate", "outperform", "evaluate", "experiment", "benchmark")
    for sentence in sentences:
        if any(marker in sentence.lower() for marker in markers):
            return sentence
    return "Not specified"


def _authors(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in re.split(r",|;", value) if item.strip()][:8]


def _keywords(article) -> list[str]:
    values = [article.primary_category] if article.primary_category else []
    if article.categories:
        values.extend([item.strip() for item in re.split(r"\s+|,", article.categories) if item.strip()])
    return list(dict.fromkeys(values))[:8]
