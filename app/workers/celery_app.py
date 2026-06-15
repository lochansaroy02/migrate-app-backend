from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "databridge",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.workers.migration_tasks"],
)

celery_app.conf.update(
    task_serializer=settings.CELERY_TASK_SERIALIZER,
    result_serializer=settings.CELERY_RESULT_SERIALIZER,
    accept_content=settings.CELERY_ACCEPT_CONTENT,
    task_track_started=settings.CELERY_TASK_TRACK_STARTED,
    task_time_limit=settings.CELERY_TASK_TIME_LIMIT,
    task_soft_time_limit=settings.CELERY_TASK_SOFT_TIME_LIMIT,
    worker_prefetch_multiplier=1,        # one task at a time per worker slot
    task_acks_late=True,                 # only ack after completion → no lost tasks on crash
    task_reject_on_worker_lost=True,
    result_expires=86400,                # keep results 24 h
    broker_connection_retry_on_startup=True,
)
