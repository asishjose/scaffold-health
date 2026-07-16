from celery import Celery

from app.core.config import settings

celery_app = Celery("scaffold_health", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.task_default_queue = "scaffold_health"

# Import every models module so its tables register on Base.metadata before
# any task runs a query — a task module may only import the model it works
# with directly, but FK string references (e.g. ForeignKey("therapists.id"))
# need every referenced table registered in this process too. Add new
# modules here as they're introduced (mirrors alembic/env.py).
from app.auth import models as auth_models  # noqa: E402,F401
from app.checkins import models as checkins_models  # noqa: E402,F401
from app.documents import models as documents_models  # noqa: E402,F401
from app.event_store import models as event_store_models  # noqa: E402,F401
from app.patients import models as patients_models  # noqa: E402,F401

# Imported after celery_app is defined, since each tasks module does
# `from app.core.celery_app import celery_app` to register its tasks.
from app.documents import tasks  # noqa: E402,F401
