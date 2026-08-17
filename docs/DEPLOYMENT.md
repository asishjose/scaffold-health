# Scaffold Health — Cloud Deployment Plan (Azure Free Tier)

**Version:** 1.0
**Status:** Deployed (Phases 0–3b complete as of 2026-08-17); Phase 4 verification in progress
**Target:** First production deployment (fresh install, no data migration)

---

## 1. Summary

This is the plan to take Scaffold Health from local Docker Compose (see `docker-compose.yml`) to a live deployment on Azure, using the free tier for all core infrastructure. Chosen over AWS and GCP because Azure is the only one of the three offering a genuinely free 12-month managed Postgres instance alongside free compute — AWS dropped its 12-month free tier for accounts created after July 15, 2025 (new accounts get a $100–200 credit expiring in 6 months instead), and GCP has no free tier for Cloud SQL or Memorystore at any account age.

This is a fresh deploy — no existing production data, so no data migration or downtime window to plan around.

**Architecture is a hybrid split, not "everything on one VM":** the FastAPI API runs on Azure Container Apps (scale-to-zero, bundled free HTTPS ingress) while the Celery worker runs on the free VM with no public IP at all. The API is the only piece that needs to be reachable from the internet — the worker only needs outbound access to Redis/Postgres/Groq/Gemini. Splitting them this way removes the one guaranteed paid line item (a VM's public IP, ~$3–4/month) and avoids hand-rolling TLS, at the cost of deploying to two compute platforms instead of one.

---

## 2. Service mapping

| Component (docker-compose service) | Azure / third-party service | Tier | Cost |
|---|---|---|---|
| `db` (Postgres + pgvector) | Azure Database for PostgreSQL — **Flexible Server**, Burstable B1MS | 12-month free (750 hrs/mo, 32GB storage + 32GB backup) | $0 |
| `api` (FastAPI) | **Azure Container Apps** — Consumption plan, scale-to-zero, built-in HTTPS ingress | Always free (180,000 vCPU-s, 360,000 GiB-s, 2M requests/mo) | $0, as long as traffic stays bursty enough to scale to zero between requests |
| `worker` (Celery) | Azure VM — **B2ats v2** (AMD burstable), **no public IP attached** | 12-month free (750 hrs/mo) | $0 |
| Container image registry | **Azure Container Registry**, Standard tier (needed to push the API's image for Container Apps to pull) | 12-month free (100GB storage, 10 webhooks) — tied to this subscription's free-account clock, confirmed live in-portal under Subscription → "Free services for 12 months" (**expires 2027-05-19**), not a permanent always-free tier | $0 |
| `redis` (Gemini query-embedding cache) | **Upstash Redis** (third-party, permanent free tier) | Always free (256MB, 500K commands/mo) | $0 |
| `frontend` (React) | Azure **Static Web Apps** | Always free (100GB bandwidth, auto-HTTPS) | $0 |
| `document_uploads` volume | Azure **Blob Storage**, or VM local disk for v1 | 12-month free / included in VM disk allowance | $0 |

**Net cost: $0/month.** No component in this version of the plan has an unavoidable charge — the public IP cost from the single-VM plan is gone because the VM no longer needs to be internet-reachable.

Redis has no free managed tier on any of the three major clouds (Azure Cache for Redis, AWS ElastiCache, GCP Memorystore are all fully paid) — Upstash was chosen as the free third-party alternative over self-hosting Redis on a second VM, to keep the architecture simpler for a first go-live.

---

## 3. Known constraints and gotchas

- **`pgvector` is off by default** on Flexible Server — must be allowlisted manually (`azure.extensions` → `vector` in Server Parameters) before `CREATE EXTENSION vector;` will work.
- **Container Apps' free quota is consumption-based, not a flat allowance — this is *why* the worker doesn't live there.** The free 180,000 vCPU-seconds/month suits a bursty, scale-to-zero API well (you're only billed while a request is actually being handled), but a continuously-running process (like the Celery worker, which must always be polling) burns through that quota in about 4 days, then bills at idle rates — working out to roughly **$11/month**, worse than the VM+public-IP cost this hybrid was meant to avoid. This is the reason the worker stays on the VM instead of also moving to Container Apps.
- **Cold starts on the API.** When Container Apps scales to zero between requests, the next request pays a few seconds of extra latency while a fresh container starts. Acceptable for a low-traffic clinical app, but worth knowing before assuming request latency is always fast.
- **Frontend and API will be on different origins in production.** Locally, the Vite dev proxy makes everything same-origin; in production, the Static Web Apps domain and the Container Apps domain are genuinely cross-origin. **CORS middleware must be added to FastAPI**, scoped to the Static Web Apps domain — there's no way around this regardless of which Azure compute service hosts the API.
- **TLS is free and automatic on this path** — a real advantage of moving the API to Container Apps over the single-VM plan. Container Apps provisions a managed HTTPS endpoint out of the box; no reverse proxy, no Let's Encrypt, no DNS name label setup needed (all of which the single-VM version of this plan required).
- **The worker VM needs zero inbound rules — no public IP, no open ports from the internet.** It only makes outbound calls (to Flexible Server, Upstash, Groq, Gemini). Azure VMs get free outbound-only internet access by default even without a public IP resource attached. Note: Microsoft has signaled this implicit "default outbound access" behavior is being phased toward requiring an explicit NAT Gateway (a paid resource) for reliability at scale — fine for this project's traffic level today, but worth re-checking at deploy time in case the default behavior has changed.
- **B-series VMs are burstable, not sustained-load compute.** CPU usage above baseline draws down accumulated credits; once exhausted, the VM throttles to baseline performance rather than being billed extra — as long as it stays in **Standard** bursting mode (not **Unlimited**, which does bill for sustained overage). The worker's actual work (mostly waiting on external Groq/Gemini API calls) is I/O-bound, which suits burstable compute well.
- **External LLM/embedding calls are outside Azure's free tier entirely.** Groq (extraction/briefs) and Gemini (embeddings) have their own separate rate limits — already hit once in development (`gemini-flash-latest`'s free tier was only 20 req/day, which is why extraction moved to Groq and Gemini was scoped down to embeddings only). Azure hosting being free doesn't change this constraint.
- **No redundancy.** Every free-tier resource here is single-instance — no autoscaling beyond Container Apps' own scale-out, no managed load balancer in front of the worker. This is a real but low-traffic production setup, not a highly-available one.
- **The 12-month clock is real** for the Flexible Server and the worker VM (Container Apps and Static Web Apps' Always Free tiers don't expire on a 12-month clock, only on usage). Set a Cost Management budget alert before provisioning anything, both as an early warning if usage patterns push any component past its free quota, and for when the 12-month window closes.

---

## 4. Deployment order

### Phase 0 — Guardrails
1. Confirm the Azure subscription is `Active` and note its Offer type (Cost Management + Billing → Subscriptions).
2. Set a Cost Management budget alert (e.g. $10/month threshold) before creating any resource.
3. Note the account creation date to track the 12-month free-tier deadline.

### Phase 1 — Data layer
4. Create the Postgres **Flexible Server** (Burstable B1MS).
5. Enable the `pgvector` extension (`azure.extensions` → `vector`, restart, `CREATE EXTENSION vector;`).
6. Create a free **Upstash Redis** database.

### Phase 2 — Production-ready code (before deploying)
7. Add CORS middleware to FastAPI, scoped to the Static Web Apps domain.
8. Replace the dev `uvicorn --reload` command with a production entrypoint for the API's Dockerfile (used by Container Apps) and a separate one for the worker (used on the VM).
9. Point config at production values: DB connection string → Flexible Server, Redis URL → Upstash, `GROQ_API_KEY` / `GEMINI_API_KEY` set for real.
10. Decide on document storage for v1: Blob Storage now, or VM local disk with a planned later migration.
11. Frontend: wire the API base URL to an env var, pointed at the future Container Apps FQDN, and confirm `npm run build` produces a clean static bundle.

### Phase 3a — Deploy the API to Container Apps
12. Create an **Azure Container Registry** (Standard tier, 12-month free) and push the API's production image to it.
13. Create a Container Apps **environment**, then a Container App from that image with ingress enabled (external, HTTPS) and **min replicas = 0** so it scales to zero when idle.
14. Set the API's environment variables/secrets on the Container App (DB connection string, `GROQ_API_KEY`, `GEMINI_API_KEY`, Upstash Redis URL).
15. Run `alembic upgrade head` against the Flexible Server (fresh schema, no existing data to migrate) — either as a one-off Container Apps Job, or locally with a temporary Flexible Server firewall rule allow-listing your IP.

### Phase 3b — Deploy the worker to the VM
16. Create the **B2ats v2** VM.
17. Configure the NSG with **no inbound rules from the internet** — the worker never needs to be reached from outside. Management access (if needed) via Azure's Bastion/Serial Console rather than opening SSH publicly.
18. Install Docker on the VM, deploy just the worker container (`docker compose up -d worker` equivalent, with `restart: always`, or a systemd unit) pointed at the same Flexible Server and Upstash Redis instance as the API.

### Phase 4 — Verify
19. Smoke test core flows: document upload → extraction, RAG copilot chat, patient timeline, patient assistant Q&A.
20. Confirm CORS works from the real Static Web Apps origin, not just localhost, and that the Container Apps HTTPS endpoint responds correctly after a cold start.
21. After 24–48h, check Cost Management → Cost analysis to confirm nothing unexpected is billing — this plan has no line item that should show a charge under normal low-traffic usage.

### Phase 5 — Hardening (post-launch, non-blocking)
22. Migrate documents to Blob Storage, if deferred in step 10.
23. Move secrets into Key Vault instead of a VM-local `.env` file.
24. Wire the existing structured JSON logging/trace correlation into Application Insights.
25. Before **2027-05-19** (when this subscription's free-account year ends, taking the free Container Registry with it — see §2), either downgrade the registry to Basic (~$5/mo, still not free) or migrate images to a permanent free registry (e.g. AWS ECR Public — 50GB storage + 500GB–5TB/mo free egress, an official always-free tier, verified 2026-08-16). Also re-check the Postgres Flexible Server and worker VM free-tier clocks at the same time, per the 12-month note in §3.

---

## 5. Why not AWS or GCP

| | AWS (new account) | Azure | GCP |
|---|---|---|---|
| Free compute | $100–200 credit only, ~4–5 months burn at this stack's usage rate | 12 months, genuinely free | Forever, but only one `e2-micro` (1 vCPU, 1GB RAM) |
| Free managed Postgres | None (credit-funded only; Aurora's 2026 free-tier addition is also credit-funded, not permanent) | **12 months, genuinely free** | None, ever |
| Free managed Redis | None | None | None |

Accounts created on AWS before July 15, 2025 ("legacy") still get the old 12-month EC2/RDS/S3 model, structurally similar to Azure's current offer — but that doesn't apply to a fresh signup today.
