from datetime import datetime
from types import SimpleNamespace

from backend.app.services.report_snapshot_service import (
    DEFAULT_BULLETIN_INCLUDE_DIGESTS,
    bulletin_snapshot_key,
)
from backend.app.services.user_bulletin_service import USER_BULLETIN_PAPER_LIMIT, UserBulletinService


def test_user_bulletin_refreshes_legacy_limited_snapshot_without_limit():
    cluster_paper_count = 57
    old_key = bulletin_snapshot_key(
        limit=10,
        include_digests=DEFAULT_BULLETIN_INCLUDE_DIGESTS,
        cluster_ids=[42],
    )
    expected_key = bulletin_snapshot_key(
        limit=USER_BULLETIN_PAPER_LIMIT,
        include_digests=DEFAULT_BULLETIN_INCLUDE_DIGESTS,
        cluster_ids=[42],
    )
    preference = SimpleNamespace(
        selection_type="clusters",
        selected_cluster_ids_json=[42],
        selected_categories_json=[],
        bulletin_snapshot_key=old_key,
        notifications_enabled=True,
        notification_frequency="weekly",
        last_generated_at=None,
        created_at=datetime(2026, 6, 1),
        updated_at=datetime(2026, 6, 1),
    )

    class FakeSnapshots:
        def __init__(self):
            self.limit = None

        def refresh_bulletin_snapshot(self, **kwargs):
            self.limit = kwargs["limit"]
            paper_count = cluster_paper_count if self.limit is None else self.limit
            return [{"cluster": {"id": "42"}, "papers": [{"id": str(index)} for index in range(paper_count)]}]

    class FakeDb:
        def __init__(self):
            self.committed = False

        def commit(self):
            self.committed = True

    service = UserBulletinService.__new__(UserBulletinService)
    service.db = FakeDb()
    service.snapshots = FakeSnapshots()
    service._get_preference = lambda user_id: preference
    service._get_snapshot = lambda snapshot_key: SimpleNamespace(payload_json=[{"old": True}])

    response = service.get_user_bulletin(user_id=1)

    assert service.snapshots.limit is None
    assert USER_BULLETIN_PAPER_LIMIT is None
    assert preference.bulletin_snapshot_key == expected_key
    assert service.db.committed is True
    assert len(response["bulletin"][0]["papers"]) == cluster_paper_count
