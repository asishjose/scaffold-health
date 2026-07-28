"""Seeds the two shared RAG corpora (clinical guidelines, patient
education) from the synthetic text files in app/rag/seed_data/. Run via
`python -m app.rag.seed_corpus` inside the api/worker container. Idempotent
per file — safe to re-run (see commands.seed_shared_corpus).

Deliberately lives under app/rag/, not a top-level scripts/ directory: only
./backend is volume-mounted into the api/worker containers, so a top-level
scripts/ directory would not be reachable via `docker exec`.
"""

from pathlib import Path

from app.core.db import SessionLocal

# Standalone entrypoint (run via `python -m`, not through the api/worker
# processes that already import every models module at startup) — needs
# the same full-registration list as alembic/env.py and core/celery_app.py
# so every FK target table is on Base.metadata before the first flush.
from app.auth import models as auth_models  # noqa: F401
from app.checkins import models as checkins_models  # noqa: F401
from app.documents import models as documents_models  # noqa: F401
from app.event_store import models as event_store_models  # noqa: F401
from app.patients import models as patients_models  # noqa: F401
from app.profile import models as profile_models  # noqa: F401
from app.rag import commands
from app.rag.events import (
    SCOPE_CLINICAL_GUIDELINES,
    SCOPE_PATIENT_EDUCATION,
    SOURCE_TYPE_EDUCATION_SEED,
    SOURCE_TYPE_GUIDELINE_SEED,
)

SEED_DATA_DIR = Path(__file__).parent / "seed_data"

CORPORA = [
    (SEED_DATA_DIR / "clinical_guidelines", SCOPE_CLINICAL_GUIDELINES, SOURCE_TYPE_GUIDELINE_SEED),
    (SEED_DATA_DIR / "patient_education", SCOPE_PATIENT_EDUCATION, SOURCE_TYPE_EDUCATION_SEED),
]


def seed_all() -> None:
    db = SessionLocal()
    try:
        for directory, scope, source_type in CORPORA:
            for path in sorted(directory.glob("*.txt")):
                text = path.read_text()
                rows = commands.seed_shared_corpus(
                    db, scope=scope, source_type=source_type, label=path.name, text=text
                )
                print(f"{scope}/{path.name}: {len(rows)} chunks")
    finally:
        db.close()


if __name__ == "__main__":
    seed_all()
