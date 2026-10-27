# AI Job Agent

A personal job-search and profile-management assistant that runs entirely on free tiers or
your own machine. No paid APIs, hosting, storage, email, or browser-automation services.

**Status: Phases 1–3 complete.**
* Phase 1: authentication, database + migrations, candidate profile, dashboard, settings,
  mock portal connector with synthetic data.
* Phase 2: job collection, normalisation, duplicate detection, freshness/expiry, rule-based
  0–100 match scores with explanations and separate eligibility checks, filters, saved jobs,
  match feedback, and a downloadable daily digest.
* Phase 3: resume upload (PDF/DOCX) with reviewed field extraction, master and job-tailored
  resume versions with hashes, cover letters, screening-answer drafts, DOCX/PDF export, and an
  application tracker with status history, follow-ups and duplicate prevention.
Real portal integrations are **not** active: every real portal is shown as *Unsupported* until
its permitted integration options are verified (Phase 5).

## Stack

| Layer | Technology | Hosting (free) |
|---|---|---|
| Web | Next.js 16, React 19, TypeScript, Tailwind CSS 4 | Vercel Hobby |
| API | Python, FastAPI, Pydantic, SQLAlchemy 2, Alembic | Render Free |
| DB | PostgreSQL 17 | Neon Free |
| AI | Rule-based engine (default, no key); optional local Ollama | — |
| Tests | Pytest, Ruff, MyPy, ESLint, Vitest, Playwright | GitHub Actions |

## Quick start (Windows PowerShell)

```powershell
git clone <your-repo-url> ai-job-agent
cd ai-job-agent
powershell -ExecutionPolicy Bypass -File scripts\setup-local.ps1
docker compose up -d --build
start http://localhost:3000
```

Create the owner account on first visit. Optional synthetic sample jobs:

```powershell
docker compose exec api python -m app.cli seed-sample-jobs
```

Run every check:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\test-all.ps1
```

## Repository layout

```
apps/web/            Next.js dashboard (app/, components/, lib/, tests/unit, tests/e2e)
services/api/        FastAPI service (app/, alembic/, tests/)
infra/               Production env template
scripts/             PowerShell: setup, tests, backup, restore
docs/                architecture, deployment, security, free-tier-audit, troubleshooting
.github/workflows/   CI
compose.yaml         Local stack (Postgres + API + web)
```

## Docs

* [Architecture](docs/architecture.md)
* [Deployment (all free)](docs/deployment.md)
* [Security](docs/security.md)
* [Free-tier audit](docs/free-tier-audit.md)
* [Troubleshooting](docs/troubleshooting.md)

## Principles

* Never claims a portal is connected or an application submitted unless it really happened.
  Mock data is flagged `is_synthetic`; simulated submissions are flagged `simulated`.
* Never invents profile facts.
* No CAPTCHA/MFA/anti-bot bypass. No portal passwords stored.
* Works with AI disabled, portals unavailable, and the backend asleep.
