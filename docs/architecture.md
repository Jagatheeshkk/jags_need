# Architecture

```
Browser ──► Next.js (Vercel Hobby / local :3000)
              │  same-origin /api/* rewrite (server-side proxy)
              ▼
            FastAPI (Render Free / local :8000)
              │  SQLAlchemy 2 + psycopg 3, small pool, pre-ping
              ▼
            PostgreSQL (Neon Free / Docker postgres:17)
```

## Why a same-origin proxy

The browser only talks to the frontend origin. `next.config.ts` rewrites `/api/:path*` to
`BACKEND_URL`. Session cookies are therefore first-party, `HttpOnly`, `SameSite=Lax`, and are
not affected by third-party-cookie blocking. `BACKEND_URL` is server-side only (no `NEXT_PUBLIC_`).

## Backend layout (`services/api/app`)

| Package | Responsibility |
|---|---|
| `core/` | Settings (env only; free-provider validation), scoring weights |
| `db/` | Declarative base, naming conventions, engine/session |
| `models/` | 18 tables (the 17 required + `alembic_version` is Alembic's own) |
| `schemas/` | Pydantic request/response models with validation |
| `repositories/` | Query helpers |
| `services/` | Profile, portals, readiness, export/delete, audit |
| `connectors/` | `PortalConnector` interface, mock connector, unverified real-portal placeholders |
| `security/` | Argon2id hashing, signed session cookies, login rate limiter |
| `api/` | Routers and dependencies (auth, CSRF) |
| `workers/` | Reserved for future task entry points (tasks run via `services/tasks.py`) |

## Data model highlights

* UUID primary keys, UTC `timestamptz`, JSONB on Postgres (JSON on SQLite for tests).
* `applications (user_id, job_id)` unique → duplicate applications are impossible at the DB level.
* `applications.idempotency_key`, `profile_sync_runs.idempotency_key`, `notifications.dedupe_key`
  unique → retries after a sleep/restart cannot double-act.
* `jobs.content_hash` + `job_sources (portal_id, external_id)` unique → dedup foundations.
* `jobs.is_synthetic`, `applications.is_simulated` → mock data is never presented as real.
* No passwords, cookies or API keys in the database. `portal_connections.credential_ref`
  holds only the *name* of an environment secret.

## Connector contract

`search_jobs`, `get_job_details`, `get_profile`, `update_profile`, `prepare_application`,
`submit_application`, `get_application_status`, `get_capabilities`.
Every write returns an `OperationResult` with `status` (`succeeded`/`failed`/`needs_user_action`/`unknown`)
and `simulated`. Unsupported operations raise `ConnectorNotSupported`; the API returns 409.

## Job pipeline (Phase 2)

```
Refresh (button / due on page open / `python -m app.cli ingest`)
  └─ task_runs row (running, heartbeat)          services/tasks.py
      └─ for each connector whose search is permitted
          └─ search_jobs(filters from profile)   roles + keywords + locations
              └─ normalise + de-duplicate        services/normalize.py, services/ingestion.py
                   1. portal + external id   -> update
                   2. canonical URL          -> merge as extra source
                   3. same company key and title/description similarity -> merge (repost)
      └─ mark expired listings
      └─ rescore changed matches                 services/match_service.py
      └─ "N new jobs" notification (deduped per run)
```

**Matching** (`services/matching.py`, `services/taxonomy.py`) is deterministic and needs no key:

| Component | Default weight | Data used |
|---|---|---|
| Skills and experience | 35 | listing skills/description vs skills you entered (70%); your years vs required range (30%) |
| Role responsibilities | 25 | title vs preferred roles: shared words and seniority (lead/manager/senior...) |
| Domain experience | 15 | HRMS, payroll, ERP, fintech... found in the listing vs your summary/employment/skills |
| Location and work arrangement | 15 | remote/hybrid/onsite and preferred locations |
| Compensation fit | 10 | listing salary top vs your minimum (same currency only) |

* Missing data on either side scores a neutral 0.5 and is labelled **unknown**, never "match".
* Roles outside the QA/testing family are capped at 30.
* **Eligibility** (expired, excluded company, below minimum experience) is reported separately
  and does not change the score.
* Scores are recomputed automatically when the profile, weights, listing or date changes
  (an inputs fingerprint is stored with each match). Saved state and feedback are kept.
* The `MatchEngine` protocol allows an optional local-model engine later; the rule-based
  engine stays the default and the fallback.

## Free-tier resilience

* Cold start: frontend maps network errors and 502/503/504 to `BackendUnavailableError`
  and retries with backoff while showing "waking up".
* DB suspend: `pool_pre_ping` + `OperationalError` → 503 `db_unavailable` with `Retry-After`.
* Migrations run on every API start (idempotent).
* No always-on workers. Each refresh runs inside the request (or CLI call) that starts it and
  persists its state in `task_runs`. A run without a heartbeat for 10 minutes is marked
  `interrupted` ("safe to retry"). Only one refresh per user runs at a time (409 otherwise).
* The refresh schedule is checked when Job Discovery opens (`only_if_due`), because a sleeping
  free instance cannot run timers. Locally, Windows Task Scheduler can run `app.cli ingest`.

## Phase plan

1. ✅ Repo, auth, migrations, profile, dashboard, mock connector, tests
2. ✅ Job ingestion, normalisation, dedup, rule-based matching
3. Resumes, cover letters, DOCX/PDF, application tracking
4. Automation rules engine + approval workflow
5. Per-portal verification and permitted integrations
6. Deployment hardening, recovery drills
