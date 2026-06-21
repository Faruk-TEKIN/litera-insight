from __future__ import annotations

from datetime import UTC, datetime, timedelta
import re

from sqlalchemy.orm import Session

from backend.app.services.notification_service import (
    CHANNEL_TELEGRAM,
    DELIVERY_FAILED,
    DELIVERY_PENDING,
    DELIVERY_SENT,
    DELIVERY_SKIPPED,
)
from backend.app.services.telegram_bot_service import TelegramBotService
from database.models.Notification import Notification
from database.models.NotificationDelivery import NotificationDelivery
from database.models.ReportSnapshot import ReportSnapshot
from database.models.UserTelegramAccount import UserTelegramAccount


MAX_DELIVERY_ATTEMPTS = 3
RETRY_DELAYS = (timedelta(minutes=1), timedelta(minutes=5), timedelta(minutes=30))


class NotificationDeliveryService:
    def __init__(self, db: Session, telegram: TelegramBotService | None = None):
        self.db = db
        self.telegram = telegram

    def dispatch(self, delivery_id: int) -> dict:
        delivery = self.db.query(NotificationDelivery).filter(NotificationDelivery.id == delivery_id).first()
        if delivery is None:
            return {"status": "missing"}
        if delivery.channel != CHANNEL_TELEGRAM:
            return {"status": "ignored"}
        if delivery.status != DELIVERY_PENDING:
            return {"status": delivery.status}

        notification = (
            self.db.query(Notification)
            .filter(Notification.id == delivery.notification_id)
            .first()
        )
        if notification is None:
            self._mark_skipped(delivery, "Notification not found.")
            return {"status": DELIVERY_SKIPPED}

        account = (
            self.db.query(UserTelegramAccount)
            .filter(
                UserTelegramAccount.user_id == notification.user_id,
                UserTelegramAccount.is_enabled.is_(True),
            )
            .first()
        )
        if account is None:
            self._mark_skipped(delivery, "Telegram account is not linked.")
            return {"status": DELIVERY_SKIPPED}

        snapshot_key = (notification.payload_json or {}).get("snapshot_key") or notification.related_snapshot_key
        snapshot = self.db.query(ReportSnapshot).filter(ReportSnapshot.snapshot_key == snapshot_key).first()
        if snapshot is None:
            self._mark_failed_or_retry(delivery, "Week's Best snapshot not found.")
            return {"status": delivery.status}

        payload = snapshot.payload_json or {}
        markdown = payload.get("full_markdown") or ""
        if not markdown:
            self._mark_failed_or_retry(delivery, "Week's Best markdown content is empty.")
            return {"status": delivery.status}

        try:
            telegram = self.telegram or TelegramBotService()
            message_result = telegram.send_message(account.telegram_chat_id, self._summary_message(payload))
            document_result = telegram.send_document(
                account.telegram_chat_id,
                self._filename(payload),
                markdown,
                caption="Full Week's Best bulletin",
            )
        except Exception as exc:
            account.last_error = str(exc)
            account.updated_at = _utcnow_naive()
            self._mark_failed_or_retry(delivery, str(exc))
            return {"status": delivery.status, "error": str(exc)}

        message_id = document_result.get("message_id") or message_result.get("message_id")
        now = _utcnow_naive()
        delivery.status = DELIVERY_SENT
        delivery.attempt_count += 1
        delivery.last_error = None
        delivery.next_attempt_at = None
        delivery.external_message_id = str(message_id) if message_id is not None else None
        delivery.sent_at = now
        delivery.updated_at = now
        account.last_error = None
        account.updated_at = now
        self.db.commit()
        return {"status": DELIVERY_SENT, "external_message_id": delivery.external_message_id}

    def _mark_skipped(self, delivery: NotificationDelivery, reason: str) -> None:
        now = _utcnow_naive()
        delivery.status = DELIVERY_SKIPPED
        delivery.last_error = reason
        delivery.updated_at = now
        self.db.commit()

    def _mark_failed_or_retry(self, delivery: NotificationDelivery, reason: str) -> None:
        now = _utcnow_naive()
        delivery.attempt_count += 1
        delivery.last_error = reason
        delivery.updated_at = now
        if delivery.attempt_count >= MAX_DELIVERY_ATTEMPTS:
            delivery.status = DELIVERY_FAILED
            delivery.next_attempt_at = None
        else:
            delay = RETRY_DELAYS[min(delivery.attempt_count - 1, len(RETRY_DELAYS) - 1)]
            delivery.status = DELIVERY_PENDING
            delivery.next_attempt_at = now + delay
        self.db.commit()

    @staticmethod
    def _summary_message(payload: dict) -> str:
        metadata = payload.get("metadata") or {}
        return "\n".join(
            [
                f"Week's Best ready: {payload.get('selection_label') or 'selected topic'}",
                f"Period: {payload.get('week_start')} - {payload.get('week_end')}",
                f"Selected papers: {metadata.get('selected_count') or 0}",
                "",
                "The full bulletin is attached as Markdown.",
            ]
        )

    @staticmethod
    def _filename(payload: dict) -> str:
        raw = "_".join(
            [
                "weeks_best",
                str(payload.get("selection_type") or "topic"),
                str(payload.get("selection_id") or "selection"),
                str(payload.get("week_start") or "start"),
                str(payload.get("week_end") or "end"),
            ]
        )
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw).strip("_")
        return f"{safe}.md"


def _utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
