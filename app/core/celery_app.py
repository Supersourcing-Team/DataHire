import os
from celery import Celery
from celery.schedules import crontab
from app.core.config import settings

# Determine the broker/backend URL, fallback to localhost redis if not provided
redis_url = settings.REDIS_URL or "redis://localhost:6379"

# Create Celery instance
celery_app = Celery(
    "datahire",
    broker=redis_url,
    backend=redis_url,
    include=[
        "app.tasks.auto_apply",
        "app.tasks.notifications"
    ]
)

# Optional configuration settings
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour max execution time per task
    beat_schedule={
        # Dispatch auto-apply daily at midnight UTC.
        "dispatch-auto-apply-every-day": {
            "task": "app.tasks.auto_apply.dispatch_auto_apply_all_task",
            "schedule": crontab(hour=0, minute=0),
        },
        # Run daily system notifications job at 1:00 AM UTC
        "run-daily-notifications-every-day": {
            "task": "app.tasks.notifications.run_daily_notifications_job",
            "schedule": crontab(hour=1, minute=0),
        }
    }
)

if __name__ == "__main__":
    celery_app.start()
