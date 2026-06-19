from __future__ import annotations

from datetime import date, datetime, timedelta, UTC
import hashlib
import json

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.services.bulletin_candidate_service import BulletinCandidateService, parse_week_window
from backend.app.services.bulletin_card_service import BulletinCardService
from backend.app.services.bulletin_diversity_service import BulletinDiversityService
from backend.app.services.bulletin_generation_service import GENERATION_VERSION, PROMPT_VERSION, BulletinGenerationService
from backend.app.services.bulletin_scoring_service import SCORING_VERSION, BulletinScoringService
from backend.app.services.bulletin_validation_service import BulletinValidationService
from database.models.ArticleData import Article
from database.models.ClusterData import Cluster
from database.models.ReportSnapshot import ReportSnapshot


WEEKS_BEST_SCHEMA_VERSION = "weeks_best_bulletin:v1"


def default_previous_week(today: date | None = None) -> tuple[date, date]:
    today = today or datetime.now(UTC).date()
    this_monday = today - timedelta(days=today.weekday())
    previous_monday = this_monday - timedelta(days=7)
    previous_sunday = this_monday - timedelta(days=1)
    return previous_monday, previous_sunday


def weeks_best_snapshot_key(
    selection_type: str,
    selection_id: str,
    week_start: date,
    week_end: date,
    generation_version: str = GENERATION_VERSION,
) -> str:
    params = {
        "selection_type": selection_type,
        "selection_id": str(selection_id),
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "generation_version": generation_version,
        "prompt_version": PROMPT_VERSION,
        "scoring_version": SCORING_VERSION,
    }
    digest = hashlib.sha256(json.dumps(params, sort_keys=True).encode("utf-8")).hexdigest()[:24]
    return f"{WEEKS_BEST_SCHEMA_VERSION}:{digest}"


class BulletinSnapshotService:
    def __init__(self, db: Session):
        self.db = db
        self.candidates = BulletinCandidateService(db)
        self.scoring = BulletinScoringService()
        self.diversity = BulletinDiversityService()
        self.cards = BulletinCardService()
        self.validation = BulletinValidationService()

    def get_or_generate(
        self,
        selection_type: str,
        selection_id: str,
        week_start: date,
        week_end: date,
        force_refresh: bool = False,
        use_llm: bool = False,
    ) -> dict:
        key = weeks_best_snapshot_key(selection_type, selection_id, week_start, week_end)
        if not force_refresh:
            snapshot = self._get_snapshot(key)
            if snapshot:
                return snapshot.payload_json
        return self.generate(selection_type, selection_id, week_start, week_end, use_llm=use_llm)

    def get_cached(
        self,
        selection_type: str,
        selection_id: str,
        week_start: date,
        week_end: date,
    ) -> dict:
        key = weeks_best_snapshot_key(selection_type, selection_id, week_start, week_end)
        snapshot = self._get_snapshot(key)
        if snapshot:
            return snapshot.payload_json
        selection = self.candidates.resolve_selection(selection_type, selection_id, week_start, week_end)
        return {
            "status": "not_generated",
            "selection_type": selection.selection_type,
            "selection_id": selection.selection_id,
            "selection_label": selection.selection_label,
            "week_start": selection.week_start.date().isoformat(),
            "week_end": selection.week_end.date().isoformat(),
            "message": "No cached Week's Best bulletin exists for this selection and week.",
        }

    def generate(
        self,
        selection_type: str,
        selection_id: str,
        week_start: date,
        week_end: date,
        use_llm: bool = False,
    ) -> dict:
        selection = self.candidates.resolve_selection(selection_type, selection_id, week_start, week_end)
        key = weeks_best_snapshot_key(selection.selection_type, selection.selection_id, week_start, week_end)
        candidate_articles = self.candidates.candidates(selection)
        scored = self.scoring.score(selection, candidate_articles)
        selected = self.diversity.select(scored, top_count=5, watch_count=3)
        cards = self.cards.cards(selected)

        if not cards:
            payload = self._empty_payload(selection, key)
            self._upsert_snapshot(key, payload)
            return payload

        bulletin = BulletinGenerationService(use_llm=use_llm).generate(selection, cards, top_count=5)
        validation = self.validation.validate(selection, cards, bulletin)
        status = "validated" if validation["valid"] else "failed"
        payload = {
            "schema_version": WEEKS_BEST_SCHEMA_VERSION,
            "snapshot_key": key,
            "status": status,
            "selection_type": selection.selection_type,
            "selection_id": selection.selection_id,
            "selection_label": selection.selection_label,
            "week_start": selection.week_start.date().isoformat(),
            "week_end": selection.week_end.date().isoformat(),
            "title": bulletin["title"],
            "editorial_lead": bulletin["editorial_lead"],
            "emerging_trend": bulletin["emerging_trend"],
            "why_it_matters": bulletin["why_it_matters"],
            "papers_to_watch": bulletin["papers_to_watch"],
            "full_markdown": bulletin["full_markdown"] if validation["valid"] else "",
            "paper_cards": cards,
            "sources": _sources(cards),
            "metadata": {
                "candidate_count": len(candidate_articles),
                "selected_count": len(cards),
                "source_count": len(cards),
                "generation_version": GENERATION_VERSION,
                "prompt_version": PROMPT_VERSION,
                "scoring_version": SCORING_VERSION,
                "model_name": BulletinGenerationService(use_llm=use_llm).ollama.model if use_llm else None,
                "use_llm": use_llm,
                "generated_at": datetime.now(UTC).replace(tzinfo=None).isoformat(),
                "limited_activity": len(candidate_articles) < 5,
            },
            "validation": validation,
        }
        self._upsert_snapshot(key, payload)
        return payload

    def selections(self, week_start: date, week_end: date) -> dict:
        start_dt, end_dt = parse_week_window(week_start, week_end)
        clusters = [
            {
                "id": int(cluster_id),
                "label": label or f"Cluster {cluster_id}",
                "paper_count_this_week": int(count),
            }
            for cluster_id, label, count in (
                self.db.query(Article.cluster_id, Cluster.cluster_description, func.count(Article.id))
                .join(Cluster, Cluster.cluster_id == Article.cluster_id)
                .filter(Article.publish_date >= start_dt, Article.publish_date <= end_dt)
                .filter(Article.cluster_id.isnot(None))
                .group_by(Article.cluster_id, Cluster.cluster_description)
                .order_by(func.count(Article.id).desc())
                .limit(50)
                .all()
            )
        ]
        categories = [
            {
                "id": category,
                "label": category,
                "paper_count_this_week": int(count),
            }
            for category, count in (
                self.db.query(Article.primary_category, func.count(Article.id))
                .filter(Article.publish_date >= start_dt, Article.publish_date <= end_dt)
                .filter(Article.primary_category.isnot(None), Article.primary_category != "")
                .group_by(Article.primary_category)
                .order_by(func.count(Article.id).desc(), Article.primary_category.asc())
                .limit(100)
                .all()
            )
        ]
        return {
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat(),
            "clusters": clusters,
            "categories": categories,
        }

    def _empty_payload(self, selection, key: str) -> dict:
        return {
            "schema_version": WEEKS_BEST_SCHEMA_VERSION,
            "snapshot_key": key,
            "status": "empty",
            "selection_type": selection.selection_type,
            "selection_id": selection.selection_id,
            "selection_label": selection.selection_label,
            "week_start": selection.week_start.date().isoformat(),
            "week_end": selection.week_end.date().isoformat(),
            "title": f"Week's Best - {selection.selection_label}",
            "editorial_lead": "",
            "emerging_trend": "",
            "why_it_matters": "",
            "papers_to_watch": [],
            "full_markdown": "",
            "paper_cards": [],
            "sources": [],
            "metadata": {
                "candidate_count": 0,
                "selected_count": 0,
                "source_count": 0,
                "generation_version": GENERATION_VERSION,
                "prompt_version": PROMPT_VERSION,
                "scoring_version": SCORING_VERSION,
                "generated_at": datetime.now(UTC).replace(tzinfo=None).isoformat(),
                "limited_activity": True,
            },
            "validation": {"valid": True, "errors": [], "warnings": ["No eligible papers found."]},
            "message": "No weekly bulletin is available because no eligible papers were found in the selected date range.",
        }

    def _get_snapshot(self, key: str) -> ReportSnapshot | None:
        return self.db.query(ReportSnapshot).filter(ReportSnapshot.snapshot_key == key).first()

    def _upsert_snapshot(self, key: str, payload: dict) -> None:
        snapshot = self._get_snapshot(key)
        if snapshot is None:
            snapshot = ReportSnapshot(snapshot_key=key, payload_json=payload)
            self.db.add(snapshot)
        snapshot.payload_json = payload
        snapshot.metadata_json = {
            "kind": "weeks_best_bulletin",
            "schema_version": WEEKS_BEST_SCHEMA_VERSION,
            "status": payload.get("status"),
            "selection_type": payload.get("selection_type"),
            "selection_id": payload.get("selection_id"),
            "week_start": payload.get("week_start"),
            "week_end": payload.get("week_end"),
        }
        snapshot.generated_at = datetime.now(UTC).replace(tzinfo=None)
        self.db.commit()


def _sources(cards: list[dict]) -> list[dict]:
    return [
        {
            "source_id": card["source_id"],
            "article_id": card["article_id"],
            "title": card["title"],
            "authors": card.get("authors") or [],
            "published_date": card.get("published_date"),
            "source_name": card.get("source"),
            "doi": card.get("doi"),
            "pdf_url": card.get("pdf_url"),
            "external_url": card.get("url"),
            "category": card.get("category"),
            "cluster_id": card.get("cluster_id"),
        }
        for card in cards
    ]
