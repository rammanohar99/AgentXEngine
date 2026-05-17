"""
Celery application — async task queue for background work.

Phase 1: wired and importable, no tasks registered yet.
Phase 4: RAG ingestion, memory summarization, and agent workflows
         will register tasks here.

The worker is started via:
    celery -A app.workers.celery_app worker --loglevel=info
"""

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "aiengos",
    broker=settings.redis_url_str,
    backend=settings.redis_url_str,
    include=[
        "app.workers.tasks.ingestion",
        "app.workers.tasks.memory",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,          # Re-queue on worker crash
    worker_prefetch_multiplier=1, # Fair dispatch — one task at a time per worker
    result_expires=3600,          # Results expire after 1 hour
)
