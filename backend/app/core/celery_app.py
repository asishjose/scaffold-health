import ssl

from celery import Celery
from celery.signals import setup_logging as celery_setup_logging_signal

from app.core.config import settings
from app.core.logging_config import configure_logging

celery_app = Celery("scaffold_health", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.task_default_queue = "scaffold_health"

# Celery's redis broker/backend (unlike redis-py's own client) refuses to
# initialize over rediss:// unless ssl_cert_reqs is set explicitly — it
# won't infer a default the way redis-py does. Upstash (production) uses
# rediss://; local docker-compose Redis uses plain redis://, so this is a
# no-op there.
if settings.redis_url.startswith("rediss://"):
    _redis_ssl_opts = {"ssl_cert_reqs": ssl.CERT_REQUIRED}
    celery_app.conf.broker_use_ssl = _redis_ssl_opts
    celery_app.conf.redis_backend_use_ssl = _redis_ssl_opts


# Connecting any receiver to this signal tells Celery to skip its own
# logging setup entirely, so the worker emits the same structured JSON
# lines as the API process instead of Celery's default text format.
@celery_setup_logging_signal.connect
def _configure_worker_logging(**kwargs) -> None:
    configure_logging()

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
from app.profile import models as profile_models  # noqa: E402,F401
from app.rag import models as rag_models  # noqa: E402,F401

# Imported after celery_app is defined, since each tasks module does
# `from app.core.celery_app import celery_app` to register its tasks.
from app.documents import tasks  # noqa: E402,F401
