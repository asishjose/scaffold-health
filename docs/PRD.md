# Scaffold Health — Product Requirements Document

**Version:** 1.0
**Status:** Approved for implementation

---

## 1. Product Summary

Scaffold Health is a clinical knowledge platform for physical therapy and orthopedic rehab clinics. It converts scattered clinical documents, therapist notes, and patient check-ins into a single structured, auditable record of each patient's recovery — the **Patient Knowledge Profile** — and uses that record to power two interfaces: a **Therapist Copilot** (appointment-prep briefs, longitudinal reasoning, contradiction flagging) and a **Patient Assistant** (progress visibility, check-ins, scoped Q&A).

The system is advisory-only: the therapist is always the sole clinical decision-maker. No AI output writes directly to a patient's care plan.

**MVP clinical wedge:** ACL reconstruction rehab (a structured ~9–12 month protocol with clear phase criteria).

**Roadmap ceiling:** orthopedic/MSK rehab only. Phase 2 expands to additional MSK protocols (knee replacement, hip replacement, shoulder, sports rehab, lower back pain). No expansion beyond MSK/orthopedic rehab is planned or in scope at any phase.

---

## 2. Problem Statement

Rehab clinics accumulate paperwork (MRI reports, discharge summaries, referral notes) and check-in data per patient, but this information stays unstructured and scattered across documents. Therapists re-read a patient's full history before every appointment, and there is no structured, provenance-tracked view of what is actually known about a patient's condition and progress. Existing digital MSK products (Hinge Health, Sword Health) focus on exercise tracking and motion capture for high-volume, low-acuity chronic pain — not on structuring the documentation and clinical reasoning burden for structured, surgeon-referred, protocol-driven recovery.

---

## 3. Target Users

| Role | Description | Access |
|---|---|---|
| **Therapist** | Licensed clinician managing a caseload of patients. Signs up directly (gated by a clinic registration code). | Full caseload visibility, full profile detail, Copilot |
| **Patient** | Individual in an active rehab protocol. Account created by their therapist; never self-registers. | Own record only, reduced profile, Patient Assistant |

No admin/superadmin role exists. Single-clinic deployment model for MVP.

---

## 4. Scope

### 4.1 In Scope (MVP)
- Therapist signup/login with registration-code gating
- Patient invite-only account creation, bound to the creating therapist
- Patient intake (structured fields, fixed to ACL injury type)
- Document upload (PDF) with async OCR/LLM extraction into structured profile fields, each with provenance and confidence
- Per-field merge logic with contradiction detection and "needs review" flagging
- On-demand therapist appointment-prep brief (Copilot)
- Patient check-in submission (pain level + note)
- Therapist-only, forward-only phase advancement
- Patient-facing scoped Q&A assistant, restricted to patient-education content, with symptom/urgent questions redirected to the clinic
- Full audit trail via an append-only event log, replayable to rebuild all read models
- Golden evaluation set for extraction accuracy (precision/recall/F1)

### 4.2 Out of Scope (MVP)
- Computer-vision motion tracking / exercise form analysis
- Automated engagement/reminder mechanisms (push notifications, email nudges)
- Real email delivery infrastructure (invite links are copy/share only, no SendGrid/SES)
- Multi-clinic / multi-tenant support
- Calendar or scheduled-appointment entities
- Patient self-registration
- Backward phase regression
- Any clinical domain outside orthopedic/MSK rehab (permanently out of scope, not just deferred)

---

## 5. Core Workflows

### 5.1 Therapist Onboarding
1. Therapist submits name, email, password, and a clinic registration code.
2. Password is hashed (bcrypt/argon2); a JWT access token (~15 min) and refresh token (~7 days) are issued on login.
3. Refresh token silently renews the access token without re-login.

### 5.2 Patient Intake
1. Therapist submits: name, DOB, contact email, injury type (fixed to ACL for MVP), surgery date.
2. A `CreatePatient` command produces an event; the Knowledge Builder sets the initial profile, with `injury` and `surgery_date` marked immutable-once-set.
3. A single-use invite link (expires in 48 hours) is generated in the same step and displayed in the therapist UI for manual sharing.
4. The therapist can create and edit the patient's profile immediately; this is never gated by whether the patient has activated their account.

### 5.3 Patient Account Activation
1. Patient opens the invite link; email is pre-filled and locked.
2. Patient sets a password; account is activated and bound to the inviting therapist via a foreign-key relationship.
3. Patient logs in through the same login endpoint used by therapists; role is distinguished via a `role` claim in the JWT.

### 5.4 Document Ingestion
1. Therapist uploads a PDF (MRI report, discharge summary, or referral note) attached to a patient.
2. An `UploadDocument` command validates file type and ownership, then produces an event.
3. An asynchronous worker (Celery, backed by Redis) performs OCR and LLM-based extraction.
4. The LLM returns candidate facts, each with a confidence score and a source quote/span.
5. Deterministic Python logic (not the LLM) routes each field to its merge strategy and applies it.
6. Provenance (`source_event_id`, `extracted_at`, `confidence`, `extractor_version`) is written on every field.
7. A new profile version is created, referencing the causing event (no in-place mutation).
8. Residual unstructured text (after structured-fact extraction) is chunked and embedded into the per-patient RAG index.
9. The UI shows a "Processing" state per document until extraction completes (poll/refetch, no websockets).
10. Extracted fields, their confidence, and their source are surfaced in the therapist UI.

### 5.5 Therapist Appointment-Prep (Copilot)
1. Therapist clicks "Generate Prep Brief" on a patient's detail page (no calendar/appointment entity exists).
2. The system assembles: full Knowledge Profile, Timeline events since the last generated brief, and relevant clinical-guideline RAG chunks (retrieval scoped by phase/flags).
3. A single structured LLM prompt (no agent orchestration) produces a three-section output: **Since last visit**, **Flags**, **Suggested focus**.
4. The brief renders inline on the patient detail page. It is advisory-only and never writes to the patient's profile or phase.

### 5.6 Patient Check-In
1. Patient submits a pain level (0–10 slider) and an optional free-text note.
2. A `SubmitCheckIn` command produces an event; the value is appended to `pain_history` (append-only merge — no data is ever discarded or overwritten).

### 5.7 Phase Progression
1. `current_phase` uses overwrite/latest-wins merge semantics.
2. Only the therapist can change it, via an explicit `AdvancePhase` command.
3. The UI offers only the single next phase in sequence — no backward regression and no skipping steps; the command handler rejects any invariant violation.
4. An optional note can be attached; the action requires explicit confirmation.
5. The Copilot brief may flag phase-advancement readiness as a suggestion; it never advances the phase itself.

### 5.8 Patient Assistant
1. Patient sees a reduced profile: phase, plan, general progress only — no `active_concerns` and no provenance data.
2. Patient can ask single-turn questions answered against a separate, patient-education-only RAG corpus.
3. Any question that reads as symptom-related or urgent is redirected to the clinic and is never answered with a clinical claim.

---

## 6. System Architecture

### 6.1 Pattern
Event-sourced CQRS. The **event store is the sole source of truth**. The Knowledge Profile, Timeline, and vector indexes are disposable, rebuildable projections derived from the event log — never written to directly.

```
Command → Command Handler (validates) → Event Store (append-only)
                                              │
                          ┌───────────────────┴───────────────────┐
                          ▼                                       ▼
                  Knowledge Builder                      Timeline/RAG Projector
                  (read model)                            (read model)
                          │                                       │
                          └───────────────────┬───────────────────┘
                                               ▼
                                   Query API (read-only, role-split)
                                               │
                                  ┌────────────┴────────────┐
                                  ▼                          ▼
                          Therapist Copilot            Patient Assistant
```

### 6.2 Command Handler Validation (all commands pass through, in order)
1. **Structural** — schema/field validity, ranges, no future timestamps
2. **Authorization** — actor permitted to act on this resource
3. **Domain invariants** — protocol-specific rules (e.g., no skipping phase steps; file type restricted to text/PDF)
4. **Idempotency** — dedupe via client idempotency key
5. **Referential integrity** — referenced IDs (patient, document) must exist

No LLM calls occur inside command handlers; all validation here is deterministic.

### 6.3 Knowledge Builder Merge Strategy (per field)

| Strategy | Fields | Behavior |
|---|---|---|
| Overwrite (latest wins) | `current_phase`, `active_restrictions` | New valid value replaces old |
| Append-only | `pain_history`, `milestones` | Accumulates; nothing discarded |
| Derived/recomputed | `pain_trend`, `exercise_adherence` | Recalculated from history; never directly settable |
| Immutable-once-set | `injury`, `surgery_date` | Conflicting new value triggers arbitration, not silent overwrite |

**Contradiction handling:** conflicting facts are never silently resolved. If confidence/source-reliability comparison doesn't resolve the conflict, both values are written and the patient is flagged `needs_review` with a specific reason (e.g. "Contradiction," "Adherence drop," "No check-in") — never a generic flag.

**Provenance:** required on every field write: `{source_event_id, extracted_at, confidence, extractor_version}`.

**Versioning:** every update creates a new profile version referencing its causing event; no in-place mutation. Enables point-in-time queries and full replay.

### 6.4 RAG Scoping
- Only unstructured prose is embedded (document narrative text, free-text notes, external guideline corpus). Structured fields, Timeline metadata, raw PHI/identifiers, and derived fields are never embedded.
- Extraction always runs first; only residual text after structured-fact extraction is chunked and embedded.
- A schema-allowlist check rejects/logs any chunk that near-exact-matches a known structured field name/value.
- Three separately scoped indexes:
  1. Per-patient document/note residual text — filtered by `patient_id` and `source_type` at the query level
  2. Shared clinical guideline corpus — Copilot-only
  3. Shared patient-education corpus — Patient Assistant-only

### 6.5 Query API
Two structurally separate modules — not one generic endpoint with role-based filtering:

| Dimension | Therapist Copilot | Patient Assistant |
|---|---|---|
| Scope | Full caseload | Single patient, hard-locked to `patient_id = token.sub` |
| Profile fields | Full, incl. `active_concerns`, provenance | Reduced (phase, plan, general progress only) |
| Retrieval corpus | Clinical guidelines + full note history | Patient-education corpus only |
| Output constraints | Direct clinical claims acceptable | No diagnostic claims; symptom questions redirected to clinic |

This split is the structural enforcement of the advisory-only, never-autonomous posture — not a prompt-level convention.

---

## 7. Technical Stack

| Layer | Choice |
|---|---|
| Backend framework | FastAPI |
| Database | PostgreSQL + pgvector |
| Async task queue | Celery + Redis |
| Frontend | React + Vite (SPA) |
| Frontend routing | React Router |
| Frontend server state | TanStack Query |
| Frontend client state | Zustand (auth token/role only) |
| UI components | Tailwind CSS + shadcn/ui |
| Auth | JWT (access + refresh), `role` claim, `OAuth2PasswordBearer` + `python-jose`/`pyjwt` |
| Password hashing | bcrypt or argon2 |
| LLM provider | Google Gemini API (free tier), behind a provider-agnostic `app/core/llm_client.py` exposing `extract_facts(text, schema)` and `generate_brief(context)` |
| Containerization | Docker Compose (single-command run) |

### 7.1 Backend Module Structure (package-by-feature)

```
core/            config, security (hashing, JWT encode/decode, get_current_user), db session
event_store/     append-only Event table + append_event() — the only write entry point
projectors/      knowledge_builder.py, timeline_rag.py, replay.py (Celery tasks)
auth/            signup, login, refresh, invite acceptance
patients/        intake, listing, detail
documents/       upload, listing
checkins/        patient check-in submission
briefs/          Copilot brief generation
query_api/       therapist.py and patient.py — separate modules, separate return types
```

**Enforcement rules (structural, not conventional):**
- Every `commands.py` writes only via `event_store.append_event()` — no direct writes to read models.
- Every router `GET` reads only via `query_api/` — never reads projector internals directly.

### 7.2 API Surface

| Method & Path | Access | Purpose |
|---|---|---|
| `POST /auth/signup` | Public (registration code required) | Therapist account creation |
| `POST /auth/login` | Public | Issue access + refresh tokens |
| `POST /auth/refresh` | Authenticated (refresh token) | Renew access token |
| `GET /auth/invite/{token}` | Public | Validate invite token |
| `POST /auth/invite/{token}` | Public | Patient sets password, activates account |
| `POST /patients` | Therapist | Create patient (intake) |
| `GET /patients` | Therapist | List caseload |
| `GET /patients/{id}` | Therapist or owning patient | Profile detail (response shape differs by role via `query_api`) |
| `POST /patients/{id}/documents` | Therapist | Upload document |
| `GET /patients/{id}/documents` | Therapist | List documents + ingestion status |
| `POST /patients/{id}/checkins` | Patient (own record only) | Submit check-in |
| `POST /patients/{id}/brief` | Therapist | Generate prep brief |
| `POST /patients/{id}/phase` | Therapist | Advance phase (forward-only) |
| `POST /patients/{id}/assistant` | Patient (own record only) | Ask the Patient Assistant a question |

### 7.3 Frontend Routing
- Public: `/login`, `/signup`, `/invite/:token`
- Therapist-protected: `/dashboard`, `/patients/new`, `/patients/:id`
- Patient-protected: `/patient`
- `ProtectedRoute` reads role from the decoded JWT and redirects accordingly.

### 7.4 Frontend Structure

```
shared/ui/       shadcn primitives
shared/api/      JWT-attaching fetch client with refresh interceptor
shared/hooks/    usePatients, usePatient, useUploadDocument, useGenerateBrief,
                 useCheckIn, useAdvancePhase, useAuth
shared/auth/     ProtectedRoute, authStore (Zustand)
pages/           PatientList, IntakeForm,
                 PatientDetail (ProfileSummaryCards, ProvenancePanel,
                                DocumentUpload/List, PrepBriefPanel, PhaseAdvanceControl),
                 PatientPortal (ProfileCard, CheckInForm, AssistantChat)
```

---

## 8. Screens

1. **Therapist patient list** — caseload rows (name, phase, weeks post-op), "Invite pending" indicator, typed "Needs review" badge shown directly in-list (e.g. "Contradiction," "Adherence drop," "No check-in")
2. **Therapist patient detail** — structured fields (adherence shown as raw %), inline-expanding "Generate prep brief," provenance panel with raw confidence scores (e.g. `conf 0.94`) and visually flagged conflicting fields, document list with ingestion status
3. **Patient view** — reduced profile, check-in form (pain slider + note), single-turn assistant chat
4. **Therapist signup/login** — name, email, password, registration code (signup); email/password (login)
5. **Patient invite/set-password** — branded confirmation page, email pre-filled and locked, 48-hour link expiry
6. **Add-patient intake form** — name, DOB, contact email, injury type (fixed to ACL), surgery date; single submit creates the patient and generates the invite
7. **Document upload** — drag-and-drop area, per-file "Processing…" status
8. **Expanded prep brief** — inline, three sections: Since last visit / Flags / Suggested focus
9. **Phase advancement** — forward-only dropdown (next phase only), optional note, explicit confirm action
10. **Invite delivery** — link displayed in the therapist UI for manual copy/share; no email-sending infrastructure

---

## 9. AI/LLM Requirements

- All LLM calls are routed through `llm_client.py`; Gemini is the only implementation for MVP, but extraction/merge/prompt logic must not depend on any Gemini-specific behavior beyond the `extract_facts`/`generate_brief` interface.
- **Extraction:** one LLM call per document, tool-use/schema-constrained output, one call returns candidate facts for a defined field group, each with a confidence score and source quote/span.
- **Merge routing is deterministic:** the LLM never decides how a conflict is resolved or which merge strategy applies — that mapping is fixed Python logic keyed by field name.
- **Copilot prompt:** single structured prompt, no multi-step agent orchestration, tool-use-constrained to the three-section output format, advisory framing enforced in the prompt text itself.
- **Evaluation:** a golden set of 10–15 hand-crafted synthetic clinical notes with expected extracted facts, built during initial extraction implementation (not after). Extraction is scored with precision/recall/F1 per field against this set. The `needs_review` contradiction path serves as the human-in-the-loop review proxy (no live clinician reviewer in this project).

---

## 10. Security & Compliance Posture

- Passwords hashed with bcrypt or argon2; never stored or logged in plaintext.
- JWT access tokens short-lived (~15 min); refresh tokens longer-lived (~7 days).
- RBAC is enforced structurally at the query level (filtered by `therapist_id`/`patient_id` in the query itself), not by post-filtering results after a broader fetch.
- MVP operates on synthetic patient data only — no real PHI. Production-only requirements (BAA-covered LLM hosting, hybrid on-prem/cloud routing for PHI-touching calls, at-rest/in-transit encryption posture, full HIPAA-style audit logging) are documented as future production requirements and are **not** implemented for MVP.

---

## 11. Roadmap

| Phase | Scope |
|---|---|
| **Phase 1 (MVP)** | ACL reconstruction rehab: event architecture, Knowledge Builder, Timeline, Patient Assistant, Therapist Copilot, RAG, evaluation loop |
| **Phase 2** | Additional orthopedic/MSK protocols: knee replacement, hip replacement, shoulder, sports rehab, lower back pain. Same architecture; new protocol configs (field schemas, phase definitions, eval sets, RAG corpora) per injury type |
| **Phase 3** | Permanently out of scope. No expansion beyond orthopedic/MSK rehab is planned |

---

## 12. Definition of Done (MVP)

Using a single seeded synthetic ACL patient journey (pre-op → 9 months post-op):

1. A therapist can sign up (with a valid registration code) and log in.
2. A therapist can create a patient record and obtain a shareable invite link in the same action.
3. A patient can activate their account via the invite link and log in.
4. A therapist can upload a PDF document and observe it transition from "Processing" to extracted, with populated fields, confidence scores, and source attribution visible.
5. A patient with an unresolved field contradiction shows a typed "Needs review" badge in both the caseload list and the patient detail view.
6. A therapist can generate a Prep Brief on demand and see all three sections (Since last visit / Flags / Suggested focus) populated from real profile, timeline, and RAG context — not placeholder text.
7. A therapist can advance a patient's phase forward one step; an out-of-sequence advancement attempt is rejected by the command handler.
8. A patient can submit a check-in (pain level + note) and see it reflected in `pain_history` server-side.
9. A patient can ask the assistant a general question and receive a scoped answer; a symptom/urgent-sounding question is redirected to the clinic instead of answered clinically.
10. The event log can be fully replayed to rebuild an identical Knowledge Profile from scratch.
11. The golden evaluation set (10–15 notes) has been run against the extraction pipeline, with precision/recall/F1 reported per field.
12. The entire stack (API, worker, database, frontend) starts with a single `docker compose up`.
