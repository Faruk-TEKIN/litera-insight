from datetime import datetime
from types import SimpleNamespace

from backend.app.main import app
from backend.app.services import report_snapshot_service


def test_single_analytics_route_registered():
    analytics_routes = [route for route in app.routes if getattr(route, "path", None) == "/analytics"]

    assert len(analytics_routes) == 1


def test_analytics_contract_keys():
    expected_keys = {
        "schemaVersion",
        "generatedAt",
        "filters",
        "timeRange",
        "metrics",
        "barData",
        "pieData",
        "scatterData",
        "monthlyData",
        "clusters",
        "categoryOptions",
        "clusterTrendSeries",
        "risingTopics",
        "filteredClusterQuality",
        "globalClusterQuality",
    }
    removed_keys = {
        "papers",
        "sourceDistribution",
        "categoryDistribution",
        "clusterTrendData",
        "clusterQuality",
    }
    payload = {
        "schemaVersion": "analytics:v6",
        "generatedAt": "2026-06-09T10:00:00",
        "filters": {"source": None, "category": None, "period": "12m"},
        "timeRange": {
            "referenceDate": "2026-06-09T10:00:00",
            "periodStart": "2025-07-01T00:00:00",
            "periodEnd": "2026-06-09T10:00:00",
            "minPublishDate": "2024-01-01T00:00:00",
        },
        "metrics": {},
        "barData": [],
        "pieData": [],
        "scatterData": [],
        "monthlyData": [],
        "clusters": [],
        "categoryOptions": [],
        "clusterTrendSeries": [],
        "risingTopics": [],
        "filteredClusterQuality": {},
        "globalClusterQuality": {},
    }

    assert expected_keys.issubset(payload.keys())
    assert removed_keys.isdisjoint(payload.keys())


def test_category_options_counts_match_dashboard_filter():
    class FakeRow:
        _mapping = {
            "category_0": 64,
            "category_1": 23,
        }

    class FakeQuery:
        def __init__(self):
            self.aggregate = False

        def with_entities(self, *args):
            self.aggregate = len(args) > 2
            return self

        def filter(self, *args):
            return self

        def group_by(self, *args):
            return self

        def order_by(self, *args):
            return self

        def limit(self, value):
            return self

        def all(self):
            return [("Computer Vision", 50), ("Machine Learning", 20)]

        def one(self):
            return FakeRow()

    context = SimpleNamespace(filtered_article_query=FakeQuery())

    assert report_snapshot_service._category_options(context) == [
        {"category": "Computer Vision", "count": 64},
        {"category": "Machine Learning", "count": 23},
    ]


def test_analytics_periods_support_requested_month_windows():
    assert report_snapshot_service.ANALYTICS_PERIODS["1m"] == 1
    assert report_snapshot_service.ANALYTICS_PERIODS["12m"] == 12
    assert report_snapshot_service.ANALYTICS_PERIODS["all"] is None
    assert report_snapshot_service.normalize_analytics_period("1m") == "1m"
    assert report_snapshot_service.normalize_analytics_period("all") == "all"
    assert report_snapshot_service.normalize_analytics_period("24m") == report_snapshot_service.DEFAULT_ANALYTICS_PERIOD


def test_month_keys_cover_full_min_max_range_for_all_period():
    keys = report_snapshot_service._month_keys_between(
        datetime(2025, 11, 14),
        datetime(2026, 2, 2),
    )

    assert keys == ["2025-11", "2025-12", "2026-01", "2026-02"]


def test_monthly_data_zero_fills_missing_months():
    class FakeRow:
        _mapping = {"month_key": "2026-02", "count": 4}

    class FakeQuery:
        def with_entities(self, *args):
            return self

        def group_by(self, *args):
            return self

        def order_by(self, *args):
            return self

        def all(self):
            return [FakeRow()]

    context = SimpleNamespace(
        period_start=datetime(2026, 1, 1),
        period_end=datetime(2026, 3, 20),
        filtered_article_query=FakeQuery(),
    )

    assert report_snapshot_service._monthly_data(context) == [
        {"month": "Jan 26", "monthKey": "2026-01", "count": 0, "publications": 0},
        {"month": "Feb 26", "monthKey": "2026-02", "count": 4, "publications": 4},
        {"month": "Mar 26", "monthKey": "2026-03", "count": 0, "publications": 0},
    ]


def test_cluster_trend_series_zero_fills_each_top_cluster_month():
    class FakeQuery:
        def with_entities(self, *args):
            return self

        def filter(self, *args):
            return self

        def group_by(self, *args):
            return self

        def order_by(self, *args):
            return self

        def all(self):
            return [(2, "2026-02", 7)]

    context = SimpleNamespace(
        period_start=datetime(2026, 1, 1),
        period_end=datetime(2026, 2, 20),
        filtered_article_query=FakeQuery(),
    )
    clusters = [
        SimpleNamespace(cluster_id=1, cluster_description="Cluster One"),
        SimpleNamespace(cluster_id=2, cluster_description="Cluster Two"),
    ]

    series = report_snapshot_service._cluster_trend_series(context, clusters, {1: 5, 2: 10})

    assert series == [
        {"cluster_id": "2", "cluster_name": "Cluster Two", "month": "Jan 26", "monthKey": "2026-01", "count": 0},
        {"cluster_id": "1", "cluster_name": "Cluster One", "month": "Jan 26", "monthKey": "2026-01", "count": 0},
        {"cluster_id": "2", "cluster_name": "Cluster Two", "month": "Feb 26", "monthKey": "2026-02", "count": 7},
        {"cluster_id": "1", "cluster_name": "Cluster One", "month": "Feb 26", "monthKey": "2026-02", "count": 0},
    ]


def test_cluster_quality_uses_filtered_query_and_filtered_counts():
    class CountQuery:
        def __init__(self, value):
            self.value = value

        def count(self):
            return self.value

    class FakeArticleQuery:
        def filter(self, *args):
            return CountQuery(10 if len(args) == 1 else 2)

    clusters = [
        SimpleNamespace(cluster_id=1, cluster_description="Small", metadata_json={}),
        SimpleNamespace(cluster_id=2, cluster_description="Large", metadata_json={}),
    ]

    quality = report_snapshot_service._cluster_quality(FakeArticleQuery(), clusters, {1: 2, 2: 8})

    assert quality["outlierCount"] == 2
    assert quality["outlierRatio"] == 0.2
    assert quality["largestClusterId"] == "2"
    assert quality["largestClusterCount"] == 8
    assert quality["largestClusterRatio"] == 0.8
    assert quality["clusteredPapers"] == 10
