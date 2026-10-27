# Free-tier audit

**Verified:** 2026-10-27, from each provider's official pages (sources below).
**Rule:** no paid plan, trial, credit, or billing activation is required for any core feature.

Free plans change. Nothing here guarantees the system stays free forever. Re-check each
source before deploying, and at least every few months. The in-app **Free-Tier Usage & Health**
page and `python -m app.cli readiness` flag known risky providers.

## Services used

| Service | Role | Free-plan evidence | Limits that matter here | Risk / fallback |
|---|---|---|---|---|
| **Vercel Hobby** | Next.js frontend + `/api` proxy | [vercel.com/docs/plans/hobby](https://vercel.com/docs/plans/hobby): "The Hobby plan is free". No billing cycle on Hobby; a feature over its limit pauses until 30 days pass. | **Personal, non-commercial use only** (fair-use guidelines). Per month: 100 GB Fast Data Transfer, 10 GB Fast Origin Transfer, 1M function invocations, 4 active CPU-hours. 100 deployments/day. | Fine for a personal job-search tool. Proxy timeout for external rewrites is not documented on that page: a Render cold start can produce a 502/504, which the frontend treats as "sleeping" and retries. Fallback: run the web app locally (`npm run dev`) or in Docker. |
| **Render Free web service** | FastAPI backend | [render.com/docs/free](https://render.com/docs/free) | Spins down after **15 min** without traffic; restart "takes about one minute". **750 free instance hours** per workspace per month, then services are suspended until next month. Bandwidth and build-minute overages are billed only if a payment method exists; otherwise the service is suspended / builds disabled. RAM/CPU not stated on that page. | Do **not** add a payment method if you want a hard $0 ceiling. Cold starts are expected; the UI shows "waking up" and retries. No continuous background workers: use manual refresh. Fallback: run the API on your Windows laptop (Docker Compose). |
| **Render Free Postgres** | *Rejected* | Same page: free databases **expire 30 days after creation** (then 14-day grace, then deletion). | — | **Not used.** Short expiry violates the "no expiring database" requirement. The readiness check fails loudly if `DATABASE_URL` points at Render. |
| **Neon Free** | PostgreSQL (production) | [neon.com/pricing](https://neon.com/pricing): $0/month, no credit card, permanent plan. | **1 GB storage per project** (20 GB total), **100 CU-hours per project per month**, compute **suspends after 5 min idle** (cannot be disabled), 5 GB egress, 6-hour history window. Over a limit: compute suspended / writes blocked until next period. Pricing page states limits do not delete data. | Cold DB resume adds latency to the first query; the API uses `pool_pre_ping` and returns a 503 "waking up" that the UI retries. Keep regular `pg_dump` backups (`scripts/backup-db.ps1`). Storage: resumes are stored in Postgres, so keep files small (upload validation arrives in Phase 3). |
| **Supabase Free** | *Not used* (considered for storage) | [supabase.com/pricing](https://supabase.com/pricing) | 500 MB DB, 1 GB file storage, 5 GB egress, **projects pause after 1 week of inactivity**, 2 active projects. | Rejected as a dependency: weekly pausing makes it unreliable for a low-traffic personal app. Files go in PostgreSQL instead. Readiness check warns if `DATABASE_URL` points at Supabase. |
| **GitHub Free + Actions** | Source control, CI | [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions) | Free for **public** repos on standard runners. Private repos: **2,000 min/month**, 500 MB artifact storage. Without a payment method, usage is blocked at the quota (no charge). | CI run ≈ 10 runner-minutes. Concurrency cancels superseded runs. If private and near quota, run `scripts\test-all.ps1` locally instead. |
| **Docker Desktop** | Local development | Not part of the deployment. | Docker Desktop's licence is free for personal use; check its terms if your situation differs. | Fallback: run backend (venv) and frontend (npm) directly; only Postgres needs a container or a Neon dev branch. |

## Implemented locally instead of using a service

| Feature | Implementation | Cost |
|---|---|---|
| AI / matching | Rule-based engine (Phase 2). Optional local **Ollama**. `AI_PROVIDER` only accepts `rule_based` or `ollama`; a paid provider cannot be configured. | $0 |
| File storage | PostgreSQL `resumes.content` with SHA-256 hashes | Counts against Neon storage |
| Background jobs | `task_runs` table: persistent state, heartbeats, interrupted-run recovery, idempotency keys. Runs inside a request or the `app.cli ingest` command; refresh-when-due on page open | $0 |
| Notifications | In-app + browser Notification API + downloadable Markdown digest (`/api/jobs/digest`). `EMAIL_PROVIDER` only accepts `none`. | $0 |
| Secrets | Environment variables in Render / Vercel dashboards | $0 |
| Backups | `pg_dump` / `pg_restore` via the `postgres:17-alpine` image | $0 |
| Domain | Free `*.vercel.app` and `*.onrender.com` subdomains | $0 |

## Email

No email provider is configured. No option was verified as free without a mandatory upgrade path
for this use, so email stays disabled. Use in-app notifications, browser notifications, and the
downloadable digest.

## Job portals (Phase 5, not verified yet)

No portal integration is active. Naukri, LinkedIn, Indeed, Instahyre and Cutshort are registered
as **unverified** connectors that refuse every operation. Before any real integration, Phase 5
must record for each portal: official API availability, terms of service on automated access,
and permitted operations. Where automation is not permitted, the app provides manual workflows
only. No scraping, CAPTCHA/MFA bypass, or anti-bot evasion will be implemented.

## Re-verification checklist

1. Open each source URL above and compare limits.
2. Confirm no credit card / payment method is required to keep the service running.
3. Confirm the free plan still permits a personal application storing your own data.
4. Update this file and the `LIMITS` table in `apps/web/app/(dashboard)/health/page.tsx`.
