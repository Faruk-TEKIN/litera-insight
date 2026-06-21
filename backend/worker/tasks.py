from backend.worker.scheduler import app
from backend.app.core.database import SessionLocal
from backend.app.services.bulletin_snapshot_service import BulletinSnapshotService, default_previous_week
from backend.app.services.notification_delivery_service import NotificationDeliveryService
from backend.app.services.notification_service import NotificationService
from database.models.UserBulletinPreference import UserBulletinPreference


@app.task(bind=True, max_retries=3)
def dispatch_notification_delivery(self, delivery_id: int):
    db = SessionLocal()
    try:
        return NotificationDeliveryService(db).dispatch(delivery_id)
    except Exception as exc:
        raise self.retry(exc=exc)
    finally:
        db.close()


@app.task
def dispatch_pending_notification_deliveries(limit: int = 100):
    db = SessionLocal()
    try:
        deliveries = NotificationService(db).pending_telegram_deliveries(limit=limit)
        delivery_ids = [delivery.id for delivery in deliveries]
        for delivery_id in delivery_ids:
            dispatch_notification_delivery.delay(delivery_id)
        return {"queued": len(delivery_ids), "delivery_ids": delivery_ids}
    finally:
        db.close()


@app.task
def generate_weeks_best_for_user(
    user_id: int,
    selection_type: str,
    selection_id: str,
    week_start: str,
    week_end: str,
    use_llm: bool = True,
):
    db = SessionLocal()
    try:
        bulletin = BulletinSnapshotService(db).get_or_generate(
            selection_type=selection_type,
            selection_id=selection_id,
            week_start=_parse_date(week_start),
            week_end=_parse_date(week_end),
            force_refresh=False,
            use_llm=use_llm,
        )
        notification = NotificationService(db).create_weeks_best_generated(user_id, bulletin)
        return {
            "user_id": user_id,
            "selection_type": selection_type,
            "selection_id": selection_id,
            "status": bulletin.get("status"),
            "notification_id": notification.id if notification else None,
        }
    finally:
        db.close()


@app.task
def generate_weekly_bulletins_for_all_users():
    db = SessionLocal()
    try:
        week_start, week_end = default_previous_week()
        preferences = (
            db.query(UserBulletinPreference)
            .filter(
                UserBulletinPreference.notifications_enabled.is_(True),
                UserBulletinPreference.notification_frequency == "weekly",
            )
            .all()
        )
        queued = []
        for preference in preferences:
            if preference.selection_type == "clusters":
                for cluster_id in preference.selected_cluster_ids_json or []:
                    task = generate_weeks_best_for_user.delay(
                        preference.user_id,
                        "cluster",
                        str(cluster_id),
                        week_start.isoformat(),
                        week_end.isoformat(),
                    )
                    queued.append(task.id)
            elif preference.selection_type == "categories":
                for category in preference.selected_categories_json or []:
                    task = generate_weeks_best_for_user.delay(
                        preference.user_id,
                        "category",
                        str(category),
                        week_start.isoformat(),
                        week_end.isoformat(),
                    )
                    queued.append(task.id)
        return {
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat(),
            "queued": len(queued),
            "task_ids": queued,
        }
    finally:
        db.close()


def _parse_date(value: str):
    from datetime import date

    return date.fromisoformat(value)
