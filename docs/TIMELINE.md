# Scaffold Health — Project Timeline

**Status as of 2026-07-25:** Weeks 1–3 complete. Week 4 starting now.

> Week dates below are approximate (back-calculated from today as the start of Week 4) — adjust if your actual start date differs.

---

## Week 1 — Project Planning (Jul 4–10) ✅ Done

- Defined product scope: Patient Knowledge Profile, Therapist Copilot, Patient Assistant, ACL-reconstruction MVP wedge
- Authored the Product Requirements Document ([docs/PRD.md](PRD.md)) — problem statement, target users, in/out of scope, Definition of Done
- Designed the core architecture: event-sourced CQRS, append-only event log, Knowledge Builder, Timeline/RAG projector
- Broke the build down into milestones M1–M9 and sequenced them

## Week 2 — Supporting Docs & Project Skeleton (Jul 11–17) ✅ Done

- Repository initialized (README, `.gitignore`, PRD committed)
- Docker Compose stack, FastAPI app, and package layout scaffolded
- **M1** — Append-only event store implemented with DB-level enforcement, plus full test suite
- **M2** — Therapist authentication: signup (registration-code gated), login, token refresh

## Week 3 — Core Platform Build (Jul 18–24) ✅ Done

- **M3** — Patient intake, invite-link creation, role-split query API (therapist vs. patient views)
- **M4** — Document upload (PDF) with async OCR/LLM text extraction and status tracking
- **M5** — Patient check-ins (pain level + note) and therapist-only forward-only phase progression
- **M6** — React frontend: auth flows, therapist caseload dashboard, patient portal
- **M7** — LLM fact extraction (Gemini-backed) with per-field provenance, merge logic, contradiction detection, and "needs review" flagging; Knowledge Builder; golden evaluation set (12 notes, precision/recall/F1 reporting)

At this point, 10 of the 12 MVP Definition-of-Done items ([docs/PRD.md §12](PRD.md#12-definition-of-done-mvp)) are complete: therapist signup/login, patient creation + invite, patient activation, document extraction with provenance, contradiction badges, forward-only phase advancement, patient check-ins, full event replay, the golden evaluation run, and `docker compose up` for the whole stack.

## Week 4 — Timeline, RAG & AI-Assisted Interfaces (Jul 25–31) 🔜 Upcoming

Covers the two remaining Definition-of-Done items (#6 and #9), plus the Patient Timeline feature:

- **Patient Timeline**: a Timeline projector/read-model (event-sourced from the existing event store, matching the architecture already named in [PRD §6](PRD.md#6-system-architecture)) surfacing curated clinical milestones — phase advances, extracted `milestones` facts, document-extraction completions — in chronological order per patient; new query endpoint; `PatientTimeline` panel added to both the therapist dashboard (`PatientDetail`) and the patient portal
- **RAG indexing pipeline**: chunk and embed residual unstructured text (document narrative, free-text notes, guideline corpus) into a per-patient RAG index per [PRD §6.4](PRD.md#64-rag-scoping) — only unstructured prose is embedded; a schema-allowlist check rejects any chunk that near-matches a known structured field
- **M8 — Prep Briefs**: `POST /patients/{id}/brief` endpoint assembling Knowledge Profile + Timeline events since the last brief + relevant RAG context into three sections (Since last visit / Flags / Suggested focus); `PrepBriefPanel` wired into the therapist dashboard
- **M9 — Patient Assistant**: `POST /patients/{id}/assistant` endpoint for scoped single-turn Q&A against a patient-education-only RAG corpus, with symptom/urgent-sounding questions redirected to the clinic instead of answered; `AssistantChat` wired into the patient portal

## Week 5 — Agentic Therapist Copilot & Wrap-up (Aug 1–7) 🔜 Upcoming

The PRD scopes the MVP Copilot as a single structured LLM prompt with no agent orchestration ([PRD §5.5](PRD.md#55-therapist-appointment-prep-copilot)). Week 5 deliberately extends past that MVP design into agentic tool-use, on top of the Week 4 Prep Brief:

- **Multi-step case review**: the agent iteratively queries the Knowledge Profile, Timeline, and RAG context itself while drafting the brief, rather than working from one pre-assembled prompt
- **Follow-up Q&A on a brief**: the therapist can ask a clarifying question about a generated brief, and the agent re-queries the relevant data to answer instead of the brief being a dead end
- **Stretch (time-permitting)**: caseload-wide triage (proactively surfacing patients needing review across the full caseload) and dedicated trend/adherence tools (e.g. pain-trend or check-in-cadence computation)
- **Guardrail** (carried over from the existing Copilot): advisory-only — the agent never writes to a patient's care plan or profile directly

Plus wrap-up items carried from the original plan:
- End-to-end verification against all 12 Definition-of-Done items
- Testing and evaluation pass (including RAG/brief/assistant/agentic-copilot quality)
- Documentation cleanup and final demo preparation

---

## Summary

| Week | Dates | Focus | Status |
|---|---|---|---|
| 1 | Jul 4–10 | Project planning, PRD, architecture design | ✅ Done |
| 2 | Jul 11–17 | Supporting docs, project skeleton, event store (M1), auth (M2) | ✅ Done |
| 3 | Jul 18–24 | Patients (M3), documents (M4), check-ins/phases (M5), frontend (M6), extraction (M7) | ✅ Done |
| 4 | Jul 25–31 | Patient Timeline, RAG index, Prep Briefs (M8), Patient Assistant (M9) | 🔜 Upcoming |
| 5 | Aug 1–7 | Agentic Therapist Copilot (multi-step review, follow-up Q&A), DoD wrap-up | 🔜 Upcoming |
