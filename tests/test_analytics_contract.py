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
        "metrics",
        "barData",
        "pieData",
        "scatterData",
        "monthlyData",
        "clusters",
        "papers",
        "sourceDistribution",
        "categoryDistribution",
        "clusterTrendData",
        "clusterTrendSeries",
        "risingTopics",
        "clusterQuality",
    }
    payload = {
        "schemaVersion": "analytics:v5",
        "generatedAt": "2026-06-09T10:00:00",
        "filters": {"source": None, "category": None, "period": "12m"},
        "metrics": {},
        "barData": [],
        "pieData": [],
        "scatterData": [],
        "monthlyData": [],
        "clusters": [],
        "papers": [],
        "sourceDistribution": [],
        "categoryDistribution": [],
        "clusterTrendData": [],
        "clusterTrendSeries": [],
        "risingTopics": [],
        "clusterQuality": {},
    }

    assert expected_keys.issubset(payload.keys())


def test_category_distribution_counts_match_dashboard_filter(monkeypatch):
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

    def fake_filtered_articles_query(db, source=None, category=None, period="12m"):
        return FakeQuery()

    monkeypatch.setattr(report_snapshot_service, "_filtered_articles_query", fake_filtered_articles_query)

    assert report_snapshot_service._category_distribution(object()) == [
        {"category": "Computer Vision", "count": 64},
        {"category": "Machine Learning", "count": 23},
    ]


def test_analytics_periods_support_requested_month_windows():
    assert report_snapshot_service.ANALYTICS_PERIODS["1m"] == 30
    assert report_snapshot_service.ANALYTICS_PERIODS["all"] is None
    assert report_snapshot_service.normalize_analytics_period("1m") == "1m"
    assert report_snapshot_service.normalize_analytics_period("all") == "all"
    assert report_snapshot_service.normalize_analytics_period("24m") == report_snapshot_service.DEFAULT_ANALYTICS_PERIOD
