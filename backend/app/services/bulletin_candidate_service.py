from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time

from sqlalchemy import or_
from sqlalchemy.orm import Session

from database.models.ArticleData import Article
from database.models.ClusterData import Cluster


MIN_ABSTRACT_CHARS = 120
MAX_CANDIDATES = 50


@dataclass(frozen=True)
class BulletinSelection:
    selection_type: str
    selection_id: str
    selection_label: str
    week_start: datetime
    week_end: datetime


def parse_week_window(week_start: date, week_end: date) -> tuple[datetime, datetime]:
    if week_end < week_start:
        raise ValueError("week_end must be on or after week_start.")
    return datetime.combine(week_start, time.min), datetime.combine(week_end, time.max)


class BulletinCandidateService:
    def __init__(self, db: Session):
        self.db = db

    def resolve_selection(
        self,
        selection_type: str,
        selection_id: str,
        week_start: date,
        week_end: date,
    ) -> BulletinSelection:
        normalized_type = selection_type.strip().lower()
        start_dt, end_dt = parse_week_window(week_start, week_end)
        if normalized_type == "cluster":
            cluster_id = int(selection_id)
            cluster = self.db.query(Cluster).filter(Cluster.cluster_id == cluster_id).first()
            label = cluster.cluster_description if cluster and cluster.cluster_description else f"Cluster {cluster_id}"
            return BulletinSelection("cluster", str(cluster_id), label, start_dt, end_dt)
        if normalized_type == "category":
            category = selection_id.strip()
            if not category:
                raise ValueError("selection_id is required for category bulletins.")
            return BulletinSelection("category", category, category, start_dt, end_dt)
        raise ValueError("selection_type must be 'cluster' or 'category'.")

    def candidates(self, selection: BulletinSelection, limit: int = MAX_CANDIDATES) -> list[Article]:
        query = (
            self.db.query(Article)
            .filter(Article.publish_date >= selection.week_start)
            .filter(Article.publish_date <= selection.week_end)
            .filter(Article.title.isnot(None), Article.title != "")
            .filter(Article.abstract_text.isnot(None))
        )
        if selection.selection_type == "cluster":
            query = query.filter(Article.cluster_id == int(selection.selection_id))
        else:
            category = selection.selection_id
            query = query.filter(
                or_(
                    Article.primary_category == category,
                    Article.categories.ilike(f"%{category}%"),
                )
            )

        articles = query.order_by(Article.publish_date.desc(), Article.id.desc()).limit(limit * 3).all()
        filtered = [
            article
            for article in articles
            if len((article.abstract_text or "").strip()) >= MIN_ABSTRACT_CHARS
        ]
        return filtered[:limit]
