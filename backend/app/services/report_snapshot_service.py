from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import json
from types import SimpleNamespace

import numpy as np
from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session

from backend.app.services.digest_service import DigestService
from database.models.ArticleData import Article
from database.models.ClusterData import Cluster
from database.models.ReportSnapshot import ReportSnapshot


LEGACY_ANALYTICS_SNAPSHOT_KEY = "analytics:v1"
ANALYTICS_SCHEMA_VERSION = "analytics:v6"
DEFAULT_ANALYTICS_PERIOD = "12m"
ANALYTICS_PERIODS = {"1m": 1, "3m": 3, "6m": 6, "12m": 12, "all": None}
DEFAULT_BULLETIN_LIMIT = 10
DEFAULT_BULLETIN_INCLUDE_DIGESTS = True
DEFAULT_BULLETIN_ABSTRACT_LIMIT = 900

COLORS = [
    "#10b981", "#3b82f6", "#f59e0b", "#ef4444", "#8b5cf6",
    "#ec4899", "#14b8a6", "#6366f1", "#06b6d4", "#f43f5e",
    "#059669", "#2563eb", "#d97706", "#dc2626", "#7c3aed",
    "#db2777", "#0d9488", "#4f46e5", "#0891b2", "#e11d48",
]


@dataclass(frozen=True)
class AnalyticsContext:
    source: str | None
    category: str | None
    period: str
    reference_date: datetime | None
    period_start: datetime | None
    period_end: datetime | None
    min_publish_date: datetime | None
    filtered_article_query: object


def get_color(cluster_id: int) -> str:
    return COLORS[abs(cluster_id) % len(COLORS)]


def normalize_analytics_period(period: str | None) -> str:
    normalized = (period or DEFAULT_ANALYTICS_PERIOD).strip().lower()
    return normalized if normalized in ANALYTICS_PERIODS else DEFAULT_ANALYTICS_PERIOD


def analytics_snapshot_key(
    source: str | None = None,
    category: str | None = None,
    period: str = DEFAULT_ANALYTICS_PERIOD,
) -> str:
    params = {
        "source": source or None,
        "category": category or None,
        "period": normalize_analytics_period(period),
    }
    digest = hashlib.sha256(json.dumps(params, sort_keys=True).encode("utf-8")).hexdigest()[:24]
    return f"{ANALYTICS_SCHEMA_VERSION}:{digest}"


ANALYTICS_SNAPSHOT_KEY = analytics_snapshot_key()


def calculate_cosine_similarity(v1, v2, default: float = 0.0) -> float:
    if v1 is None or v2 is None:
        return default
    arr1 = np.array(v1, dtype=np.float32)
    arr2 = np.array(v2, dtype=np.float32)
    dot = np.dot(arr1, arr2)
    norm1 = np.linalg.norm(arr1)
    norm2 = np.linalg.norm(arr2)
    if norm1 == 0.0 or norm2 == 0.0:
        return 0.0
    return float(dot / (norm1 * norm2))


def bulletin_snapshot_key(
    limit: int | None,
    include_digests: bool,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
    category: str | None = None,
    source: str | None = None,
    cluster_ids: list[int] | None = None,
    categories: list[str] | None = None,
) -> str:
    params = {
        "limit": limit,
        "include_digests": include_digests,
        "period_start": period_start.isoformat() if period_start else None,
        "period_end": period_end.isoformat() if period_end else None,
        "category": category,
        "source": source,
        "cluster_ids": sorted(cluster_ids or []),
        "categories": sorted(categories or []),
    }
    digest = hashlib.sha256(json.dumps(params, sort_keys=True).encode("utf-8")).hexdigest()[:24]
    return f"bulletin:v1:{digest}"


def default_bulletin_snapshot_key() -> str:
    return bulletin_snapshot_key(
        limit=DEFAULT_BULLETIN_LIMIT,
        include_digests=DEFAULT_BULLETIN_INCLUDE_DIGESTS,
    )


def _iso_or_none(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _month_start(value: datetime) -> datetime:
    return value.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _add_months(value: datetime, months: int) -> datetime:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return value.replace(year=year, month=month)


def _month_keys_between(start: datetime | None, end: datetime | None) -> list[str]:
    if start is None or end is None:
        return []
    current = _month_start(start)
    last = _month_start(end)
    keys = []
    while current <= last:
        keys.append(current.strftime("%Y-%m"))
        current = _add_months(current, 1)
    return keys


def _month_label(month_key: str) -> str:
    return datetime.strptime(month_key, "%Y-%m").strftime("%b %y")


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _category_match_clause(category: str):
    normalized = category.strip()
    escaped = _escape_like(normalized)
    categories_text = func.coalesce(Article.categories, "")
    normalized_categories = func.concat(
        " ",
        func.replace(
            func.replace(
                func.replace(
                    func.replace(categories_text, ",", " "),
                    ";",
                    " ",
                ),
                "|",
                " ",
            ),
            "\n",
            " ",
        ),
        " ",
    )
    return or_(
        Article.primary_category == normalized,
        normalized_categories.ilike(f"% {escaped} %", escape="\\"),
    )


def _base_analytics_article_query(
    db: Session,
    source: str | None = None,
    category: str | None = None,
):
    query = db.query(Article).filter(Article.publish_date.isnot(None))
    if source:
        query = query.filter(Article.source == source)
    if category:
        query = query.filter(_category_match_clause(category))
    return query


def build_analytics_context(
    db: Session,
    source: str | None = None,
    category: str | None = None,
    period: str = DEFAULT_ANALYTICS_PERIOD,
) -> AnalyticsContext:
    period = normalize_analytics_period(period)
    base_query = _base_analytics_article_query(db, source=source, category=category)
    min_publish_date, reference_date = base_query.with_entities(
        func.min(Article.publish_date),
        func.max(Article.publish_date),
    ).one()

    period_start = None
    period_end = reference_date
    filtered_article_query = base_query
    if reference_date is None:
        filtered_article_query = base_query.filter(Article.id.is_(None))
    elif ANALYTICS_PERIODS[period] is None:
        period_start = _month_start(min_publish_date or reference_date)
        filtered_article_query = base_query.filter(
            Article.publish_date >= period_start,
            Article.publish_date <= reference_date,
        )
    else:
        period_start = _month_start(_add_months(reference_date, -(ANALYTICS_PERIODS[period] - 1)))
        filtered_article_query = base_query.filter(
            Article.publish_date >= period_start,
            Article.publish_date <= reference_date,
        )

    return AnalyticsContext(
        source=source,
        category=category,
        period=period,
        reference_date=reference_date,
        period_start=period_start,
        period_end=period_end,
        min_publish_date=min_publish_date,
        filtered_article_query=filtered_article_query,
    )


def analytics_data_fingerprint(db: Session) -> str:
    article_count, max_publish_date, max_updated_date = (
        db.query(
            func.count(Article.id),
            func.max(Article.publish_date),
            func.max(Article.updated_date),
        )
        .filter(Article.publish_date.isnot(None))
        .one()
    )
    cluster_count, max_cluster_created_at = db.query(
        func.count(Cluster.id),
        func.max(Cluster.created_at),
    ).one()
    payload = {
        "articleCount": int(article_count or 0),
        "maxPublishDate": _iso_or_none(max_publish_date),
        "maxUpdatedDate": _iso_or_none(max_updated_date),
        "clusterCount": int(cluster_count or 0),
        "maxClusterCreatedAt": _iso_or_none(max_cluster_created_at),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


class ReportSnapshotService:
    def __init__(self, db: Session):
        self.db = db

    def get_analytics(
        self,
        force_refresh: bool = False,
        source: str | None = None,
        category: str | None = None,
        period: str = DEFAULT_ANALYTICS_PERIOD,
    ) -> dict:
        period = normalize_analytics_period(period)
        key = analytics_snapshot_key(source=source, category=category, period=period)
        if force_refresh:
            return self.refresh_analytics_snapshot(source=source, category=category, period=period)
        data_fingerprint = self._analytics_data_fingerprint()
        snapshot = self._get_snapshot(key)
        if snapshot and (snapshot.metadata_json or {}).get("dataFingerprint") == data_fingerprint:
            return with_analytics_defaults(snapshot.payload_json, source=source, category=category, period=period)
        return self.refresh_analytics_snapshot(source=source, category=category, period=period)

    def get_bulletin(
        self,
        limit: int = DEFAULT_BULLETIN_LIMIT,
        include_digests: bool = DEFAULT_BULLETIN_INCLUDE_DIGESTS,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
        category: str | None = None,
        source: str | None = None,
        cluster_ids: list[int] | None = None,
        categories: list[str] | None = None,
        force_refresh: bool = False,
    ) -> list[dict]:
        key = bulletin_snapshot_key(
            limit=limit,
            include_digests=include_digests,
            period_start=period_start,
            period_end=period_end,
            category=category,
            source=source,
            cluster_ids=cluster_ids,
            categories=categories,
        )
        if force_refresh:
            return self.refresh_bulletin_snapshot(
                limit=limit,
                include_digests=include_digests,
                period_start=period_start,
                period_end=period_end,
                category=category,
                source=source,
                cluster_ids=cluster_ids,
                categories=categories,
            )
        snapshot = self._get_snapshot(key)
        if snapshot:
            return snapshot.payload_json
        return []

    def refresh_default_snapshots(self) -> dict[str, str]:
        self.db.query(ReportSnapshot).filter(
            or_(
                ReportSnapshot.snapshot_key.like("analytics:%"),
                ReportSnapshot.snapshot_key.like("bulletin:%"),
            )
        ).delete(synchronize_session=False)
        self.db.commit()

        self.refresh_analytics_snapshot()
        self.refresh_bulletin_snapshot(
            limit=DEFAULT_BULLETIN_LIMIT,
            include_digests=DEFAULT_BULLETIN_INCLUDE_DIGESTS,
        )
        return {
            "analytics": ANALYTICS_SNAPSHOT_KEY,
            "bulletin": default_bulletin_snapshot_key(),
        }

    def refresh_analytics_snapshot(
        self,
        source: str | None = None,
        category: str | None = None,
        period: str = DEFAULT_ANALYTICS_PERIOD,
    ) -> dict:
        period = normalize_analytics_period(period)
        payload = build_analytics_payload(self.db, source=source, category=category, period=period)
        key = analytics_snapshot_key(source=source, category=category, period=period)
        data_fingerprint = self._analytics_data_fingerprint()
        self._upsert_snapshot(
            key,
            payload,
            metadata={
                "kind": "analytics",
                "schemaVersion": ANALYTICS_SCHEMA_VERSION,
                "source": source,
                "category": category,
                "period": period,
                "dataFingerprint": data_fingerprint,
            },
        )
        return payload

    def refresh_bulletin_snapshot(
        self,
        limit: int | None = DEFAULT_BULLETIN_LIMIT,
        include_digests: bool = DEFAULT_BULLETIN_INCLUDE_DIGESTS,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
        category: str | None = None,
        source: str | None = None,
        cluster_ids: list[int] | None = None,
        categories: list[str] | None = None,
    ) -> list[dict]:
        payload = build_bulletin_payload(
            self.db,
            limit=limit,
            include_digests=include_digests,
            period_start=period_start,
            period_end=period_end,
            category=category,
            source=source,
            cluster_ids=cluster_ids,
            categories=categories,
        )
        key = bulletin_snapshot_key(
            limit=limit,
            include_digests=include_digests,
            period_start=period_start,
            period_end=period_end,
            category=category,
            source=source,
            cluster_ids=cluster_ids,
            categories=categories,
        )
        self._upsert_snapshot(
            key,
            payload,
            metadata={
                "kind": "bulletin",
                "limit": limit,
                "include_digests": include_digests,
                "period_start": period_start.isoformat() if period_start else None,
                "period_end": period_end.isoformat() if period_end else None,
                "category": category,
                "source": source,
                "cluster_ids": sorted(cluster_ids or []),
                "categories": sorted(categories or []),
            },
        )
        return payload

    def _get_snapshot(self, snapshot_key: str) -> ReportSnapshot | None:
        return self.db.query(ReportSnapshot).filter(ReportSnapshot.snapshot_key == snapshot_key).first()

    def _analytics_data_fingerprint(self) -> str:
        return analytics_data_fingerprint(self.db)

    def _upsert_snapshot(self, snapshot_key: str, payload, metadata: dict | None = None) -> None:
        generated_at = datetime.now(UTC).replace(tzinfo=None)
        snapshot = self._get_snapshot(snapshot_key)
        if snapshot is None:
            snapshot = ReportSnapshot(snapshot_key=snapshot_key, payload_json=payload)
            self.db.add(snapshot)
        snapshot.payload_json = payload
        snapshot.metadata_json = metadata or {}
        snapshot.generated_at = generated_at
        self.db.commit()


def _cluster_counts_from_query(article_query) -> dict[int, int]:
    return {
        int(cluster_id): int(count)
        for cluster_id, count in (
            article_query.with_entities(Article.cluster_id, func.count(Article.id))
            .filter(Article.cluster_id.isnot(None))
            .group_by(Article.cluster_id)
            .all()
        )
    }


def _clusters_for_counts(db: Session, cluster_counts: dict[int, int]) -> list[Cluster]:
    cluster_ids = list(cluster_counts)
    cluster_rows = (
        db.query(Cluster).filter(Cluster.cluster_id.in_(cluster_ids)).all()
        if cluster_ids
        else []
    )
    return _clusters_from_counts(cluster_counts, cluster_rows)


def _time_range_payload(context: AnalyticsContext) -> dict:
    return {
        "referenceDate": _iso_or_none(context.reference_date),
        "periodStart": _iso_or_none(context.period_start),
        "periodEnd": _iso_or_none(context.period_end),
        "minPublishDate": _iso_or_none(context.min_publish_date),
    }


def _coerce_analytics_context(
    context_or_db,
    source: str | None = None,
    category: str | None = None,
    period: str = DEFAULT_ANALYTICS_PERIOD,
) -> AnalyticsContext:
    if hasattr(context_or_db, "filtered_article_query"):
        return context_or_db
    return build_analytics_context(context_or_db, source=source, category=category, period=period)


def build_analytics_payload(
    db: Session,
    source: str | None = None,
    category: str | None = None,
    period: str = DEFAULT_ANALYTICS_PERIOD,
) -> dict:
    context = build_analytics_context(db, source=source, category=category, period=period)
    article_query = context.filtered_article_query
    total_papers = article_query.count()
    cluster_counts = _cluster_counts_from_query(article_query)
    clusters = _clusters_for_counts(db, cluster_counts)
    active_clusters = len(cluster_counts)
    clustered_papers = sum(cluster_counts.values())
    avg_papers_per_cluster = clustered_papers / active_clusters if active_clusters else 0
    week_ago = context.reference_date - timedelta(days=7) if context.reference_date else None

    formatted_clusters = [
        _format_cluster_payload(
            cluster,
            _cluster_representation_score(cluster),
            paper_count=int(cluster_counts.get(cluster.cluster_id, 0)),
        )
        for cluster in clusters
    ]

    metrics = {
        "totalPapers": total_papers,
        "activeClusters": active_clusters,
        "avgPapersPerCluster": avg_papers_per_cluster,
        "weeklyPicks": article_query.filter(Article.publish_date >= week_ago).count() if week_ago else 0,
        "clusteredPapers": clustered_papers,
    }

    bar_data = [
        {
            "name": cluster["name"],
            "fullName": cluster["name"],
            "count": cluster["paper_count"],
            "color": cluster["color"],
            "papers": cluster["paper_count"],
        }
        for cluster in formatted_clusters
    ]
    pie_data = [{"name": item["name"], "value": item["count"], "color": item["color"]} for item in bar_data[:8]]
    scatter_data = [
        {
            "cluster": cluster["name"],
            "fullName": cluster["name"],
            "x": cluster["paper_count"],
            "y": round((cluster.get("representation_score") or 0) * 100, 2),
            "z": cluster["paper_count"],
            "color": cluster["color"],
        }
        for cluster in formatted_clusters
    ]

    category_context = build_analytics_context(db, source=source, category=None, period=context.period)
    global_context = build_analytics_context(db, period="all")
    global_cluster_counts = _cluster_counts_from_query(global_context.filtered_article_query)
    global_clusters = _clusters_for_counts(db, global_cluster_counts)

    return {
        "schemaVersion": ANALYTICS_SCHEMA_VERSION,
        "generatedAt": datetime.now(UTC).replace(tzinfo=None).isoformat(),
        "filters": {
            "source": source,
            "category": category,
            "period": context.period,
        },
        "timeRange": _time_range_payload(context),
        "metrics": metrics,
        "barData": bar_data,
        "pieData": pie_data,
        "scatterData": scatter_data,
        "monthlyData": _monthly_data(context),
        "clusters": formatted_clusters,
        "categoryOptions": _category_options(category_context),
        "clusterTrendSeries": _cluster_trend_series(context, clusters, cluster_counts),
        "risingTopics": _rising_topics(context, clusters, cluster_counts),
        "filteredClusterQuality": _cluster_quality(article_query, clusters, cluster_counts),
        "globalClusterQuality": _cluster_quality(
            global_context.filtered_article_query,
            global_clusters,
            global_cluster_counts,
        ),
    }


def build_bulletin_payload(
    db: Session,
    limit: int | None = DEFAULT_BULLETIN_LIMIT,
    include_digests: bool = DEFAULT_BULLETIN_INCLUDE_DIGESTS,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
    category: str | None = None,
    source: str | None = None,
    cluster_ids: list[int] | None = None,
    categories: list[str] | None = None,
) -> list[dict]:
    category_filters = _normalize_categories(category=category, categories=categories)
    selected_cluster_ids = sorted({int(cluster_id) for cluster_id in (cluster_ids or [])})
    cluster_query = db.query(Cluster)
    if selected_cluster_ids:
        cluster_query = cluster_query.filter(Cluster.cluster_id.in_(selected_cluster_ids))
    elif category_filters or source or period_start or period_end:
        matching_cluster_ids = [
            row[0]
            for row in _matching_article_query(
                db,
                categories=category_filters,
                source=source,
                period_start=period_start,
                period_end=period_end,
            )
            .with_entities(Article.cluster_id)
            .filter(Article.cluster_id.isnot(None))
            .distinct()
            .all()
        ]
        if not matching_cluster_ids:
            return []
        cluster_query = cluster_query.filter(Cluster.cluster_id.in_(matching_cluster_ids))

    clusters = cluster_query.order_by(Cluster.article_count.desc()).all()
    digest_service = DigestService(db)
    result_clusters = []

    for cluster in clusters:
        articles = _cluster_articles(
            db,
            cluster,
            limit,
            categories=category_filters,
            source=source,
            period_start=period_start,
            period_end=period_end,
        )
        if not articles:
            continue
        metadata_scores = _representative_scores(cluster)
        formatted_papers = []
        for paper in articles:
            score = metadata_scores.get(paper.id, 0.8)
            formatted_papers.append(
                _format_paper_payload(
                    paper,
                    score,
                    week_ago=None,
                    representative=True,
                    abstract_limit=DEFAULT_BULLETIN_ABSTRACT_LIMIT,
                )
            )
        formatted_papers.sort(key=lambda item: item["representation_score"], reverse=True)

        cluster_payload = {
            "cluster": _format_cluster_payload(
                cluster,
                representation_score=None,
                paper_count=_matching_article_query(
                    db,
                    cluster_id=cluster.cluster_id,
                    categories=category_filters,
                    source=source,
                    period_start=period_start,
                    period_end=period_end,
                ).count(),
            ),
            "papers": formatted_papers,
        }

        if include_digests:
            digest_article_limit = min(max(limit or DEFAULT_BULLETIN_LIMIT, 1), 10)
            digest = digest_service.get_or_create_cluster_digest(
                cluster_id=cluster.cluster_id,
                period_start=period_start,
                period_end=period_end,
                category=category,
                categories=category_filters,
                source=source,
                max_articles=digest_article_limit,
                use_llm=False,
            )
            cluster_payload["digest"] = _compact_digest(digest)

        result_clusters.append(cluster_payload)

    return result_clusters


def _compact_digest(digest: dict | None) -> dict | None:
    if digest is None:
        return None
    return {
        "cluster_id": digest.get("cluster_id"),
        "summary": digest.get("summary"),
        "highlights": digest.get("highlights") or [],
        "article_ids": digest.get("article_ids") or [],
        "created_at": digest.get("created_at"),
    }


def empty_analytics_payload(
    snapshot_missing: bool = False,
    source: str | None = None,
    category: str | None = None,
    period: str = DEFAULT_ANALYTICS_PERIOD,
) -> dict:
    period = normalize_analytics_period(period)
    return {
        "schemaVersion": ANALYTICS_SCHEMA_VERSION,
        "generatedAt": datetime.now(UTC).replace(tzinfo=None).isoformat(),
        "filters": {
            "source": source,
            "category": category,
            "period": period,
        },
        "timeRange": {
            "referenceDate": None,
            "periodStart": None,
            "periodEnd": None,
            "minPublishDate": None,
        },
        "metrics": {
            "totalPapers": 0,
            "activeClusters": 0,
            "avgPapersPerCluster": 0,
            "weeklyPicks": 0,
            "clusteredPapers": 0,
        },
        "barData": [],
        "pieData": [],
        "scatterData": [],
        "monthlyData": [],
        "clusters": [],
        "categoryOptions": [],
        "clusterTrendSeries": [],
        "risingTopics": [],
        "filteredClusterQuality": empty_cluster_quality(),
        "globalClusterQuality": empty_cluster_quality(),
    }


def with_analytics_defaults(
    payload: dict,
    source: str | None = None,
    category: str | None = None,
    period: str = DEFAULT_ANALYTICS_PERIOD,
) -> dict:
    base = empty_analytics_payload(source=source, category=category, period=period)
    merged = {**base, **(payload or {})}
    merged["metrics"] = {**base["metrics"], **(payload or {}).get("metrics", {})}
    merged["filters"] = {**base["filters"], **(payload or {}).get("filters", {})}
    merged["timeRange"] = {**base["timeRange"], **(payload or {}).get("timeRange", {})}
    merged["filteredClusterQuality"] = {
        **base["filteredClusterQuality"],
        **(payload or {}).get("filteredClusterQuality", {}),
    }
    merged["globalClusterQuality"] = {
        **base["globalClusterQuality"],
        **(payload or {}).get("globalClusterQuality", {}),
    }
    return merged


def empty_cluster_quality() -> dict:
    return {
        "outlierCount": 0,
        "outlierRatio": 0,
        "largestClusterId": None,
        "largestClusterName": None,
        "largestClusterCount": 0,
        "largestClusterRatio": 0,
        "avgRepresentationScore": 0,
        "clusteredPapers": 0,
        "totalPapersWithEmbedding": 0,
    }


def _cluster_centroids(db: Session, clusters: list[Cluster]) -> dict[int, np.ndarray]:
    centroids = {}
    for cluster in clusters:
        article_embeddings = (
            db.query(Article.embedding)
            .filter(Article.cluster_id == cluster.cluster_id, Article.embedding.isnot(None))
            .all()
        )
        if article_embeddings:
            embeddings = [np.array(article[0], dtype=np.float32) for article in article_embeddings]
            centroids[cluster.cluster_id] = np.mean(embeddings, axis=0)
    return centroids


def _format_paper_payload(
    paper: Article,
    representation_score: float,
    week_ago: datetime | None,
    representative: bool = False,
    abstract_limit: int | None = None,
) -> dict:
    authors_str = paper.authors or "Unknown Authors"
    venue_str = paper.venue or "Unknown Venue"
    year_str = str(paper.publish_date.year) if paper.publish_date else ""
    ref = f"{authors_str} - {venue_str} ({year_str})" if year_str else f"{authors_str} - {venue_str}"
    is_weekly_pick = bool(week_ago and paper.publish_date and paper.publish_date >= week_ago)
    created_at = paper.publish_date.isoformat() if paper.publish_date else datetime.utcnow().isoformat()

    abstract = paper.abstract_text or ""
    if abstract_limit is not None and len(abstract) > abstract_limit:
        abstract = f"{abstract[:abstract_limit].rstrip()}..."

    return {
        "id": str(paper.id),
        "cluster_id": str(paper.cluster_id),
        "title": paper.title,
        "reference": ref,
        "abstract": abstract,
        "is_representative": representative,
        "representation_score": representation_score,
        "published_at": paper.publish_date.isoformat() if paper.publish_date else None,
        "is_weekly_pick": is_weekly_pick,
        "week_label": "This Week",
        "created_at": created_at,
        "citation_count": paper.citation_count or 0,
        "source": paper.source,
        "primary_category": paper.primary_category,
        "doi": paper.doi,
        "url": paper.url or paper.pdf_url,
        "pdf_url": paper.pdf_url,
        "has_pdf": bool(paper.pdf_url or (paper.metadata_json or {}).get("has_pdf")),
    }


def _format_cluster_payload(
    cluster: Cluster,
    representation_score: float | None,
    paper_count: int | None = None,
) -> dict:
    desc = cluster.cluster_description or ""
    keyword = desc.split(",")[0].strip() if "," in desc else desc.split(" ")[0].strip()
    if not keyword:
        keyword = f"Topic {cluster.cluster_id}"

    payload = {
        "id": str(cluster.cluster_id),
        "name": cluster.cluster_description or f"Cluster {cluster.cluster_id}",
        "keyword": keyword,
        "description": cluster.cluster_description or "",
        "color": get_color(cluster.cluster_id),
        "paper_count": paper_count if paper_count is not None else cluster.article_count,
        "created_at": cluster.created_at.isoformat() if cluster.created_at else datetime.utcnow().isoformat(),
        "metadata": cluster.metadata_json or {},
    }
    if representation_score is not None:
        payload["representation_score"] = representation_score
    return payload


def _clusters_from_counts(cluster_counts: dict[int, int], clusters: list[Cluster]) -> list[Cluster]:
    existing_by_id = {cluster.cluster_id: cluster for cluster in clusters}
    merged = []
    for cluster_id, paper_count in cluster_counts.items():
        cluster = existing_by_id.get(cluster_id)
        if cluster is None:
            cluster = SimpleNamespace(
                cluster_id=cluster_id,
                cluster_description=f"Cluster {cluster_id}",
                article_count=int(paper_count),
                metadata_json={},
                created_at=None,
            )
        merged.append(cluster)
    return sorted(merged, key=lambda cluster: cluster_counts.get(cluster.cluster_id, 0), reverse=True)


def _representative_scores(cluster: Cluster) -> dict[int, float]:
    if not cluster.metadata_json:
        return {}
    raw_scores = cluster.metadata_json.get("representative_article_scores") or {}
    scores = {}
    for article_id, score in raw_scores.items():
        try:
            scores[int(article_id)] = float(score)
        except (TypeError, ValueError):
            continue
    return scores


def _cluster_representation_score(cluster: Cluster) -> float:
    scores = list(_representative_scores(cluster).values())
    return sum(scores) / len(scores) if scores else 0.0


def _filtered_articles_query(
    db: Session,
    source: str | None = None,
    category: str | None = None,
    period: str = DEFAULT_ANALYTICS_PERIOD,
):
    return build_analytics_context(db, source=source, category=category, period=period).filtered_article_query


def _category_options(context: AnalyticsContext) -> list[dict]:
    primary_categories = [
        primary_category
        for primary_category, _count in (
            context.filtered_article_query
            .with_entities(Article.primary_category, func.count(Article.id))
            .filter(Article.primary_category.isnot(None), Article.primary_category != "")
            .group_by(Article.primary_category)
            .order_by(func.count(Article.id).desc(), Article.primary_category.asc())
            .limit(20)
            .all()
        )
    ]
    if not primary_categories:
        return []

    count_columns = [
        func.coalesce(
            func.sum(
                case(
                    (
                        _category_match_clause(primary_category),
                        1,
                    ),
                    else_=0,
                )
            ),
            0,
        ).label(f"category_{index}")
        for index, primary_category in enumerate(primary_categories)
    ]
    row = context.filtered_article_query.with_entities(*count_columns).one()
    counts = row._mapping
    options = [
        {
            "category": primary_category,
            "count": int(counts[f"category_{index}"] or 0),
        }
        for index, primary_category in enumerate(primary_categories)
    ]
    return sorted(options, key=lambda item: (-item["count"], item["category"]))


def _category_distribution(
    db: Session,
    source: str | None = None,
    period: str = DEFAULT_ANALYTICS_PERIOD,
) -> list[dict]:
    return _category_options(build_analytics_context(db, source=source, period=period))


def _monthly_data(
    context_or_db,
    source: str | None = None,
    category: str | None = None,
    period: str = DEFAULT_ANALYTICS_PERIOD,
) -> list[dict]:
    context = _coerce_analytics_context(context_or_db, source=source, category=category, period=period)
    monthly_rows = (
        context.filtered_article_query
        .with_entities(
            func.to_char(func.date_trunc("month", Article.publish_date), "YYYY-MM").label("month_key"),
            func.count(Article.id).label("count"),
        )
        .group_by("month_key")
        .order_by("month_key")
        .all()
    )
    counts = {row._mapping["month_key"]: int(row._mapping["count"]) for row in monthly_rows}
    return [
        {
            "month": _month_label(month_key),
            "monthKey": month_key,
            "count": counts.get(month_key, 0),
            "publications": counts.get(month_key, 0),
        }
        for month_key in _month_keys_between(context.period_start, context.period_end)
    ]


def _cluster_trend_series(
    context: AnalyticsContext,
    clusters: list[Cluster],
    cluster_counts: dict[int, int],
) -> list[dict]:
    top_clusters = sorted(
        clusters,
        key=lambda cluster: cluster_counts.get(cluster.cluster_id, 0),
        reverse=True,
    )[:8]
    if not top_clusters:
        return []

    cluster_ids = [cluster.cluster_id for cluster in top_clusters]
    cluster_names = {
        cluster.cluster_id: cluster.cluster_description or f"Cluster {cluster.cluster_id}"
        for cluster in top_clusters
    }
    rows = (
        context.filtered_article_query
        .with_entities(
            Article.cluster_id,
            func.to_char(func.date_trunc("month", Article.publish_date), "YYYY-MM").label("month_key"),
            func.count(Article.id).label("count"),
        )
        .filter(Article.cluster_id.in_(cluster_ids))
        .group_by(Article.cluster_id, "month_key")
        .order_by("month_key")
        .all()
    )

    counts = {(int(cluster_id), month_key): int(count) for cluster_id, month_key, count in rows}
    series = []
    for month_key in _month_keys_between(context.period_start, context.period_end):
        for cluster_id in cluster_ids:
            series.append(
                {
                    "cluster_id": str(cluster_id),
                    "cluster_name": cluster_names.get(cluster_id, f"Cluster {cluster_id}"),
                    "month": _month_label(month_key),
                    "monthKey": month_key,
                    "count": counts.get((cluster_id, month_key), 0),
                }
            )

    return series


def _cluster_trend_data(
    db: Session,
    clusters: list[Cluster],
    source: str | None = None,
    category: str | None = None,
    period: str = DEFAULT_ANALYTICS_PERIOD,
) -> dict[str, list[dict]]:
    context = build_analytics_context(db, source=source, category=category, period=period)
    cluster_counts = _cluster_counts_from_query(context.filtered_article_query)
    series = _cluster_trend_series(context, clusters, cluster_counts)
    by_month: dict[str, dict] = {}
    for item in series:
        month_payload = by_month.setdefault(
            item["monthKey"],
            {"month": item["month"], "monthKey": item["monthKey"], "clusters": {}, "total": 0},
        )
        month_payload["clusters"][item["cluster_id"]] = item["count"]
        month_payload["total"] += item["count"]
    return {"wide": [by_month[key] for key in sorted(by_month)], "series": series}


def _rising_topics(
    context_or_db,
    clusters: list[Cluster],
    cluster_counts: dict[int, int] | None = None,
    source: str | None = None,
    category: str | None = None,
) -> list[dict]:
    if cluster_counts is not None and not isinstance(cluster_counts, dict):
        source = cluster_counts
        cluster_counts = None
    context = _coerce_analytics_context(context_or_db, source=source, category=category, period="all")
    if cluster_counts is None:
        cluster_counts = _cluster_counts_from_query(context.filtered_article_query)
    if context.reference_date is None:
        return []
    reference_date = context.reference_date
    rows = []
    for cluster in clusters:
        counts = {}
        for days in (7, 30, 90):
            last_start = reference_date - timedelta(days=days)
            prev_start = reference_date - timedelta(days=days * 2)
            base_query = _base_analytics_article_query(
                context.filtered_article_query.session,
                source=context.source,
                category=context.category,
            ).filter(
                Article.cluster_id == cluster.cluster_id
            )
            counts[f"last_{days}d"] = base_query.filter(
                Article.publish_date >= last_start,
                Article.publish_date <= reference_date,
            ).count()
            counts[f"prev_{days}d"] = base_query.filter(
                Article.publish_date >= prev_start,
                Article.publish_date < last_start,
            ).count()

        acceleration_7d = acceleration(counts["last_7d"], counts["prev_7d"])
        acceleration_30d = acceleration(counts["last_30d"], counts["prev_30d"])
        acceleration_90d = acceleration(counts["last_90d"], counts["prev_90d"])
        score = 0.5 * acceleration_30d + 0.3 * acceleration_90d + 0.2 * acceleration_7d
        rows.append(
            {
                "cluster_id": str(cluster.cluster_id),
                "name": cluster.cluster_description or f"Cluster {cluster.cluster_id}",
                "paper_count": int(cluster_counts.get(cluster.cluster_id, 0)),
                **counts,
                "acceleration_7d": round(acceleration_7d, 4),
                "acceleration_30d": round(acceleration_30d, 4),
                "acceleration_90d": round(acceleration_90d, 4),
                "score": round(score, 4),
                "color": get_color(cluster.cluster_id),
            }
        )

    return sorted(rows, key=lambda item: (item["last_30d"] > 0, item["score"], item["last_30d"], item["paper_count"]), reverse=True)[:8]


def acceleration(current: int, previous: int) -> float:
    return (current - previous) / max(previous, 1)


def _cluster_quality(article_query, clusters: list[Cluster], cluster_counts: dict[int, int] | None = None) -> dict:
    if cluster_counts is None and hasattr(article_query, "query"):
        cluster_counts = {cluster.cluster_id: int(cluster.article_count or 0) for cluster in clusters}
        article_query = _base_analytics_article_query(article_query)
    cluster_counts = cluster_counts or {}
    total_papers_with_embedding = article_query.filter(Article.embedding.isnot(None)).count()
    outlier_count = article_query.filter(
        Article.embedding.isnot(None),
        Article.cluster_id.is_(None),
    ).count()
    clustered_papers = sum(cluster_counts.values())
    largest_cluster = max(
        clusters,
        key=lambda cluster: cluster_counts.get(cluster.cluster_id, 0),
        default=None,
    )
    largest_count = cluster_counts.get(largest_cluster.cluster_id, 0) if largest_cluster else 0
    representation_scores = [
        _cluster_representation_score(cluster)
        for cluster in clusters
        if _cluster_representation_score(cluster) > 0
    ]
    quality = empty_cluster_quality()
    quality.update(
        {
            "outlierCount": outlier_count,
            "outlierRatio": round(outlier_count / total_papers_with_embedding, 4) if total_papers_with_embedding else 0,
            "largestClusterId": str(largest_cluster.cluster_id) if largest_cluster else None,
            "largestClusterName": (
                largest_cluster.cluster_description or f"Cluster {largest_cluster.cluster_id}"
                if largest_cluster
                else None
            ),
            "largestClusterCount": largest_count or 0,
            "largestClusterRatio": round(largest_count / clustered_papers, 4) if clustered_papers else 0,
            "avgRepresentationScore": round(sum(representation_scores) / len(representation_scores), 4)
            if representation_scores
            else 0,
            "clusteredPapers": clustered_papers,
            "totalPapersWithEmbedding": total_papers_with_embedding,
        }
    )
    return quality


def _normalize_categories(category: str | None = None, categories: list[str] | None = None) -> list[str]:
    values = []
    if category:
        values.append(category)
    values.extend(categories or [])
    return sorted({value.strip() for value in values if value and value.strip()})


def _matching_article_query(
    db: Session,
    cluster_id: int | None = None,
    categories: list[str] | None = None,
    source: str | None = None,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
):
    query = db.query(Article)
    if cluster_id is not None:
        query = query.filter(Article.cluster_id == cluster_id)
    if source:
        query = query.filter(Article.source == source)
    if categories:
        query = query.filter(or_(*[_category_match_clause(item) for item in categories]))
    if period_start:
        query = query.filter(Article.publish_date >= period_start)
    if period_end:
        query = query.filter(Article.publish_date <= period_end)
    return query


def _cluster_articles(
    db: Session,
    cluster: Cluster,
    limit: int | None,
    categories: list[str] | None = None,
    source: str | None = None,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
) -> list[Article]:
    representative_ids = []
    if cluster.metadata_json:
        representative_ids = cluster.metadata_json.get("representative_article_ids") or []
    if not representative_ids and cluster.representative_docs:
        representative_ids = [
            int(value)
            for value in cluster.representative_docs.split(",")
            if value.strip().isdigit()
        ]

    if representative_ids:
        articles = (
            _matching_article_query(
                db,
                cluster_id=cluster.cluster_id,
                categories=categories,
                source=source,
                period_start=period_start,
                period_end=period_end,
            )
            .filter(Article.id.in_(representative_ids))
            .all()
        )
        by_id = {article.id: article for article in articles}
        ordered_articles = [by_id[article_id] for article_id in representative_ids if article_id in by_id]
        if limit is not None and len(ordered_articles) >= limit:
            return ordered_articles[:limit]

        remaining_query = (
            _matching_article_query(
                db,
                cluster_id=cluster.cluster_id,
                categories=categories,
                source=source,
                period_start=period_start,
                period_end=period_end,
            )
            .filter(Article.id.notin_(representative_ids))
        )
        if limit is not None:
            remaining_query = remaining_query.limit(limit - len(ordered_articles))
        remaining = remaining_query.all()
        return ordered_articles + remaining

    query = (
        _matching_article_query(
            db,
            cluster_id=cluster.cluster_id,
            categories=categories,
            source=source,
            period_start=period_start,
            period_end=period_end,
        )
    )
    if limit is not None:
        query = query.limit(limit)
    return query.all()
