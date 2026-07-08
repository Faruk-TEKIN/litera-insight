from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

# from database.models.Notification import Notification
# from database.models.NotificationDelivery import NotificationDelivery
from database.models.UserBulletinPreference import UserBulletinPreference
# from database.models.UserTelegramAccount import UserTelegramAccount


NOTIFICATION_TYPE_WEEKS_BEST = "weeks_best_generated"
CHANNEL_IN_APP = "in_app"
CHANNEL_TELEGRAM = "telegram"
DELIVERY_PENDING = "pending"
DELIVERY_SENT = "sent"
DELIVERY_FAILED = "failed"
DELIVERY_SKIPPED = "skipped"


class NotificationService:
    def __init__(self, db: Session):
        self.db = db

    def create_weeks_best_generated(
        self,
        user_id: int,
        bulletin_payload: dict,
        enable_telegram: bool = True,
        enqueue_delivery: bool = True,
    ) -> Notification | None:
        if bulletin_payload.get("status") != "validated":
            return None

        snapshot_key = bulletin_payload.get("snapshot_key")
        if not snapshot_key:
            return None

        preference = (
            self.db.query(UserBulletinPreference)
            .filter(UserBulletinPreference.user_id == user_id)
            .first()
        )
        if preference is not None and not preference.notifications_enabled:
            return None

        existing = self._find_existing(user_id, NOTIFICATION_TYPE_WEEKS_BEST, snapshot_key)
        if existing is not None:
            return existing

        now = _utcnow_naive()
        selection_label = bulletin_payload.get("selection_label") or "selected topic"
        week_start = bulletin_payload.get("week_start")
        week_end = bulletin_payload.get("week_end")
        title = "Week's Best is ready"
        body = f"{selection_label} bulletin for {week_start} - {week_end} is ready."
        payload = {
            "snapshot_key": snapshot_key,
            "selection_type": bulletin_payload.get("selection_type"),
            "selection_id": bulletin_payload.get("selection_id"),
            "selection_label": selection_label,
            "week_start": week_start,
            "week_end": week_end,
            "status": bulletin_payload.get("status"),
            "selected_count": (bulletin_payload.get("metadata") or {}).get("selected_count"),
            "document_format": "markdown",
        }
        notification = Notification(
            user_id=user_id,
            type=NOTIFICATION_TYPE_WEEKS_BEST,
            title=title,
            body=body,
            payload_json=payload,
            related_snapshot_key=snapshot_key,
            created_at=now,
            updated_at=now,
        )
        self.db.add(notification)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            return self._find_existing(user_id, NOTIFICATION_TYPE_WEEKS_BEST, snapshot_key)

        self.db.refresh(notification)
        in_app = self._create_delivery(notification.id, CHANNEL_IN_APP, DELIVERY_SENT, sent_at=now)
        telegram = None
        if enable_telegram:
            telegram = self._create_delivery(notification.id, CHANNEL_TELEGRAM, DELIVERY_PENDING)
        self.db.commit()

        if enqueue_delivery and telegram is not None:
            self._enqueue_delivery(telegram.id)

        return notification

    def list_notifications(self, user_id: int, limit: int = 20, unread_only: bool = False) -> dict:
        query = self.db.query(Notification).filter(Notification.user_id == user_id)
        if unread_only:
            query = query.filter(Notification.read_at.is_(None))
        notifications = query.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit).all()
        return {
            "items": [self.format_notification(notification) for notification in notifications],
            "unread_count": self.unread_count(user_id),
        }

    def unread_count(self, user_id: int) -> int:
        return (
            self.db.query(Notification)
            .filter(Notification.user_id == user_id, Notification.read_at.is_(None))
            .count()
        )

    def mark_read(self, user_id: int, notification_id: int) -> dict | None:
        notification = (
            self.db.query(Notification)
            .filter(Notification.id == notification_id, Notification.user_id == user_id)
            .first()
        )
        if notification is None:
            return None
        if notification.read_at is None:
            now = _utcnow_naive()
            notification.read_at = now
            notification.updated_at = now
            self.db.commit()
            self.db.refresh(notification)
        return self.format_notification(notification)

    def mark_all_read(self, user_id: int) -> dict:
        now = _utcnow_naive()
        updated = (
            self.db.query(Notification)
            .filter(Notification.user_id == user_id, Notification.read_at.is_(None))
            .update({Notification.read_at: now, Notification.updated_at: now}, synchronize_session=False)
        )
        self.db.commit()
        return {"updated": updated, "unread_count": 0}

    def pending_telegram_deliveries(self, limit: int = 100) -> list[NotificationDelivery]:
        now = _utcnow_naive()
        return (
            self.db.query(NotificationDelivery)
            .filter(NotificationDelivery.channel == CHANNEL_TELEGRAM)
            .filter(NotificationDelivery.status == DELIVERY_PENDING)
            .filter(
                (NotificationDelivery.next_attempt_at.is_(None))
                | (NotificationDelivery.next_attempt_at <= now)
            )
            .order_by(NotificationDelivery.created_at.asc())
            .limit(limit)
            .all()
        )

    def _find_existing(self, user_id: int, notification_type: str, snapshot_key: str) -> Notification | None:
        return (
            self.db.query(Notification)
            .filter(
                Notification.user_id == user_id,
                Notification.type == notification_type,
                Notification.related_snapshot_key == snapshot_key,
            )
            .first()
        )

    def _create_delivery(
        self,
        notification_id: int,
        channel: str,
        status: str,
        sent_at: datetime | None = None,
    ) -> NotificationDelivery:
        now = _utcnow_naive()
        delivery = NotificationDelivery(
            notification_id=notification_id,
            channel=channel,
            status=status,
            attempt_count=0,
            sent_at=sent_at,
            created_at=now,
            updated_at=now,
        )
        self.db.add(delivery)
        self.db.flush()
        return delivery

    def _enqueue_delivery(self, delivery_id: int) -> None:
        try:
            from backend.worker.tasks import dispatch_notification_delivery

            dispatch_notification_delivery.delay(delivery_id)
        except Exception as exc:
            delivery = self.db.query(NotificationDelivery).filter(NotificationDelivery.id == delivery_id).first()
            if delivery is not None:
                delivery.last_error = f"Delivery queued locally but broker dispatch failed: {exc}"
                delivery.updated_at = _utcnow_naive()
                self.db.commit()

    @staticmethod
    def format_notification(notification: Notification) -> dict:
        return {
            "id": notification.id,
            "type": notification.type,
            "title": notification.title,
            "body": notification.body,
            "payload": notification.payload_json or {},
            "related_snapshot_key": notification.related_snapshot_key,
            "read_at": notification.read_at.isoformat() if notification.read_at else None,
            "created_at": notification.created_at.isoformat() if notification.created_at else None,
        }


def user_has_enabled_telegram(db: Session, user_id: int) -> bool:
    account = (
        db.query(UserTelegramAccount)
        .filter(UserTelegramAccount.user_id == user_id, UserTelegramAccount.is_enabled.is_(True))
        .first()
    )
    return account is not None


def _utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
