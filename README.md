# Scaffold Health

Clinical knowledge platform for orthopedic/MSK rehab clinics (MVP wedge: ACL reconstruction). Event-sourced CQRS backend powering a Therapist Copilot and a Patient Assistant on top of a provenance-tracked Knowledge Profile. Advisory-only — the therapist is always the sole clinical decision-maker.

See [`docs/PRD.md`](docs/PRD.md) for the full product requirements: workflows, architecture, API surface, and the MVP Definition of Done.

## Quick start

```
cp .env.example .env
docker compose up --build
```

- Frontend: http://localhost:5173 (Vite dev server; proxies `/api/*` to the API)
- API: http://localhost:8000 (`GET /health`)
- Postgres: localhost:5433
- Redis: localhost:6380

Run the backend test suite:

```
docker compose exec api python -m pytest
```

## Development workflow

- `main` — stable, production-ready. Updated only at completed milestone/MVP releases.
- `develop` — primary integration branch for ongoing work.
- `feature/*` — one branch per feature or fix, branched from `develop`, merged back with `--no-ff` after validation.

## Status

Milestones 1–7 are complete: repo scaffold and event-sourced store foundation, auth (therapist signup/login, patient invites), patient intake and caseload, document upload with async text extraction, patient check-ins with forward-only phase progression, the React frontend (auth pages, therapist dashboard/intake/patient detail, patient portal), and LLM fact extraction (Gemini-backed, `backend/app/core/llm_client.py`) with the Knowledge Builder merge engine — per-field overwrite/append-only/immutable-once-set strategies, contradiction detection, and provenance surfaced in the therapist UI (`backend/app/profile/`). A 12-note golden evaluation set (`backend/eval/`) scores extraction at recall 1.00 / precision 0.65 / F1 0.79 per field. Remaining for MVP: Copilot prep briefs, the Patient Assistant, and RAG indexes (needed for briefs). See `docs/PRD.md` §12 for the full Definition of Done.
