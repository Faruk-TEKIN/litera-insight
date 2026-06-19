from __future__ import annotations

import numpy as np

from backend.app.services.bulletin_scoring_service import ScoredBulletinCandidate


class BulletinDiversityService:
    def select(
        self,
        candidates: list[ScoredBulletinCandidate],
        top_count: int = 5,
        watch_count: int = 3,
        mmr_lambda: float = 0.7,
    ) -> list[ScoredBulletinCandidate]:
        total = max(1, top_count + watch_count)
        pool = _dedupe(candidates)
        selected: list[ScoredBulletinCandidate] = []

        while pool and len(selected) < total:
            best = max(
                pool,
                key=lambda candidate: (
                    mmr_lambda * candidate.final_score
                    - (1.0 - mmr_lambda) * _max_similarity(candidate, selected),
                    candidate.final_score,
                ),
            )
            selected.append(best)
            pool.remove(best)
        return selected


def _dedupe(candidates: list[ScoredBulletinCandidate]) -> list[ScoredBulletinCandidate]:
    seen_groups: set[str] = set()
    seen_titles: set[str] = set()
    result: list[ScoredBulletinCandidate] = []
    for candidate in candidates:
        title = (candidate.article.title or "").strip().lower()
        if candidate.diversity_group in seen_groups or title in seen_titles:
            continue
        seen_groups.add(candidate.diversity_group)
        seen_titles.add(title)
        result.append(candidate)
    return result


def _max_similarity(candidate: ScoredBulletinCandidate, selected: list[ScoredBulletinCandidate]) -> float:
    if not selected:
        return 0.0
    return max(_embedding_similarity(candidate.article.embedding, item.article.embedding) for item in selected)


def _embedding_similarity(left, right) -> float:
    if left is None or right is None:
        return 0.0
    left_arr = np.array(left, dtype=np.float32)
    right_arr = np.array(right, dtype=np.float32)
    left_norm = np.linalg.norm(left_arr)
    right_norm = np.linalg.norm(right_arr)
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return max(0.0, min(1.0, float(np.dot(left_arr, right_arr) / (left_norm * right_norm))))
