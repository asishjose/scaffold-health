# Scaffold Health — CI/CD Automation Plan

**Status:** Planning — nothing in this doc is implemented yet, except the one workflow noted as already live.
**Date:** 2026-08-17
**Scope:** Every service in the stack — frontend, backend API, Celery worker, container registry, and DB migrations.

---

## 1. Current state

| Piece | Automated today? | How |
|---|---|---|
| Frontend build + deploy | ✅ Yes | [azure-static-web-apps-salmon-moss-0f742761e.yml](../.github/workflows/azure-static-web-apps-salmon-moss-0f742761e.yml) — push to `main` or PR → build `/frontend` → deploy to Static Web Apps |
| Backend tests | ❌ No | `backend/tests/` (pytest, DB-backed) exists but nothing runs it in CI |
| Frontend typecheck/lint | ⚠️ Partial | `tsc -b` runs as part of `npm run build` inside the SWA workflow, so a type error already fails the deploy — but there's no lint, and no dedicated CI check on branches other than `main`/PRs |
| Backend image build | ❌ No | Manual `docker build` + push, by hand |
| API deploy (Container Apps) | ❌ No | Manual `az containerapp update`, by hand |
| Worker deploy (VM) | ❌ No | Manual SSH-less update — currently whatever manual process was used to land the last two `fix:` commits |
| DB migrations | ❌ No | Manual `alembic upgrade head`, run by hand against the Flexible Server |
| Infra provisioning | ❌ No | All resources created by hand via `az` CLI / portal, no IaC |

**Real Azure resources in play** (confirmed live via `az resource list`, resource group `scaffold-app-rg` unless noted):

| Resource | Name | Notes |
|---|---|---|
| Container Registry | `scaffoldhealthacr` (`scaffoldhealthacr.azurecr.io`) | Holds `scaffold-api:latest`, pulled via the Container Apps environment's **system-assigned managed identity** — no ACR admin credentials in use |
| Container App (API) | `scaffold-api` | min replicas 0, max 10; FQDN `scaffold-api.bluepond-8365be39.westus2.azurecontainerapps.io` |
| Container Apps environment | `managedEnvironment-scaffoldapprg-9fe9` | |
| Worker VM | `scaffold-worker` (`Standard_B2ats_v2`) | **No public IP** (private IP `10.1.1.4` only) — this shapes the worker deploy design in §4.3 |
| Postgres Flexible Server | `asish-shared-pg-server` (in separate RG `shared-db-rg` — shared across projects) | |
| Static Web App | `scaffold-frontend` | |
| Blob storage | `scaffoldhealthdocs` | |

No Azure AD App Registration / federated credential exists yet for GitHub Actions → Azure auth (checked via `az ad app list --show-mine` — empty). That has to be created as part of this plan; see §3.

---

## 2. What can be automated — full inventory

### Frontend (Static Web Apps)
- Already automated: build + deploy on push/PR. **Keep as-is.**
- Add later, optional: ESLint has no config in this repo yet, and there's no frontend test runner — not proposing to add test tooling here since none exists to wire up; noting it as a future gap, not part of this plan.

### Backend API — tests
- Run `pytest` (backend/tests/) on every push and PR touching `backend/**`.
- Tests run real Alembic migrations against a real Postgres at session start (`conftest.py`), so CI needs a **Postgres service container with pgvector** (`pgvector/pgvector:pg16`, same image as `docker-compose.yml`) and a Redis service container — both trivial as GitHub Actions `services:`.

### Backend API — build & deploy
- Build the Docker image (`backend/Dockerfile`) and push to `scaffoldhealthacr`, tagged with the git SHA (plus a floating `latest`).
- Roll the new image out to the `scaffold-api` Container App (`az containerapp update --image ...`).
- Smoke-test the deployed revision (hit a health endpoint) before calling the deploy green.

### Worker — build & deploy
- Same image (the Dockerfile already supports both roles — `docker-compose.yml` just overrides the `command:` for `worker` vs `api`), so no second Dockerfile needed.
- **The VM has no public IP**, so GitHub Actions can't SSH into it directly. The clean way to reach it without opening any inbound port is **`az vm run-command invoke`** — it goes through the Azure control plane (VM agent), not the network, so it works identically whether or not the VM is internet-reachable. The run-command script does `docker pull` + recreate the worker container.
- Noted alternative for later: install a self-hosted GitHub Actions runner *on* the VM (outbound-only registration with GitHub, no inbound needed either). More native than `run-command` shell scripts, but it's another long-lived process to maintain on a box with no public IP — not necessary for a first pass.

### Database migrations
- Automate `alembic upgrade head` as an explicit step in the deploy pipeline rather than a manual one-off.
- Recommended mechanism: a dedicated **Azure Container Apps Job** in the same environment as `scaffold-api`, using the same freshly-pushed image with command overridden to `alembic upgrade head`. It reuses the exact network path the API already uses to reach `asish-shared-pg-server` (which already works today), so there's no firewall/IP-allowlist dance needed per deploy — unlike running migrations from the GitHub-hosted runner, which would need the Flexible Server firewall opened to GitHub's dynamic IP ranges every time.
- Ordering matters: migration job must complete successfully **before** the API/worker are pointed at the new image, since new code may assume the new schema.

### Infra provisioning (flagged, not in scope here)
- Everything above was created by hand (`az` CLI / portal). Converting `scaffold-app-rg` to Bicep or Terraform would make the environment reproducible and let infra changes go through PR review too — worth doing eventually, but it's a separate, larger effort from wiring up app-level CI/CD. Not proposed as part of this plan.

### Secrets/config
- Recommend CI/CD stays scoped to **code and image delivery**, not secret values. `GROQ_API_KEY`, `GEMINI_API_KEY`, DB connection strings, etc. continue to be set by hand on the Container App and the VM's `.env`, as today (Key Vault migration is already tracked as Phase 5 in [DEPLOYMENT.md](DEPLOYMENT.md)). Keeping secret rotation manual and out of workflow YAML avoids a whole extra class of leak risk for a clinical-data app.

---

## 3. Auth: GitHub Actions → Azure

No credentials exist for this yet. Recommend **OIDC federated credentials** (no long-lived secret stored in GitHub at all) over a service-principal-with-client-secret:

1. Create an App Registration (e.g. `scaffold-health-gha`).
2. Add a federated credential trusting GitHub's OIDC issuer, scoped to this repo and branch: subject `repo:asishjose/scaffold-health:ref:refs/heads/main` (add a second one scoped to `pull_request` only if PR workflows need Azure access — CI/test workflows shouldn't need Azure creds at all, only the deploy workflows do, and those should stay `main`-only).
3. Grant **narrowly-scoped** RBAC roles to that App Registration's service principal — not subscription-wide Contributor:
   - `AcrPush` on `scaffoldhealthacr` only
   - A Container Apps-scoped role (`Container Apps Contributor` or a custom role limited to `Microsoft.App/containerApps/*` and `Microsoft.App/jobs/*`) scoped to the `scaffold-app-rg` resource group
   - `Virtual Machine Contributor` scoped to the `scaffold-worker` resource only (needed to call `run-command`)
4. Store only non-secret identifiers in GitHub repo variables: `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`. Nothing secret to rotate.

---

## 4. Proposed workflows

### 4.1 `backend-ci.yml` — new
- Trigger: PR and push, paths `backend/**`.
- Job: spin up `pgvector/pgvector:pg16` + `redis:7-alpine` as service containers, install `requirements-dev.txt`, run `pytest`.
- No Azure auth needed — pure signal, safe to turn on immediately with zero blast radius.

### 4.2 `backend-deploy.yml` — new
- Trigger: push to `main`, paths `backend/**`. Gated behind a GitHub **Environment** (`production`) with required reviewer approval — see §6.
- Jobs, in order:
  1. **build-and-push** — `docker build` from `backend/Dockerfile`, `az acr login` (OIDC), push tagged `scaffoldhealthacr.azurecr.io/scaffold-api:<git-sha>` and re-tag `:latest`.
  2. **migrate** (needs: build-and-push) — run the Container Apps Job (§2, Database migrations) pointed at the `:<git-sha>` image; fail the workflow if this fails, and stop here — nothing downstream runs.
  3. **deploy-api** (needs: migrate) — `az containerapp update -n scaffold-api -g scaffold-app-rg --image scaffoldhealthacr.azurecr.io/scaffold-api:<git-sha>`, then curl the health endpoint on the resulting revision.
  4. **deploy-worker** (needs: migrate, can run in parallel with deploy-api) — `az vm run-command invoke` on `scaffold-worker`: `docker pull` the new tag, stop/remove the old worker container, start the new one with the same env file already on the VM.
- `concurrency: group: backend-deploy, cancel-in-progress: false` so two pushes to `main` can't race and interleave partial deploys.

### 4.3 Frontend
- Leave [azure-static-web-apps-salmon-moss-0f742761e.yml](../.github/workflows/azure-static-web-apps-salmon-moss-0f742761e.yml) exactly as-is. It already builds and blocks on `tsc` failures; no changes needed for this plan.

---

## 5. Tagging & rollback

- Deploy by **git SHA tag**, not `latest` — `latest` stays as a convenience alias only. This means `az containerapp update --image ...:<sha>` always references an exact, known-good commit.
- Container Apps keeps prior revisions automatically — rollback is pointing traffic at a previous revision or re-running `az containerapp update` with the previous SHA tag, no rebuild required.
- Worker rollback: same idea — re-run the `run-command` script with the previous SHA tag. Worth logging the previously-deployed tag somewhere visible (workflow summary output is enough) so a manual rollback has something to reference.

## 6. Guardrails (this touches real patient data)

- **Manual approval gate** on `backend-deploy.yml` via a GitHub `production` Environment with a required reviewer — unlike the frontend (static content, low risk), API/worker/migration changes touch the real DB and should not auto-deploy unattended on every merge to `main`. This is the one place in this plan that's a judgment call rather than a fact — flagging it explicitly in §8 below rather than deciding it silently.
- Migrations never auto-rollback. A failed migration fails the workflow loudly and hard-blocks the API/worker deploy steps (already encoded in the job dependency chain in §4.2).
- No secret values ever move through workflow YAML (§2, Secrets/config).

## 7. Phased rollout order

Recommend landing this incrementally rather than as one big-bang PR, so each phase is independently low-risk and reviewable:

1. **Phase A** — `backend-ci.yml` (tests only, no Azure auth, no deploy changes). Pure signal, ship first.
2. **Phase B** — One-time Azure setup: App Registration + federated credential + scoped RBAC (§3).
3. **Phase C** — Build-and-push job only (validate image lands in ACR correctly before touching prod deploy).
4. **Phase D** — Migration Container Apps Job, validated standalone against the real schema before wiring into the deploy chain.
5. **Phase E** — `deploy-api` job + health-check, behind the `production` environment gate.
6. **Phase F** — `deploy-worker` job via `run-command`, same gate.
7. **Phase G (optional, later)** — Frontend lint/test tooling once it exists; IaC for `scaffold-app-rg`; Key Vault-backed secrets (already tracked as DEPLOYMENT.md Phase 5).

## 8. Open decisions (need your call, not assumed)

- **Approval gate:** auto-deploy backend on every push to `main`, or require a manual click-to-approve given this is clinical data? Plan above assumes the latter (recommended) — confirm before Phase E/F.
- **Worker deploy mechanism long-term:** `az vm run-command` (recommended, no new standing infrastructure) vs. a self-hosted Actions runner on the VM (more native, but another long-lived process to maintain). Plan above assumes `run-command`.
- **Atomic vs. independent API/worker deploys:** plan above runs them in parallel off the same migrated image in one workflow run (§4.2) — confirm that's the right coupling, vs. wanting to deploy API and worker independently on separate schedules.
