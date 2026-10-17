from celery import Celery
from app.core.config import settings
celery = Celery("eavie", broker=settings.REDIS_URL, backend=settings.REDIS_URL, include=["app.workers.tasks"])
celery.conf.update(task_default_queue="default", task_track_started=True, worker_prefetch_multiplier=1, result_expires=3600, task_time_limit=900)
