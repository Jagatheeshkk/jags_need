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
| `workers/` | Database-backed tasks (Phase 2) |

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

## Free-tier resilience

* Cold start: frontend maps network errors and 502/503/504 to `BackendUnavailableError`
  and retries with backoff while showing "waking up".
* DB suspend: `pool_pre_ping` + `OperationalError` → 503 `db_unavailable` with `Retry-After`.
* Migrations run on every API start (idempotent).
* No always-on workers are assumed; scheduled work will be manual-refresh first (Phase 2).

## Phase plan

1. ✅ Repo, auth, migrations, profile, dashboard, mock connector, tests (this milestone)
2. Job ingestion, normalisation, dedup, rule-based matching
3. Resumes, cover letters, DOCX/PDF, application tracking
4. Automation rules engine + approval workflow
5. Per-portal verification and permitted integrations
6. Deployment hardening, recovery drills
