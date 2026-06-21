import sys
from pathlib import Path

from celery import Celery
from celery.schedules import crontab

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.core.config import settings

app = Celery(
    "tasks",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

app.conf.timezone = "Europe/Istanbul"
app.conf.beat_schedule = {
    "dispatch-pending-notification-deliveries": {
        "task": "backend.worker.tasks.dispatch_pending_notification_deliveries",
        "schedule": 60.0,
    },
    "generate-weekly-bulletins-for-all-users": {
        "task": "backend.worker.tasks.generate_weekly_bulletins_for_all_users",
        "schedule": crontab(minute=0, hour=9, day_of_week="monday"),
    },
}

import backend.worker.tasks  # noqa: E402,F401
