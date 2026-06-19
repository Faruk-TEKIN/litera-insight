from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math

import numpy as np

from backend.app.services.bulletin_candidate_service import BulletinSelection
from database.models.ArticleData import Article


SCORING_VERSION = "weeks_best_scoring_v1"
DEFAULT_WEIGHTS = {
    "relevance": 0.30,
    "centrality": 0.20,
    "quality": 0.15,
    "citation": 0.10,
    "recency": 0.10,
    "novelty": 0.10,
    "source_quality": 0.05,
}


@dataclass
class ScoredBulletinCandidate:
    article: Article
    relevance_score: float
    centrality_score: float
    quality_score: float
    citation_score: float
    recency_score: float
    novelty_score: float
    source_quality_score: float
    final_score: float
    diversity_group: str


class BulletinScoringService:
    def score(self, selection: BulletinSelection, articles: list[Article]) -> list[ScoredBulletinCandidate]:
        citation_max = max([math.log1p(article.citation_count or 0) for article in articles] or [1.0])
        centroid = _centroid([article.embedding for article in articles if article.embedding is not None])
        scored = [
            self._score_article(selection, article, centroid, citation_max)
            for article in articles
        ]
        return sorted(scored, key=lambda item: item.final_score, reverse=True)

    def _score_article(
        self,
        selection: BulletinSelection,
        article: Article,
        centroid: np.ndarray | None,
        citation_max: float,
    ) -> ScoredBulletinCandidate:
        relevance = _relevance(selection, article, centroid)
        centrality = _similarity(article.embedding, centroid, default=relevance)
        quality = _quality_score(article)
        citation = math.log1p(article.citation_count or 0) / citation_max if citation_max > 0 else 0.0
        recency = _recency_score(article.publish_date, selection.week_start, selection.week_end)
        novelty = 1.0
        source_quality = _source_quality_score(article)
        scores = {
            "relevance": relevance,
            "centrality": centrality,
            "quality": quality,
            "citation": citation,
            "recency": recency,
            "novelty": novelty,
            "source_quality": source_quality,
        }
        final = sum(DEFAULT_WEIGHTS[name] * scores[name] for name in DEFAULT_WEIGHTS)
        return ScoredBulletinCandidate(
            article=article,
            relevance_score=relevance,
            centrality_score=centrality,
            quality_score=quality,
            citation_score=citation,
            recency_score=recency,
            novelty_score=novelty,
            source_quality_score=source_quality,
            final_score=final,
            diversity_group=_diversity_group(article),
        )


def _relevance(selection: BulletinSelection, article: Article, centroid: np.ndarray | None) -> float:
    if selection.selection_type == "cluster":
        return _similarity(article.embedding, centroid, default=0.8 if article.cluster_id is not None else 0.0)
    category = selection.selection_id
    if article.primary_category == category:
        return 1.0
    if category and category in (article.categories or ""):
        return 0.8
    return 0.0


def _quality_score(article: Article) -> float:
    abstract_len = len((article.abstract_text or "").strip())
    abstract_score = min(1.0, abstract_len / 1200)
    title_score = 1.0 if 12 <= len((article.title or "").strip()) <= 220 else 0.6
    metadata_score = sum(
        [
            0.2 if article.doi else 0.0,
            0.2 if article.pdf_url else 0.0,
            0.2 if article.authors else 0.0,
            0.2 if article.source else 0.0,
            0.2 if article.publish_date else 0.0,
        ]
    )
    return min(1.0, 0.45 * abstract_score + 0.25 * title_score + 0.30 * metadata_score)


def _recency_score(publish_date: datetime | None, week_start: datetime, week_end: datetime) -> float:
    if publish_date is None:
        return 0.0
    total = max((week_end - week_start).total_seconds(), 1.0)
    elapsed = min(max((publish_date - week_start).total_seconds(), 0.0), total)
    return elapsed / total


def _source_quality_score(article: Article) -> float:
    score = 0.5
    if article.source in {"arxiv", "openalex", "semanticscholar"}:
        score += 0.2
    if article.doi:
        score += 0.15
    if article.pdf_url or (article.metadata_json or {}).get("has_pdf"):
        score += 0.15
    return min(1.0, score)


def _centroid(embeddings) -> np.ndarray | None:
    values = [np.array(embedding, dtype=np.float32) for embedding in embeddings if embedding is not None]
    if not values:
        return None
    return np.mean(values, axis=0)


def _similarity(embedding, other: np.ndarray | None, default: float = 0.0) -> float:
    if embedding is None or other is None:
        return default
    left = np.array(embedding, dtype=np.float32)
    right = np.array(other, dtype=np.float32)
    left_norm = np.linalg.norm(left)
    right_norm = np.linalg.norm(right)
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return max(0.0, min(1.0, float(np.dot(left, right) / (left_norm * right_norm))))


def _diversity_group(article: Article) -> str:
    if article.doi:
        return f"doi:{article.doi.strip().lower()}"
    if article.external_id:
        return f"external:{article.source}:{article.external_id}"
    return f"title:{(article.title or '').strip().lower()[:120]}"
