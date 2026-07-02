import os
from celery import Celery
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
)

if __name__ == "__main__":
    celery_app.start()
