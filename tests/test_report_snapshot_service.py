from datetime import datetime
from types import SimpleNamespace

from backend.app.services.bulletin_snapshot_service import (
    BulletinSnapshotService,
    default_previous_week,
    weeks_best_snapshot_key,
)
from backend.app.schemas.bulletin import WeeksBestBulletinRequest
from backend.app.services.bulletin_generation_service import BulletinGenerationService
from backend.app.services.bulletin_validation_service import BulletinValidationService
from backend.app.services.bulletin_candidate_service import BulletinSelection
from backend.app.services.report_snapshot_service import (
    ANALYTICS_SNAPSHOT_KEY,
    ANALYTICS_SCHEMA_VERSION,
    DEFAULT_BULLETIN_INCLUDE_DIGESTS,
    DEFAULT_BULLETIN_LIMIT,
    LEGACY_ANALYTICS_SNAPSHOT_KEY,
    ReportSnapshotService,
    acceleration,
    analytics_snapshot_key,
    bulletin_snapshot_key,
    default_bulletin_snapshot_key,
    empty_cluster_quality,
    _clusters_from_counts,
)
from database.db import Base
from database.models.ReportSnapshot import ReportSnapshot


def test_report_snapshot_model_registered():
    assert ReportSnapshot.__tablename__ in Base.metadata.tables


def test_analytics_snapshot_key_is_stable():
    assert ANALYTICS_SNAPSHOT_KEY == analytics_snapshot_key()
    assert ANALYTICS_SNAPSHOT_KEY.startswith(f"{ANALYTICS_SCHEMA_VERSION}:")


def test_analytics_snapshot_key_changes_with_filters():
    base_key = analytics_snapshot_key()
    filtered_key = analytics_snapshot_key(source="arxiv", category="cs.CL", period="3m")

    assert filtered_key.startswith(f"{ANALYTICS_SCHEMA_VERSION}:")
    assert base_key != filtered_key


def test_default_analytics_does_not_fall_back_to_legacy_snapshot():
    class FakeAnalyticsService(ReportSnapshotService):
        def __init__(self):
            super().__init__(db=object())
            self.refreshed = False

        def _get_snapshot(self, snapshot_key):
            if snapshot_key == LEGACY_ANALYTICS_SNAPSHOT_KEY:
                return SimpleNamespace(payload_json={"filters": {"period": "all"}, "metrics": {"totalPapers": 999}})
            return None

        def _analytics_data_fingerprint(self):
            return "fingerprint"

        def refresh_analytics_snapshot(self, source=None, category=None, period="12m"):
            self.refreshed = True
            return {"filters": {"period": period}, "metrics": {"totalPapers": 12}}

    service = FakeAnalyticsService()
    payload = service.get_analytics(period="12m")

    assert service.refreshed is True
    assert payload["filters"]["period"] == "12m"
    assert payload["metrics"]["totalPapers"] == 12


def test_analytics_snapshot_refreshes_when_data_fingerprint_changes():
    class FakeAnalyticsService(ReportSnapshotService):
        def __init__(self):
            super().__init__(db=object())
            self.refreshed = False

        def _analytics_data_fingerprint(self):
            return "new"

        def _get_snapshot(self, snapshot_key):
            return SimpleNamespace(
                payload_json={"filters": {"period": "12m"}, "metrics": {"totalPapers": 999}},
                metadata_json={"dataFingerprint": "old"},
            )

        def refresh_analytics_snapshot(self, source=None, category=None, period="12m"):
            self.refreshed = True
            return {"filters": {"period": period}, "metrics": {"totalPapers": 12}}

    service = FakeAnalyticsService()
    payload = service.get_analytics(period="12m")

    assert service.refreshed is True
    assert payload["metrics"]["totalPapers"] == 12


def test_analytics_snapshot_uses_cache_when_data_fingerprint_matches():
    class FakeAnalyticsService(ReportSnapshotService):
        def __init__(self):
            super().__init__(db=object())
            self.refreshed = False

        def _analytics_data_fingerprint(self):
            return "same"

        def _get_snapshot(self, snapshot_key):
            return SimpleNamespace(
                payload_json={"filters": {"period": "12m"}, "metrics": {"totalPapers": 999}},
                metadata_json={"dataFingerprint": "same"},
            )

        def refresh_analytics_snapshot(self, source=None, category=None, period="12m"):
            self.refreshed = True
            return {"filters": {"period": period}, "metrics": {"totalPapers": 12}}

    service = FakeAnalyticsService()
    payload = service.get_analytics(period="12m")

    assert service.refreshed is False
    assert payload["metrics"]["totalPapers"] == 999


def test_acceleration_handles_zero_previous_window():
    assert acceleration(5, 0) == 5
    assert acceleration(0, 0) == 0


def test_empty_cluster_quality_avoids_zero_division_defaults():
    quality = empty_cluster_quality()

    assert quality["outlierRatio"] == 0
    assert quality["largestClusterRatio"] == 0
    assert quality["avgRepresentationScore"] == 0


def test_clusters_from_counts_falls_back_when_cluster_metadata_is_missing():
    clusters = _clusters_from_counts({42: 15, 7: 30}, [])

    assert [cluster.cluster_id for cluster in clusters] == [7, 42]
    assert [cluster.article_count for cluster in clusters] == [30, 15]
    assert clusters[0].cluster_description == "Cluster 7"


def test_clusters_from_counts_keeps_existing_cluster_metadata():
    existing = SimpleNamespace(
        cluster_id=42,
        cluster_description="Vision Transformers",
        article_count=0,
        metadata_json={},
        created_at=None,
    )

    clusters = _clusters_from_counts({42: 15}, [existing])

    assert clusters == [existing]
    assert clusters[0].cluster_description == "Vision Transformers"
    assert clusters[0].article_count == 0


def test_clusters_from_counts_sorts_by_filtered_count_not_global_count():
    large_global = SimpleNamespace(
        cluster_id=1,
        cluster_description="Large Global",
        article_count=500,
        metadata_json={},
        created_at=None,
    )
    large_filtered = SimpleNamespace(
        cluster_id=2,
        cluster_description="Large Filtered",
        article_count=10,
        metadata_json={},
        created_at=None,
    )

    clusters = _clusters_from_counts({1: 5, 2: 30}, [large_global, large_filtered])

    assert [cluster.cluster_id for cluster in clusters] == [2, 1]


def test_default_bulletin_snapshot_key_matches_default_params():
    assert default_bulletin_snapshot_key() == bulletin_snapshot_key(
        limit=DEFAULT_BULLETIN_LIMIT,
        include_digests=DEFAULT_BULLETIN_INCLUDE_DIGESTS,
    )


def test_bulletin_snapshot_key_changes_with_filters():
    base_key = bulletin_snapshot_key(limit=50, include_digests=True)
    filtered_key = bulletin_snapshot_key(
        limit=50,
        include_digests=True,
        period_start=datetime(2026, 1, 1),
        category="cs.AI",
        source="arxiv",
    )

    assert base_key.startswith("bulletin:v1:")
    assert filtered_key.startswith("bulletin:v1:")
    assert base_key != filtered_key


def test_weeks_best_snapshot_key_is_stable_and_scoped():
    base_key = weeks_best_snapshot_key(
        selection_type="cluster",
        selection_id="42",
        week_start=datetime(2026, 6, 8).date(),
        week_end=datetime(2026, 6, 14).date(),
    )
    category_key = weeks_best_snapshot_key(
        selection_type="category",
        selection_id="cs.AI",
        week_start=datetime(2026, 6, 8).date(),
        week_end=datetime(2026, 6, 14).date(),
    )

    assert base_key.startswith("weeks_best_bulletin:v1:")
    assert base_key == weeks_best_snapshot_key(
        selection_type="cluster",
        selection_id="42",
        week_start=datetime(2026, 6, 8).date(),
        week_end=datetime(2026, 6, 14).date(),
    )
    assert base_key != category_key
    assert base_key != weeks_best_snapshot_key(
        selection_type="cluster",
        selection_id="42",
        week_start=datetime(2026, 6, 8).date(),
        week_end=datetime(2026, 6, 14).date(),
        use_llm=False,
    )
    assert base_key != weeks_best_snapshot_key(
        selection_type="cluster",
        selection_id="42",
        week_start=datetime(2026, 6, 8).date(),
        week_end=datetime(2026, 6, 14).date(),
        model_name="another-model",
    )


def test_weeks_best_request_uses_ollama_by_default():
    request = WeeksBestBulletinRequest(
        selection_type="category",
        selection_id="cs.AI",
        week_start=datetime(2026, 6, 8).date(),
        week_end=datetime(2026, 6, 14).date(),
    )

    assert request.use_llm is True


def test_weeks_best_get_or_generate_retries_failed_snapshot(monkeypatch):
    class FailedSnapshot:
        payload_json = {"status": "failed"}

    service = BulletinSnapshotService.__new__(BulletinSnapshotService)
    monkeypatch.setattr(service, "_get_snapshot", lambda key: FailedSnapshot())

    def fake_generate(selection_type, selection_id, week_start, week_end, use_llm=True):
        return {"status": "validated", "selection_id": selection_id, "use_llm": use_llm}

    monkeypatch.setattr(service, "generate", fake_generate)

    result = service.get_or_generate(
        selection_type="category",
        selection_id="cs.AI",
        week_start=datetime(2026, 6, 8).date(),
        week_end=datetime(2026, 6, 14).date(),
    )

    assert result == {"status": "validated", "selection_id": "cs.AI", "use_llm": True}


def test_weeks_best_generation_marks_deterministic_fallback(monkeypatch):
    class FailingOllama:
        model = "gemma4:e4b"

        def generate(self, prompt: str) -> str:
            raise RuntimeError("ollama is unavailable")

    monkeypatch.setattr(
        "backend.app.services.bulletin_generation_service.get_ollama_service",
        lambda: FailingOllama(),
    )
    selection = BulletinSelection(
        selection_type="category",
        selection_id="cs.AI",
        selection_label="cs.AI",
        week_start=datetime(2026, 6, 8),
        week_end=datetime(2026, 6, 14, 23, 59, 59),
    )
    cards = [
        {
            "source_id": "S1",
            "article_id": 1,
            "title": "A Reliable RAG Evaluation Method",
            "authors": ["Alice"],
            "published_date": "2026-06-10",
            "source": "arxiv",
            "doi": "10.1000/example",
            "pdf_url": None,
            "url": None,
            "one_sentence_summary": "This paper evaluates retrieval augmented generation systems with auditable evidence.",
        }
    ]

    bulletin = BulletinGenerationService(use_llm=True).generate(selection, cards)

    assert bulletin["generation_source"] == "deterministic_fallback"
    assert bulletin["llm_error"] == "Ollama generation failed; deterministic fallback was used."
    assert "A Reliable RAG Evaluation Method" in bulletin["full_markdown"]


def test_default_previous_week_uses_monday_to_sunday_window():
    week_start, week_end = default_previous_week(today=datetime(2026, 6, 12).date())

    assert week_start.isoformat() == "2026-06-01"
    assert week_end.isoformat() == "2026-06-07"


def test_weeks_best_validation_rejects_unknown_citations():
    selection = BulletinSelection(
        selection_type="category",
        selection_id="cs.AI",
        selection_label="cs.AI",
        week_start=datetime(2026, 6, 8),
        week_end=datetime(2026, 6, 14, 23, 59, 59),
    )
    cards = [
        {
            "source_id": "S1",
            "article_id": 1,
            "title": "A Reliable RAG Evaluation Method",
            "published_date": "2026-06-10",
        }
    ]
    bulletin = {
        "full_markdown": "\n".join(
            [
                "# Week's Best - cs.AI",
                "## Editorial Lead",
                "Claim [S2]",
                "## Top Papers",
                "### 1. A Reliable RAG Evaluation Method",
                "## Emerging Trend",
                "Trend [S1]",
                "## Why It Matters",
                "Reason [S1]",
                "## Papers to Watch",
                "- None",
                "## Sources",
                "[S1] A Reliable RAG Evaluation Method",
            ]
        )
    }

    result = BulletinValidationService().validate(selection, cards, bulletin)

    assert result["valid"] is False
    assert any("Unknown cited source ids" in error for error in result["errors"])


def test_weeks_best_validation_accepts_numbered_top_papers_list():
    selection = BulletinSelection(
        selection_type="category",
        selection_id="cs.AI",
        selection_label="cs.AI",
        week_start=datetime(2026, 6, 8),
        week_end=datetime(2026, 6, 14, 23, 59, 59),
    )
    cards = [
        {
            "source_id": "S1",
            "article_id": 1,
            "title": "A Reliable RAG Evaluation Method",
            "published_date": "2026-06-10",
        }
    ]
    bulletin = {
        "full_markdown": "\n".join(
            [
                "# Week's Best - cs.AI",
                "## Editorial Lead",
                "Claim [S1]",
                "## Top Papers",
                "1. **A Reliable RAG Evaluation Method** - A concise source-grounded summary. [S1]",
                "## Emerging Trend",
                "Trend [S1]",
                "## Why It Matters",
                "Reason [S1]",
                "## Papers to Watch",
                "- None",
                "## Sources",
                "[S1] A Reliable RAG Evaluation Method",
            ]
        )
    }

    result = BulletinValidationService().validate(selection, cards, bulletin)

    assert result["valid"] is True


def test_weeks_best_validation_rejects_empty_top_papers_section():
    selection = BulletinSelection(
        selection_type="category",
        selection_id="cs.AI",
        selection_label="cs.AI",
        week_start=datetime(2026, 6, 8),
        week_end=datetime(2026, 6, 14, 23, 59, 59),
    )
    cards = [
        {
            "source_id": "S1",
            "article_id": 1,
            "title": "A Reliable RAG Evaluation Method",
            "published_date": "2026-06-10",
        }
    ]
    bulletin = {
        "full_markdown": "\n".join(
            [
                "# Week's Best - cs.AI",
                "## Editorial Lead",
                "Claim [S1]",
                "## Top Papers",
                "",
                "## Emerging Trend",
                "Trend [S1]",
                "## Why It Matters",
                "Reason [S1]",
                "## Papers to Watch",
                "- None",
                "## Sources",
                "[S1] A Reliable RAG Evaluation Method",
            ]
        )
    }

    result = BulletinValidationService().validate(selection, cards, bulletin)

    assert result["valid"] is False
    assert "Top Papers section is empty." in result["errors"]
