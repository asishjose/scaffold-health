from celery import Celery

from app.core.config import settings

celery_app = Celery("scaffold_health", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.task_default_queue = "scaffold_health"
