"""Golden-set evaluation for RAG retrieval quality across all three scopes
(clinical_guidelines, patient_education, patient_notes). Runs real Gemini
embedding calls against golden_retrieval_queries.json and scores results
from the existing retrieve_*_chunks functions.

Prerequisite: the two shared corpora must already be seeded —
    python -m app.rag.seed_corpus

Usage (from backend/, with GEMINI_API_KEY set):
    python -m eval.run_retrieval_eval
"""

import json
import math
import time
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.llm_client import LLMExtractionError, embed_text

# Standalone entrypoint (run via `python -m`, not through the api/worker
# processes that already import every models module at startup) — needs
# the same full-registration list as alembic/env.py / app/rag/seed_corpus.py
# so every FK target table is on Base.metadata before the first flush.
from app.auth import commands as auth_commands
from app.auth import models as auth_models
from app.checkins import models as checkins_models  # noqa: F401
from app.documents import commands as document_commands
from app.documents import models as documents_models  # noqa: F401
from app.documents import tasks as document_tasks
from app.event_store import models as event_store_models  # noqa: F401
from app.patients import commands as patient_commands
from app.patients import models as patients_models  # noqa: F401
from app.patients.models import Patient
from app.profile import models as profile_models  # noqa: F401
from app.query_api import patient as patient_query_api
from app.query_api import therapist as therapist_query_api
from app.rag import commands as rag_commands
from app.rag import models as rag_models  # noqa: F401
from app.rag.events import (
    SCOPE_CLINICAL_GUIDELINES,
    SCOPE_PATIENT_EDUCATION,
    SCOPE_PATIENT_NOTES,
)

EVAL_DIR = Path(__file__).parent
QUERIES_PATH = EVAL_DIR / "golden_retrieval_queries.json"
RESULTS_PATH = EVAL_DIR / "retrieval_results.json"
PATIENT_JOURNEY_DIR = EVAL_DIR / "patient_journey_fixture"

MAX_ATTEMPTS = 4
RETRY_BACKOFF_SECONDS = 15

# Advisory only (see score_query / negative-query reporting below).
# Calibrated from the first real run's negative-query top1_similarity
# values (0.51-0.65, mean 0.57) — note those overlap the low end of real
# positive-hit similarities (e.g. 0.618 for pe-hep-consistency), so this is
# not a clean separator and must never be treated as pass/fail; it only
# flags negative queries worth a second look.
NEGATIVE_SIMILARITY_ADVISORY_THRESHOLD = 0.57

EVAL_THERAPIST_EMAIL = "retrieval-eval-therapist@scaffold.test"
# v2: several fixture documents literally contain "2026-04-01" as their
# surgery/admission date. An eval patient whose own surgery_date matches
# that string collides with app/rag/allowlist.py's substring leakage
# check (any known value >=6 chars found verbatim in a chunk rejects that
# whole chunk), silently dropping the sentences that mention it — which
# happen to also carry the graft-type and referral-reason content — from
# the index. Use a surgery_date that doesn't appear anywhere in the
# fixture text so indexing isn't confounded by the (correctly-functioning)
# leakage guard.
EVAL_PATIENT_EMAIL = "retrieval-eval-patient-v2@scaffold.test"

PATIENT_JOURNEY_STEMS = [
    "01_mri_report",
    "02_operative_report",
    "03_discharge_summary",
    "04_referral_note",
    "05_pt_progress_week2",
    "06_pt_progress_week4",
    "07_pt_progress_week8",
    "08_pt_progress_week12",
    "09_pt_progress_week16",
]


def _embed_query_with_retry(query: str) -> tuple[list[float], float]:
    """Returns (embedding, latency_seconds) where latency times only the
    final successful call, mirroring run_eval.py's _extract_facts_with_retry.
    """
    for attempt in range(1, MAX_ATTEMPTS + 1):
        start = time.perf_counter()
        try:
            embedding = embed_text(query, task_type="RETRIEVAL_QUERY")
            return embedding, time.perf_counter() - start
        except LLMExtractionError as exc:
            if attempt == MAX_ATTEMPTS:
                raise
            print(f"  attempt {attempt} failed ({exc}); retrying in {RETRY_BACKOFF_SECONDS}s")
            time.sleep(RETRY_BACKOFF_SECONDS)
    raise AssertionError("unreachable")


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = (len(ordered) - 1) * pct
    lo, hi = math.floor(k), math.ceil(k)
    if lo == hi:
        return ordered[int(k)]
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


def _matches(text: str, keywords: list[str]) -> bool:
    lowered = text.lower()
    return any(keyword.lower() in lowered for keyword in keywords)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0


def ensure_patient_journey_indexed(db: Session) -> Patient:
    """Reuses a fixed eval patient across runs (looked up by a marker
    contact_email) so re-running the eval doesn't re-call the embedding API
    for indexing — only the query embeddings should cost anything on repeat
    runs.
    """
    existing = db.execute(
        select(Patient).where(Patient.contact_email == EVAL_PATIENT_EMAIL)
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    therapist = db.execute(
        select(auth_models.Therapist).where(auth_models.Therapist.email == EVAL_THERAPIST_EMAIL)
    ).scalar_one_or_none()
    if therapist is None:
        therapist = auth_commands.register_therapist(
            db,
            name="Retrieval Eval Therapist",
            email=EVAL_THERAPIST_EMAIL,
            password="a-strong-eval-password",
            registration_code=settings.clinic_registration_code,
        )

    patient = patient_commands.create_patient(
        db,
        therapist_id=therapist.id,
        name="Retrieval Eval Patient",
        date_of_birth=date(1998, 1, 1),
        contact_email=EVAL_PATIENT_EMAIL,
        surgery_date=date(2025, 11, 3),
    )

    # upload_document() also dispatches process_document via Celery .delay()
    # to the real worker container (same broker the eval script's host
    # process talks to) — suppress that so our own, synchronous call to
    # index_document_residual_text below is the only thing that indexes
    # these documents. Otherwise the live worker would independently OCR
    # each PDF, run real fact extraction, and index its own (possibly
    # different) residual text, racing our call and double-indexing.
    # Same pattern as tests/documents/test_tasks.py's
    # test_process_document_still_extracted_when_rag_indexing_fails.
    document_tasks.process_document.delay = lambda *args, **kwargs: None

    for stem in PATIENT_JOURNEY_STEMS:
        pdf_bytes = (PATIENT_JOURNEY_DIR / f"{stem}.pdf").read_bytes()
        text = (PATIENT_JOURNEY_DIR / f"{stem}.txt").read_text()
        document = document_commands.upload_document(
            db,
            patient_id=patient.id,
            therapist_id=therapist.id,
            filename=f"{stem}.pdf",
            content_type="application/pdf",
            file_bytes=pdf_bytes,
        )
        rows = rag_commands.index_document_residual_text(
            db, patient=patient, document=document, text=text
        )
        print(f"  indexed patient_notes/{stem}.pdf ({len(rows)} chunks)")

    return patient


def score_query(query: dict, results: list, query_embedding: list[float]) -> dict:
    expected_labels = set(query.get("expected_labels", []))
    ranked_labels = [r.source_label for r in results]
    hit_rank = (
        next((i + 1 for i, label in enumerate(ranked_labels) if label in expected_labels), None)
        if expected_labels
        else None
    )

    keyword_valid = None
    if hit_rank is not None and query.get("expected_keywords"):
        keyword_valid = _matches(results[hit_rank - 1].chunk_text, query["expected_keywords"])

    top1_similarity = (
        _cosine_similarity(query_embedding, results[0].embedding) if results else None
    )

    return {
        "hit_rank": hit_rank,
        "hit@1": hit_rank is not None and hit_rank <= 1,
        "hit@3": hit_rank is not None and hit_rank <= 3,
        "hit@8": hit_rank is not None and hit_rank <= 8,
        "reciprocal_rank": (1 / hit_rank) if hit_rank else 0.0,
        "keyword_valid": keyword_valid,
        "top1_similarity": top1_similarity,
        "top_labels": ranked_labels,
        "is_negative": not expected_labels,
    }


def _retrieve(db: Session, scope: str, embedding: list[float], eval_patient: Patient) -> list:
    if scope == SCOPE_CLINICAL_GUIDELINES:
        return therapist_query_api.retrieve_clinical_guideline_chunks(db, query_embedding=embedding)
    if scope == SCOPE_PATIENT_EDUCATION:
        return patient_query_api.retrieve_patient_education_chunks(db, query_embedding=embedding)
    if scope == SCOPE_PATIENT_NOTES:
        return therapist_query_api.retrieve_patient_notes_chunks(
            db,
            therapist_id=eval_patient.therapist_id,
            patient_id=eval_patient.id,
            query_embedding=embedding,
        )
    raise ValueError(f"unknown scope {scope!r}")


def main() -> None:
    db = SessionLocal()
    try:
        queries = json.loads(QUERIES_PATH.read_text())

        eval_patient = None
        if any(q["scope"] == SCOPE_PATIENT_NOTES for q in queries):
            eval_patient = ensure_patient_journey_indexed(db)

        per_query_reports = []
        skipped: list[str] = []
        latencies: list[float] = []

        for query in queries:
            try:
                embedding, embed_latency = _embed_query_with_retry(query["query"])
            except LLMExtractionError as exc:
                print(f"skipping {query['id']}: {exc}")
                skipped.append(query["id"])
                continue

            start = time.perf_counter()
            results = _retrieve(db, query["scope"], embedding, eval_patient)
            db_latency = time.perf_counter() - start

            scored = score_query(query, results, embedding)
            total_latency = embed_latency + db_latency
            latencies.append(total_latency)

            per_query_reports.append(
                {
                    "id": query["id"],
                    "scope": query["scope"],
                    "query": query["query"],
                    **scored,
                    "embed_latency_seconds": embed_latency,
                    "db_latency_seconds": db_latency,
                }
            )
            sim = scored["top1_similarity"]
            sim_str = f"{sim:.3f}" if sim is not None else "n/a"
            print(
                f"scored {query['id']} ({query['scope']}): "
                f"hit_rank={scored['hit_rank']} top1_sim={sim_str}"
            )

        if skipped:
            print(f"\n{len(skipped)} quer(y/ies) skipped after repeated failures: {skipped}")

        query_success_rate = (len(queries) - len(skipped)) / len(queries) if queries else 0.0
        latency_p95 = _percentile(latencies, 0.95)
        latency_mean = sum(latencies) / len(latencies) if latencies else 0.0

        positive = [r for r in per_query_reports if not r["is_negative"]]
        negative = [r for r in per_query_reports if r["is_negative"]]

        per_scope: dict[str, dict] = {}
        for scope in (SCOPE_CLINICAL_GUIDELINES, SCOPE_PATIENT_EDUCATION, SCOPE_PATIENT_NOTES):
            rows = [r for r in positive if r["scope"] == scope]
            if not rows:
                continue
            keyword_checked = [r for r in rows if r["keyword_valid"] is not None]
            per_scope[scope] = {
                "n": len(rows),
                "hit@1": sum(r["hit@1"] for r in rows) / len(rows),
                "hit@3": sum(r["hit@3"] for r in rows) / len(rows),
                "hit@8": sum(r["hit@8"] for r in rows) / len(rows),
                "mrr": sum(r["reciprocal_rank"] for r in rows) / len(rows),
                "keyword_validity_rate": (
                    sum(r["keyword_valid"] for r in keyword_checked) / len(keyword_checked)
                    if keyword_checked
                    else None
                ),
            }

        overall = {
            "n": len(positive),
            "hit@1": sum(r["hit@1"] for r in positive) / len(positive) if positive else 0.0,
            "hit@3": sum(r["hit@3"] for r in positive) / len(positive) if positive else 0.0,
            "hit@8": sum(r["hit@8"] for r in positive) / len(positive) if positive else 0.0,
            "mrr": sum(r["reciprocal_rank"] for r in positive) / len(positive) if positive else 0.0,
        }
        keyword_checked_all = [r for r in positive if r["keyword_valid"] is not None]
        overall["keyword_validity_rate"] = (
            sum(r["keyword_valid"] for r in keyword_checked_all) / len(keyword_checked_all)
            if keyword_checked_all
            else None
        )

        negative_sims = [r["top1_similarity"] for r in negative if r["top1_similarity"] is not None]
        negative_summary = {
            "n": len(negative),
            "mean_top1_similarity": sum(negative_sims) / len(negative_sims) if negative_sims else None,
            "over_advisory_threshold": sum(
                1 for s in negative_sims if s > NEGATIVE_SIMILARITY_ADVISORY_THRESHOLD
            ),
        }

        print()
        print(f"{'scope':<22}{'n':>4}{'hit@1':>8}{'hit@3':>8}{'hit@8':>8}{'mrr':>8}{'kw_valid':>10}")
        for scope, stats in per_scope.items():
            kw = stats["keyword_validity_rate"]
            kw_str = f"{kw:.2f}" if kw is not None else "n/a"
            print(
                f"{scope:<22}{stats['n']:>4}{stats['hit@1']:>8.2f}{stats['hit@3']:>8.2f}"
                f"{stats['hit@8']:>8.2f}{stats['mrr']:>8.2f}{kw_str:>10}"
            )
        overall_kw = overall["keyword_validity_rate"]
        overall_kw_str = f"{overall_kw:.2f}" if overall_kw is not None else "n/a"
        print(
            f"{'OVERALL':<22}{overall['n']:>4}{overall['hit@1']:>8.2f}{overall['hit@3']:>8.2f}"
            f"{overall['hit@8']:>8.2f}{overall['mrr']:>8.2f}{overall_kw_str:>10}"
        )

        print()
        mean_sim = negative_summary["mean_top1_similarity"]
        mean_sim_str = f"{mean_sim:.3f}" if mean_sim is not None else "n/a"
        print(
            f"negative queries: {negative_summary['n']}, mean top1_similarity {mean_sim_str}, "
            f"{negative_summary['over_advisory_threshold']} over advisory threshold "
            f"({NEGATIVE_SIMILARITY_ADVISORY_THRESHOLD})"
        )
        print(f"query success rate: {query_success_rate:.2%}")
        print(f"latency: mean {latency_mean:.2f}s, p95 {latency_p95:.2f}s")

        RESULTS_PATH.write_text(
            json.dumps(
                {
                    "per_scope": per_scope,
                    "overall": overall,
                    "negative_queries": negative_summary,
                    "queries": per_query_reports,
                    "skipped_queries": skipped,
                    "query_success_rate": query_success_rate,
                    "latency_seconds": {
                        "mean": latency_mean,
                        "p95": latency_p95,
                        "values": latencies,
                    },
                },
                indent=2,
            )
        )
        print(f"\nFull results written to {RESULTS_PATH}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
