from types import SimpleNamespace

from backend.app.services.notification_service import (
    CHANNEL_IN_APP,
    CHANNEL_TELEGRAM,
    DELIVERY_PENDING,
    DELIVERY_SENT,
    NotificationService,
)


class FakeDb:
    def __init__(self):
        self.added = []
        self.commits = 0
        self.rollbacks = 0

    def add(self, item):
        self.added.append(item)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def refresh(self, item):
        if getattr(item, "id", None) is None:
            item.id = 101

    def query(self, model):
        return SimpleNamespace(
            filter=lambda *args, **kwargs: SimpleNamespace(first=lambda: None),
            count=lambda: 0,
        )


def test_create_weeks_best_notification_creates_in_app_and_telegram_delivery():
    db = FakeDb()
    deliveries = []
    queued = []
    service = NotificationService(db)
    service._find_existing = lambda user_id, notification_type, snapshot_key: None
    service._create_delivery = lambda notification_id, channel, status, sent_at=None: deliveries.append(
        SimpleNamespace(id=len(deliveries) + 1, channel=channel, status=status, sent_at=sent_at)
    ) or deliveries[-1]
    service._enqueue_delivery = lambda delivery_id: queued.append(delivery_id)

    notification = service.create_weeks_best_generated(
        7,
        {
            "status": "validated",
            "snapshot_key": "weeks_best_bulletin:v1:abc",
            "selection_type": "cluster",
            "selection_id": "42",
            "selection_label": "Graph Neural Networks",
            "week_start": "2026-06-08",
            "week_end": "2026-06-14",
            "metadata": {"selected_count": 5},
        },
    )

    assert notification is not None
    assert notification.user_id == 7
    assert notification.related_snapshot_key == "weeks_best_bulletin:v1:abc"
    assert notification.payload_json["selection_id"] == "42"
    assert notification.payload_json["selected_count"] == 5
    assert [(delivery.channel, delivery.status) for delivery in deliveries] == [
        (CHANNEL_IN_APP, DELIVERY_SENT),
        (CHANNEL_TELEGRAM, DELIVERY_PENDING),
    ]
    assert queued == [2]
    assert db.commits == 2


def test_create_weeks_best_notification_skips_non_validated_payload():
    service = NotificationService(FakeDb())

    notification = service.create_weeks_best_generated(
        7,
        {"status": "failed", "snapshot_key": "weeks_best_bulletin:v1:abc"},
    )

    assert notification is None


def test_create_weeks_best_notification_returns_existing_duplicate():
    existing = SimpleNamespace(id=5)
    service = NotificationService(FakeDb())
    service._find_existing = lambda user_id, notification_type, snapshot_key: existing

    notification = service.create_weeks_best_generated(
        7,
        {"status": "validated", "snapshot_key": "weeks_best_bulletin:v1:abc"},
    )

    assert notification is existing
