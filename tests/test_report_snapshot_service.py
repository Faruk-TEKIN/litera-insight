from datetime import datetime

from backend.app.services.bulletin_snapshot_service import (
    default_previous_week,
    weeks_best_snapshot_key,
)
from backend.app.services.bulletin_validation_service import BulletinValidationService
from backend.app.services.bulletin_candidate_service import BulletinSelection
from backend.app.services.report_snapshot_service import (
    ANALYTICS_SNAPSHOT_KEY,
    ANALYTICS_SCHEMA_VERSION,
    DEFAULT_BULLETIN_INCLUDE_DIGESTS,
    DEFAULT_BULLETIN_LIMIT,
    acceleration,
    analytics_snapshot_key,
    bulletin_snapshot_key,
    default_bulletin_snapshot_key,
    empty_cluster_quality,
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


def test_acceleration_handles_zero_previous_window():
    assert acceleration(5, 0) == 5
    assert acceleration(0, 0) == 0


def test_empty_cluster_quality_avoids_zero_division_defaults():
    quality = empty_cluster_quality()

    assert quality["outlierRatio"] == 0
    assert quality["largestClusterRatio"] == 0
    assert quality["avgRepresentationScore"] == 0


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
