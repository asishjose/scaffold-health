# Scaffold Health

Clinical knowledge platform for orthopedic/MSK rehab clinics (MVP wedge: ACL reconstruction). Event-sourced CQRS backend powering a Therapist Copilot and a Patient Assistant on top of a provenance-tracked Knowledge Profile. Advisory-only — the therapist is always the sole clinical decision-maker.

See [`docs/PRD.md`](docs/PRD.md) for the full product requirements: workflows, architecture, API surface, and the MVP Definition of Done.

## Quick start

```
cp .env.example .env
docker compose up --build
```

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

Milestone 1 (repo scaffold, Docker Compose stack, event-sourced store foundation) is complete. See `docs/PRD.md` §12 for the full Definition of Done this build is working toward.
