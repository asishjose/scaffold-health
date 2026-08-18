# Scaffold Health — Final Project Report

---

## 1. Title & Overview

**Project Title:** Scaffold Health — An Event-Sourced Clinical Knowledge Platform for Orthopedic Rehab Clinics

Scaffold Health is a clinical knowledge platform for physical therapy and orthopedic rehab clinics. It converts scattered clinical documents, therapist notes, and patient check-ins into a single structured, auditable record of each patient's recovery — the **Patient Knowledge Profile** — and uses that record to power two purpose-built interfaces: a **Therapist Copilot** for appointment-prep and longitudinal reasoning, and a **Patient Assistant** for progress visibility and scoped Q&A. The system is advisory-only by design: the therapist remains the sole clinical decision-maker, and no AI output writes directly to a patient's care plan.

The project is scoped to a single clinical wedge — ACL reconstruction rehab, a structured ~9–12 month protocol with well-defined phase criteria — chosen to prove out the architecture on one high-signal use case before generalizing to other orthopedic/MSK protocols.

Built over a five-week development cycle, the project spans an event-sourced CQRS backend, an LLM-driven document extraction and retrieval pipeline, a role-split React frontend for therapists and patients, and a live, zero-cost production deployment on Azure.

---

## 2. Executive Summary

This project set out to build a full, working clinical software system end to end — not a toy demo — as a way to gain hands-on depth in a few areas at once: event-sourced system design, retrieval-augmented generation with LLMs, structured data extraction from unstructured documents, and shipping a real full-stack application to a live cloud deployment.

The result is a working platform where a therapist can onboard, add a patient, upload a clinical document and watch it get parsed into structured fields with confidence scores and source attribution, generate an AI-assisted prep brief before a visit, and advance a patient through their recovery phases — while the patient has their own portal to check in, track progress, and ask scoped questions to an assistant grounded in a patient-education knowledge base.

Highlights:
- An event-sourced CQRS architecture where every state change is captured as an immutable event, and all read models (patient profile, timeline, RAG indexes) are rebuildable projections — the system was verified to fully replay its event log into an identical state.
- An LLM extraction pipeline that turns uploaded PDFs into structured, provenanced facts, with deterministic (non-LLM) merge and contradiction-detection logic, backed by a golden evaluation set for measuring extraction accuracy.
- Three separately scoped retrieval-augmented generation indexes (per-patient notes, clinical guidelines, patient education) powering two distinct AI features: a therapist-facing prep-brief generator and copilot chat, and a patient-facing scoped Q&A assistant with a deterministic safety gate for symptom/urgent questions.
- A React frontend with role-specific layouts for therapists and patients, built on top of a clean role-split query API.
- A complete production deployment on Azure's free tier, running at $0/month, using a hybrid architecture split across Container Apps and a VM to work around free-tier limitations.

---

## 3. Introduction

### 3.1 Problem Statement

Rehab clinics accumulate paperwork for every patient — MRI reports, discharge summaries, referral notes — alongside ongoing check-in data, but this information stays unstructured and scattered across documents. A therapist has to re-read a patient's full history before every appointment, and there is no structured, provenance-tracked view of what is actually known about a patient's condition and progress at any given point in time. Existing digital MSK products (e.g. Hinge Health, Sword Health) focus on exercise tracking and motion capture for high-volume, low-acuity chronic pain — not on the documentation and clinical-reasoning burden of structured, surgeon-referred, protocol-driven recovery. That gap — turning scattered documents into a trustworthy, structured, auditable knowledge base per patient — is what this project targets.

### 3.2 Objectives

The project was built to design and implement, end to end:
- An event-sourced system where every piece of clinical knowledge is derived from an immutable, replayable log rather than mutable database rows.
- A document-to-structured-data pipeline using LLMs, with confidence scoring, source attribution, and a clear separation between what an LLM extracts and how conflicts get resolved.
- A retrieval-augmented generation setup with deliberately scoped, non-overlapping knowledge sources for two different audiences (clinician vs. patient).
- A production-shaped full-stack application — role-based auth, a real frontend for two distinct user types, and a live cloud deployment — rather than a local-only prototype.

### 3.3 Target Users

| Role | Description | Access |
|---|---|---|
| **Therapist** | A licensed clinician managing a caseload of patients. Signs up directly, gated by a clinic registration code. | Full caseload visibility, full patient profile detail (including provenance and flagged concerns), document upload, brief generation, copilot chat, phase advancement |
| **Patient** | An individual in an active rehab protocol. Their account is created by their therapist — patients never self-register. | Their own record only, a reduced view of their profile, check-in submission, and the patient assistant |

There is no admin/superadmin role — the system is designed for a single clinic.

### 3.4 Scope

**What the system does:**
- Structured patient intake with an invite-based account activation flow
- PDF document upload with asynchronous OCR/LLM extraction into structured, provenanced profile fields
- Deterministic conflict/contradiction handling with a therapist review queue for anything uncertain
- On-demand, AI-generated appointment-prep briefs and multi-turn copilot chat for therapists
- Patient check-ins (pain level + note) and therapist-controlled, forward-only phase progression
- A scoped, safety-gated Q&A assistant for patients
- A full patient timeline and a complete, replayable audit trail
- A quantitative evaluation loop for extraction accuracy

**What the system deliberately does not do:**
- No computer-vision motion tracking or exercise-form analysis
- No automated engagement/reminder infrastructure (push notifications, email nudges)
- No real email delivery — invite links are generated and shared manually by the therapist
- No multi-clinic / multi-tenant support
- No calendar or scheduled-appointment entities
- No patient self-registration, and no backward phase regression
- The clinical scope is limited to orthopedic/MSK rehab, with the current implementation built and validated against one protocol: ACL reconstruction recovery, a structured ~9–12 month timeline with clearly defined phase criteria — chosen because a well-defined protocol makes it possible to build and test real phase-progression and extraction logic rather than a generic placeholder.

---

## 4. System Architecture

### 4.1 Architectural Pattern

The backend is built as an **event-sourced CQRS (Command Query Responsibility Segregation) system**. The event store is the single source of truth; every other piece of derived state — the patient's Knowledge Profile, their Timeline, and the RAG vector indexes — is a disposable, rebuildable **projection** computed from the event log. Nothing is ever written directly to a read model.

```
Command → Command Handler (validates) → Event Store (append-only)
                                              │
                          ┌───────────────────┴───────────────────┐
                          ▼                                       ▼
                  Knowledge Builder                      Timeline / RAG Projector
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

Every projector (Knowledge Builder, Timeline, RAG) is applied synchronously and inline from the same command handlers that write the causing event — there is no separate replay/catch-up worker in the normal write path. A full replay of the event log was verified to reconstruct an identical Knowledge Profile from scratch, confirming the read models are genuinely derived rather than independently maintained state.

### 4.2 Command Handler Validation Pipeline

Every command passes through the same ordered validation pipeline before an event is appended:

1. **Structural** — schema/field validity, value ranges, no future timestamps
2. **Authorization** — is the acting user permitted to act on this resource
3. **Domain invariants** — protocol-specific rules (e.g. phase steps cannot be skipped; uploaded files must be PDF)
4. **Idempotency** — deduplication via a client idempotency key
5. **Referential integrity** — referenced IDs (patient, document) must actually exist

No LLM call ever happens inside a command handler — everything at the write boundary is deterministic.

### 4.3 Knowledge Builder: Merge Strategies

Each profile field is assigned one of four merge strategies, applied by fixed, auditable Python logic — never by the LLM:

| Strategy | Example fields | Behavior |
|---|---|---|
| Overwrite (latest wins) | `current_phase`, `active_restrictions`, `active_concerns` | New valid value replaces the old one |
| Append-only | `pain_history`, `milestones` | Accumulates; nothing is ever discarded |
| Derived / recomputed | `pain_trend`, `exercise_adherence` | Recalculated from history; never directly settable |
| Immutable-once-set | `injury`, `surgery_date` | A conflicting new value triggers review rather than a silent overwrite |

### 4.4 Contradiction Handling & Review Queue

Rather than blindly merging every fact an LLM extracts, the merge layer holds anything uncertain for explicit therapist review instead of writing it straight into the Knowledge Profile:

- A fact is **staged** (not merged) if it falls below a confidence threshold, or if it conflicts with an immutable baseline value (e.g. an extracted injury description that doesn't match the patient's recorded injury).
- For overwrite-strategy fields, if *any* fact in a batch is low-confidence, the whole batch is staged together — since an overwrite replaces every currently active value for that field at once, merging only the confident subset would silently discard context the therapist hasn't seen.
- Staged facts sit in a `PendingProfileFact` queue with a reason attached, visible to the therapist, who can **approve** (optionally editing the value first) or **reject** each one. Nothing reaches the Knowledge Profile — and therefore the Copilot or a prep brief — until it has either been auto-merged with high confidence or explicitly approved.
- This queue is separate from the general "needs review" contradiction flag that surfaces on a patient's record, which covers broader concerns like a missed check-in or an adherence drop.

### 4.5 Provenance & Versioning

Every field write carries a provenance record: `source_event_id`, `extracted_at`, `confidence`, and `extractor_version`. Every update creates a **new version** of the profile field, referencing the event that caused it — never an in-place mutation. This makes point-in-time queries and full event replay possible.

### 4.6 Retrieval-Augmented Generation (RAG) Scoping

Three separately scoped vector indexes exist, each backed by pgvector inside the same Postgres instance rather than a separate vector-store dependency:

1. **Per-patient document/note residual text** — filtered by patient and source type at query time
2. **Shared clinical guideline corpus** — accessible only to the Therapist Copilot
3. **Shared patient-education corpus** — accessible only to the Patient Assistant

Only unstructured prose is ever embedded — document narrative text, free-text notes, and the external guideline/education corpora. Structured fields, timeline metadata, and identifiers are never embedded, and a schema-allowlist check rejects any chunk that near-exact-matches a known structured field name or value before it can enter an index. Extraction always runs first; only the residual text left over after structured-fact extraction is chunked and embedded.

---

## 5. Technology Stack

| Layer | Technology |
|---|---|
| Backend framework | FastAPI |
| Database | PostgreSQL + pgvector |
| ORM / migrations | SQLAlchemy 2.x + Alembic |
| Async task queue | Celery + Redis |
| Frontend | React 18 + Vite |
| Frontend routing | React Router 6 |
| Frontend server state | TanStack Query |
| Frontend client state | Zustand |
| UI styling | Tailwind CSS |
| Auth | JWT (access + refresh) via PyJWT, bcrypt password hashing |
| PDF handling | pypdf |
| LLM (extraction, generation) | Groq (primary), Google Gemini (fallback) |
| Embeddings | Google Gemini embeddings |
| Document storage | Local volume in development, Azure Blob Storage in production |
| Containerization | Docker Compose |
| Cloud hosting | Microsoft Azure (Container Apps, a Linux VM, Flexible Server Postgres, Static Web Apps) |

---

## 6. Core Workflows

### 6.1 Therapist Onboarding
A therapist signs up with a name, email, password, and a clinic registration code. The password is hashed with bcrypt; on login, a short-lived JWT access token (15 minutes) and a longer-lived refresh token (7 days) are issued. The refresh token silently renews the access token in the background without forcing a re-login.

### 6.2 Patient Intake & Invite
A therapist submits a patient's name, date of birth, contact email, injury type, and surgery date. This produces an event that initializes the patient's Knowledge Profile, with `injury` and `surgery_date` marked immutable-once-set. A single-use invite link (48-hour expiry) is generated in the same step and displayed for the therapist to share manually — there is no email-sending infrastructure. The therapist can create and edit the patient's profile immediately, independent of whether the patient has activated their account yet.

### 6.3 Patient Account Activation
The patient opens their invite link (email pre-filled and locked), sets a password, and their account is activated and bound to the inviting therapist. They log in through the same endpoint as therapists; a `role` claim in the JWT determines which side of the app they land on.

### 6.4 Document Ingestion & Extraction
A therapist uploads a PDF (MRI report, discharge summary, referral note) attached to a patient. The command validates file type and ownership before appending an event. An asynchronous Celery worker then performs OCR and LLM-based extraction, returning candidate facts with a confidence score and a source quote for each. Deterministic merge routing (§4.3–4.4) applies each fact — auto-merging confident, non-conflicting facts and staging everything else for therapist review. The frontend shows a "Processing" state per document until extraction completes, then surfaces each field's value, confidence, and source.

### 6.5 Therapist Prep Briefs
On a patient's detail page, a therapist can generate a prep brief on demand. The system assembles the full Knowledge Profile, Timeline events since the last brief, and relevant clinical-guideline RAG chunks into a single structured LLM prompt, producing a three-section output — **Since last visit**, **Flags**, and **Suggested focus**. The brief is rendered inline; it is advisory-only and is never written back into the patient's profile or phase.

### 6.6 Patient Check-Ins
A patient submits a pain level (0–10) and an optional free-text note. This is an append-only write to `pain_history` — no prior check-in is ever discarded or overwritten.

### 6.7 Phase Progression
Only a therapist can advance a patient's `current_phase`, via an explicit action that offers only the single next phase in sequence — no skipping and no backward regression. The command handler rejects any out-of-sequence attempt regardless of what the UI allows. An optional note can be attached, and the action requires explicit confirmation.

### 6.8 Patient Assistant
A patient can ask single-turn questions answered against a separate, patient-education-only RAG corpus. Any question that reads as symptom-related or urgent is redirected to the clinic instead of being answered — this check runs deterministically before any RAG/LLM call, with the LLM's own judgment used only as a secondary backstop (see §7.4).

### 6.9 Patient Timeline
A chronological, per-patient timeline aggregates phase advances, extracted milestones, and document-extraction completions into one view, shown to both the therapist (with full detail) and the patient (with a reduced, non-clinical view of the same events).

### 6.10 Therapist Copilot Chat
Beyond the single-shot prep brief, therapists have access to a multi-turn chat scoped to one patient. Each message re-embeds the question, retrieves from both the patient-notes and clinical-guidelines RAG indexes, re-assembles the current Knowledge Profile and recent Timeline activity, and includes the real prior-turn message history for continuity — producing a grounded, if not tool-using, conversational interface on top of the same data the prep brief draws from.

---

## 7. AI / LLM Engineering

### 7.1 Extraction Pipeline
Document text is sent to the LLM with a schema-constrained prompt asking for structured facts (field name, value, confidence, source quote). Groq (`openai/gpt-oss-120b`) is the primary provider for all text-generation calls — extraction, briefs, assistant and copilot answers — with Google Gemini (`gemini-2.5-flash`) as an automatic fallback if the primary call fails. Gemini is also the sole provider for embeddings, since Groq has no embeddings API. Every LLM call is routed through a single provider-agnostic client module, so callers depend only on a fixed interface (`extract_facts`, `generate_brief_text`, `embed_text`, `answer_patient_question`, `answer_copilot_message`) and never on provider-specific types.

### 7.2 Deterministic Merge & Review Routing
The LLM only proposes facts with a confidence score — it never decides how a conflict is resolved or which merge strategy applies. That mapping is fixed Python logic keyed by field name (§4.3), and anything below a confidence threshold or in conflict with an immutable baseline is routed to the therapist review queue rather than merged automatically (§4.4).

### 7.3 Prep Brief Prompt Design
The brief prompt is a single structured call, not an agent loop — it takes the assembled Knowledge Profile, recent Timeline events, and retrieved clinical-guideline chunks, and is constrained to return exactly three sections. Advisory framing ("suggest, never instruct") is enforced directly in the prompt text as well as structurally, by the brief never being written back to the patient's record.

### 7.4 Patient Assistant Safety Design
Symptom/urgent-question detection uses a deterministic, word-boundary-aware keyword gate that runs *before* any RAG or LLM call — this is the primary safety mechanism, not a suggestion to the model. The LLM's own structured output includes a `redirect` flag as a secondary backstop, but the system never relies on the model alone to catch an urgent question. An early implementation of the keyword check used naive substring matching and incorrectly matched terms like "red" inside "reduce" and "er" inside "after" — this was caught and fixed by switching to word-boundary regex matching before the feature was considered complete.

### 7.5 Copilot Chat
The multi-turn copilot (§6.10) issues one structured LLM call per message, passing the real conversation history as a message array (not folded into a single prompt string), combined with fresh retrieval from two RAG indexes and a freshly re-assembled profile/timeline context on every turn — so answers stay grounded in current data rather than only in what was true when the conversation started.

### 7.6 Extraction Evaluation
A golden evaluation set of hand-labeled synthetic clinical notes is used to score the extraction pipeline with precision/recall/F1 per field. Current results:

| Field | Precision | Recall | F1 |
|---|---|---|---|
| `active_concerns` | 1.00 | 1.00 | 1.00 |
| `active_restrictions` | 1.00 | 1.00 | 1.00 |
| `surgery_date` | 1.00 | 1.00 | 1.00 |
| `injury` | 0.60 | 1.00 | 0.75 |
| `milestones` | 0.60 | 1.00 | 0.75 |
| **Overall** | **0.81** | **1.00** | **0.89** |

Recall is perfect across every field — the extraction pipeline never misses a fact that should have been found. The lower precision on `injury` and `milestones` comes from the LLM occasionally extracting additional, legitimate atomic facts that the evaluation's strict one-to-one label matching counts as false positives rather than true extras — a scoring-methodology artifact rather than evidence of hallucination, though a closer look at real false positives would be a natural next step in tightening the eval itself.

---

## 8. Frontend & UX

### 8.1 Information Architecture
The frontend is split into two independent shells selected by role after login: a therapist shell with a global sidebar (Dashboard / Caseload / Copilot) that switches to a contextual per-patient sidebar (Overview / Documents / Pending Review / Pain & Check-ins / Timeline / Provenance) when viewing a specific patient, and a patient portal shell with its own static sidebar (Overview / Check-in / Timeline / Ask Assistant). The two shells share no layout code — they are independent, role-specific experiences rather than one generic shell with conditional rendering.

### 8.2 Key Screens
- **Login / Signup** — role-aware auth, registration-code-gated therapist signup
- **Invite acceptance** — branded confirmation page, email pre-filled and locked
- **Therapist dashboard** — needs-review list, pending invites, phase distribution across the caseload, derived client-side from existing caseload data rather than a dedicated backend endpoint
- **Caseload list** — patient rows with phase, typed "needs review" badges, invite status
- **Patient intake form** — single submit creates the patient and generates the invite
- **Patient detail (per-patient tabs)** — Overview, Documents (upload + processing status), Pending Review (approve/reject staged facts), Pain & Check-ins, Timeline, Provenance
- **Copilot** — prep-brief generation and multi-turn chat
- **Patient portal (per-patient tabs)** — Overview, Check-in (pain slider + note), Timeline, Ask Assistant

### 8.3 Notable Design Decisions
- Dashboard metrics are computed client-side from data the app already fetches for the caseload list, rather than adding new backend endpoints purely for a summary view.
- The staged-facts review queue got its own dedicated tab and approve/reject UI rather than being folded into the general profile view, since it represents an action the therapist needs to take, not just information to read.
- `PrepBriefPanel` is scoped to the Copilot page only (not duplicated into per-patient tabs), to avoid two independent surfaces that could show inconsistent state for the same brief.

---

## 9. Security Posture

- Passwords are hashed with bcrypt and never stored or logged in plaintext.
- JWT access tokens are short-lived (15 minutes); refresh tokens last 7 days; invite links expire after 48 hours.
- Role-based access is enforced structurally at the query level — every query filters by `therapist_id`/`patient_id` directly in the query itself, rather than fetching broadly and filtering results afterward.
- The Patient Assistant's query API is hard-locked to `patient_id == token.sub` — a patient can only ever query their own record, at the code level, not by convention.
- CORS is explicitly scoped to the deployed frontend's origin in production.
- The advisory-only, never-autonomous posture (no AI output writes to a care plan) is enforced by the architecture itself — separate query modules per role, and briefs/assistant answers that are read-only outputs — not by a prompt-level instruction alone.
- The system runs on synthetic patient data only. It does not implement production-grade PHI handling — BAA-covered LLM hosting, full at-rest/in-transit encryption posture, and HIPAA-style audit logging are not in place, and would be required before this could touch real patient data.

---

## 10. Testing & Quality

- The backend test suite covers 224 test functions across 27 files, spanning every module: auth, patients, documents, check-ins, profile/merge logic, RAG (chunking, allowlist filtering, retrieval), timeline, briefs, copilot, and assistant.
- The golden evaluation set (§7.6) provides a quantitative accuracy signal for the extraction pipeline, run outside the normal test suite.
- One known intermittent test failure exists: a race condition where a live, always-running Celery worker container picks up and processes a document that a test is also driving directly, causing an occasional ordering mismatch in document/timeline-related tests. It passes reliably in isolation; the root cause is understood but not yet fixed.
- Beyond automated tests, each feature was manually verified end to end in the browser against the running stack before being considered complete — e.g. confirming a real document upload actually reaches "Processing" → extracted with populated fields, or that a symptom-sounding patient question is correctly redirected without an LLM call being made.

---

## 11. Deployment

### 11.1 Architecture
The application runs live on Microsoft Azure, using a **hybrid split** rather than a single server: the FastAPI API runs on Azure Container Apps (scale-to-zero, with built-in HTTPS ingress), while the Celery worker runs on a small Linux VM with **no public IP** at all. The API is the only component that needs to be reachable from the internet — the worker only needs outbound access to the database, Redis, and the LLM providers. This split removes the one guaranteed recurring cost (a VM's public IP) and avoids hand-rolling TLS.

### 11.2 Service Mapping

| Component | Azure / third-party service | Cost |
|---|---|---|
| Frontend | Azure Static Web Apps | $0 |
| API | Azure Container Apps (Consumption, scale-to-zero) | $0 |
| Worker | Azure VM (burstable, no public IP) | $0 |
| Database | Azure Database for PostgreSQL — Flexible Server (with pgvector) | $0 |
| Container registry | Azure Container Registry | $0 (12-month free tier) |
| Cache/broker | Upstash Redis (third-party) | $0 |
| Document storage | Azure Blob Storage | $0 |

**Net cost: $0/month.**

### 11.3 Constraints Handled
- `pgvector` is off by default on Flexible Server and had to be explicitly allowlisted before `CREATE EXTENSION vector` would work.
- The Celery worker deliberately stays on the VM rather than also moving to Container Apps — a continuously-polling process burns through Container Apps' consumption-based free quota in days, then bills at a rate worse than the VM this architecture was built to avoid.
- Frontend and API are genuinely cross-origin in production (unlike the same-origin dev proxy setup locally), so CORS middleware scoped to the frontend's domain is required in the API.
- Container Apps' scale-to-zero means the first request after idle time pays a short cold-start penalty — an acceptable trade for a low-traffic application.
- The worker VM needs zero inbound rules; Azure VMs get outbound-only internet access by default even without a public IP attached, which was confirmed working.
- Several of the free-tier resources (Flexible Server, the worker VM, Container Registry) are tied to a 12-month free-tier clock rather than being permanently free, which is tracked against the account's creation date.

### 11.4 Post-Deploy Hardening
An unused static public IP left attached to the worker VM (contradicting the "no public IP" design and the exact cost the hybrid split was meant to avoid) was identified and removed during a review pass, with outbound connectivity confirmed unaffected afterward.

**Known open items:** secrets currently live as plain environment variables rather than in a managed secret store (Key Vault); centralized logging/observability (e.g. Application Insights) is not yet wired in; and the container registry's free tier has a fixed 12-month expiry that will need a decision (downgrade tier or migrate images) before it lapses.

---

## 12. Development Process

The system was built incrementally, in dependency order: the append-only event store and its enforcement came first, since every other module depends on it; then therapist authentication and patient intake; then document upload with asynchronous OCR/LLM extraction; then check-ins and phase progression; then the first version of the React frontend. Once that foundation was working end to end, the LLM-driven features were layered on top in sequence — fact extraction with provenance and contradiction handling, the RAG chunking/embedding pipeline, prep-brief generation, and the patient assistant — followed by a full frontend rework into the role-specific sidebar layouts described in §8, and finally the multi-turn copilot chat. Cloud deployment to Azure was done as a distinct final phase once the application was feature-complete locally.

Each module was built test-first where practical, backed by a real test suite per feature (§10), and verified manually in a running browser before being considered done — not just passing automated tests.

---

## 13. Challenges & Key Decisions

- **Injury-contradiction false positives.** An early version of contradiction detection compared extracted injury text to the patient's baseline injury field using exact string matching, which flagged nearly every real document as contradictory since natural language never matches a fixed slug like `acl_reconstruction`. Fixed by switching to keyword-based matching (e.g. checking for "acl" or "anterior cruciate ligament") instead of exact equality.
- **LLM provider quota limits.** Gemini's free-tier quota for its stronger model was exhausted quickly during development (20 requests/day), which forced a provider strategy rethink — Groq became the primary generation provider, with Gemini kept as an automatic fallback and as the sole embeddings provider, rather than depending on a single free-tier-constrained model for everything.
- **Confidence-based review queue over silent auto-merge.** Initially, extracted facts were merged automatically with just a "needs review" flag on contradictions. This was reworked into an explicit staging queue (§4.4) so nothing uncertain — low-confidence or conflicting — reaches the Knowledge Profile, and therefore any AI-generated brief or chat answer, without a therapist explicitly approving it first.
- **Substring-matching bug in urgent-question detection.** The first pass at the patient assistant's safety keyword check used plain substring matching, which incorrectly flagged words like "reduce" (contains "red") and "after"/"better" (contain "er") as urgent-symptom language. Fixed with word-boundary regex matching before the feature was considered complete.
- **Frontend route collision.** The per-patient contextual sidebar is selected by matching the `/patients/:id/*` route pattern, which also matched the sibling static route `/patients/new` — treating the literal string "new" as if it were a patient ID. Fixed by explicitly excluding that value in the route-matching logic.
- **Cost-driven deployment architecture.** Rather than a single always-on server, the deployment was deliberately split so the continuously-running Celery worker sits on a free-tier VM while the bursty API scales to zero on Container Apps — a direct response to the two Azure services having very different free-tier billing models (§11.3).

---

## 14. Capabilities Delivered

Verified end to end, against a seeded synthetic ACL patient journey covering pre-op through several months post-op:

1. Therapist signup (registration-code gated) and login
2. Patient record creation with a shareable invite link generated in the same action
3. Patient account activation via the invite link, and login
4. PDF document upload, visibly transitioning from "Processing" to extracted, with populated fields, confidence scores, and source attribution
5. Low-confidence or contradicting extracted facts routed to a therapist review queue, with approve/reject actions
6. A typed "needs review" badge surfaced in both the caseload list and patient detail view for unresolved concerns
7. On-demand prep-brief generation, populated from real profile, timeline, and retrieved clinical-guideline context — not placeholder text
8. Multi-turn copilot chat on a specific patient, grounded in live profile/timeline/RAG context each turn
9. Forward-only phase advancement, with an out-of-sequence attempt rejected by the command handler itself
10. Patient check-in submission (pain level + note), reflected server-side in `pain_history`
11. Patient assistant answering general questions from a scoped education corpus, and redirecting symptom/urgent-sounding questions to the clinic instead
12. A chronological patient timeline visible to both roles, with role-appropriate detail
13. Full event-log replay reconstructing an identical Knowledge Profile from scratch
14. A quantitative extraction-accuracy evaluation (precision/recall/F1 per field) run against a golden note set
15. The entire stack — API, worker, database, frontend — starting from a single `docker compose up`, and the same application running live in production on Azure

---

## 15. Future Work

- **Additional rehab protocols.** The architecture (field schemas, phase definitions, evaluation sets, RAG corpora) was designed to be per-protocol config rather than hardcoded to ACL reconstruction, but only the ACL protocol has actually been built and validated — extending to other orthopedic/MSK protocols (e.g. knee replacement, hip replacement, shoulder, sports rehab, lower back pain) would be the next natural step in proving that out.
- **Production-grade security hardening.** Migrating secrets out of plain environment variables and into a managed secret store, wiring in centralized logging/observability, and resolving the container registry's free-tier expiry.
- **Deeper agentic behavior in the copilot.** The current copilot chat is a grounded, context-rich conversational interface, but it doesn't yet take autonomous multi-step actions (e.g. iteratively deciding what to query next, or proactively surfacing caseload-wide patients needing review) — moving toward genuine tool-using agent behavior on top of the existing data layer is a logical extension.
- **Tightening the extraction evaluation.** The evaluation's strict one-to-one fact matching under-counts legitimate extra extractions as false positives (§7.6); refining the scoring methodology would give a more accurate picture of true extraction quality.
- **Fixing the known test race condition.** The intermittent Celery-worker test failure (§10) has an understood root cause but hasn't been fixed yet.
- Features intentionally left out of scope throughout — multi-tenant support, real email delivery, computer-vision motion tracking, calendar/appointment entities — remain open if the project were to grow beyond a single-clinic, single-protocol system.

---

## 16. Conclusion

This project delivered a complete, working clinical software system — not just individual pieces of technology in isolation, but an event-sourced backend, an LLM extraction and RAG pipeline with real safety and provenance guarantees, a role-specific frontend for two different kinds of users, and a live, cost-free production deployment, all integrated into one coherent application. Building it end to end forced real engineering trade-offs rather than academic ones: how much to trust an LLM's output before a human reviews it, how to keep a "read model" honestly derived from an event log instead of drifting into ad hoc mutable state, how to scope retrieval so a clinician-facing feature and a patient-facing feature never leak into each other, and how to deploy a multi-service application within a genuinely free infrastructure budget. The system meets every capability it set out to demonstrate (§14), and the gaps that remain (§15) are well understood rather than unknown unknowns — which is arguably the most useful outcome of a project built to learn from.

---

## 17. Appendix

### 17.1 Full API Surface

| Method & Path | Access | Purpose |
|---|---|---|
| `POST /auth/signup` | Public (registration code required) | Therapist account creation |
| `POST /auth/login` | Public | Issue access + refresh tokens |
| `POST /auth/refresh` | Authenticated | Renew access token |
| `GET /auth/invite/{token}` | Public | Validate invite token |
| `POST /auth/invite/{token}` | Public | Patient sets password, activates account |
| `POST /patients` | Therapist | Create patient (intake) |
| `GET /patients` | Therapist | List caseload |
| `GET /patients/{id}` | Therapist or owning patient | Profile detail (response shape differs by role) |
| `POST /patients/{id}/phase` | Therapist | Advance phase (forward-only) |
| `GET /patients/{id}/pending-facts` | Therapist | List staged facts awaiting review |
| `POST /patients/{id}/pending-facts/{fact_id}/approve` | Therapist | Approve a staged fact (optionally edited) |
| `POST /patients/{id}/pending-facts/{fact_id}/reject` | Therapist | Reject a staged fact |
| `POST /patients/{id}/documents` | Therapist | Upload document |
| `GET /patients/{id}/documents` | Therapist | List documents + ingestion status |
| `POST /patients/{id}/checkins` | Patient (own record only) | Submit check-in |
| `GET /patients/{id}/brief` | Therapist | Fetch latest generated brief |
| `POST /patients/{id}/brief` | Therapist | Generate a new prep brief |
| `GET /patients/{id}/timeline` | Therapist or owning patient | Chronological patient timeline |
| `POST /patients/{id}/assistant` | Patient (own record only) | Ask the patient assistant a question |
| `GET /patients/{id}/copilot/messages` | Therapist | Fetch copilot chat history |
| `POST /patients/{id}/copilot/messages` | Therapist | Send a copilot chat message |

### 17.2 Backend Module Structure

```
core/        config, security (hashing, JWT), db session, LLM client, Redis client
event_store/ append-only Event table + append_event() — the only write entry point
auth/        signup, login, refresh, invite acceptance
patients/    intake, listing, detail, phase advancement, pending-fact review
documents/   upload, listing, storage, async extraction task
checkins/    patient check-in submission
profile/     Knowledge Builder — merge logic, provenance, pending-fact staging
timeline/    Timeline projector and query endpoint
rag/         chunking, embedding, allowlist filtering, scoped retrieval
briefs/      prep-brief generation
assistant/   patient Q&A, urgent-question detection
copilot/     multi-turn therapist chat
query_api/   therapist.py and patient.py — separate modules, separate return types
```

### 17.3 Frontend Module Structure

```
shared/ui/        base UI primitives
shared/api/        JWT-attaching fetch client with refresh interceptor
shared/auth/        ProtectedRoute, Zustand auth store
shared/layout/       TherapistShell, PatientPortalShell
shared/components/  cross-role shared panels (e.g. timeline)
pages/               Login, Signup, InviteAccept, Dashboard, Caseload, Copilot,
                     IntakeForm, patient-detail/*, patient-portal/*
```

