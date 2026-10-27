# Deployment (all free tier)

Target: **Vercel Hobby** (web) → **Render Free** (API) → **Neon Free** (PostgreSQL).
Limits and sources: [free-tier-audit.md](free-tier-audit.md). Never add a payment method to
Render or Vercel if you want a hard $0 ceiling: without one, overages suspend instead of bill.

All commands are Windows PowerShell, run from the repository root unless noted.

## 0. Local development

```powershell
# Prerequisites: Python 3.12+, Node 20.9+, Docker Desktop, Git
powershell -ExecutionPolicy Bypass -File scripts\setup-local.ps1   # venv, npm ci, Playwright, .env with random secrets
docker compose up -d --build                                       # db + api + web
docker compose ps                                                  # all should be healthy/up
start http://localhost:3000                                        # create the owner account
```

If ports are taken, set `POSTGRES_HOST_PORT`, `API_HOST_PORT`, `WEB_HOST_PORT` in `.env`.

Without Docker for the app (Postgres still in Docker, or a Neon dev branch):

```powershell
docker compose up -d db
cd services\api
$env:DATABASE_URL = "postgresql://aja:<POSTGRES_PASSWORD from .env>@localhost:5432/aja"
.\.venv\Scripts\python.exe -m app.cli migrate
.\.venv\Scripts\python.exe -m app.cli seed
.\.venv\Scripts\python.exe -m app.cli seed-sample-jobs     # optional: 10 synthetic jobs
.\.venv\Scripts\uvicorn.exe app.main:app --reload --port 8000
# second terminal
cd apps\web
$env:BACKEND_URL = "http://127.0.0.1:8000"
npm run dev
```

### Migrations

```powershell
cd services\api
.\.venv\Scripts\alembic.exe upgrade head                    # apply (DATABASE_URL from env)
.\.venv\Scripts\alembic.exe revision --autogenerate -m "describe change"   # after model changes
.\.venv\Scripts\alembic.exe check                           # models and migrations agree
```

The API container runs `migrate` on every start; it is idempotent.

### Tests

```powershell
powershell -ExecutionPolicy Bypass -File scripts\test-all.ps1
# also against Postgres (uses a throwaway DB; all its tables are dropped):
docker compose exec db createdb -U aja aja_test
powershell -ExecutionPolicy Bypass -File scripts\test-all.ps1 -PostgresUrl "postgresql://aja:<pw>@localhost:5432/aja_test"
```

### Frontend production build

```powershell
cd apps\web
$env:BACKEND_URL = "http://127.0.0.1:8000"; $env:NEXT_TELEMETRY_DISABLED = "1"
npm run build
npx next start --port 3000
```

## 1. Database: Neon Free

1. Sign up at neon.com (no card). Create a project, PostgreSQL 17, region nearest Render's.
2. Copy two connection strings from **Connect**:
   * **Pooled** (host contains `-pooler`) → the API's `DATABASE_URL`.
   * **Direct** (no `-pooler`) → for `pg_dump`/`pg_restore` and manual migrations.
3. Both must end with `?sslmode=require`.

## 2. Backend: Render Free web service

1. Push the repository to GitHub (public or private).
2. Render → **New → Web Service** → connect the repo. Instance type **Free**.
3. Settings:
   * Root Directory: `services/api`
   * Runtime: Python 3 (set env `PYTHON_VERSION` to a 3.13 release if the default is older)
   * Build Command: `pip install .`
   * Start Command: `python -m app.cli migrate && python -m app.cli seed && uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   * Health Check Path: `/api/health`
   * (Alternatively choose the Docker runtime; `services/api/Dockerfile` honours `$PORT`.)
4. Environment variables (see `infra/env.production.example`):
   `ENVIRONMENT=production`, `DATABASE_URL` (Neon pooled), `SECRET_KEY`, `BOOTSTRAP_TOKEN`,
   `CORS_ORIGINS=https://<project>.vercel.app`, `AI_PROVIDER=rule_based`.
   Generate secrets: `python -c "import secrets; print(secrets.token_urlsafe(48))"`
5. Deploy. Check `https://<service>.onrender.com/api/health` → `{"status":"ok","database":"ok"}`.

## 3. Frontend: Vercel Hobby

1. Vercel → **Add New → Project** → import the repo.
2. Root Directory: `apps/web`. Framework preset: Next.js.
3. Environment variables: `BACKEND_URL=https://<service>.onrender.com`, `NEXT_TELEMETRY_DISABLED=1`.
4. Deploy. Open `https://<project>.vercel.app`, enter the `BOOTSTRAP_TOKEN` once to create the owner.
5. Optional CLI instead of the dashboard:
   ```powershell
   cd apps\web
   npx vercel login
   npx vercel --prod
   ```

## 4. After deploying

* **Free-Tier Usage & Health** page: readiness must show `Paid dependencies: none`, and no `fail`.
* First request after idle can take ~1 minute (Render). That is expected.
* Optionally remove `BOOTSTRAP_TOKEN` access by rotating it after setup (setup is closed once an owner exists anyway).

## 5. Backup and restore

```powershell
# Local Compose DB
powershell -File scripts\backup-db.ps1
powershell -File scripts\restore-db.ps1 -File backups\aja-YYYYMMDD-HHMMSS.dump

# Neon (use the DIRECT host)
powershell -File scripts\backup-db.ps1 -DatabaseUrl "postgresql://USER:PW@ep-xxx.REGION.aws.neon.tech/neondb?sslmode=require"
powershell -File scripts\restore-db.ps1 -File backups\aja-....dump -DatabaseUrl "postgresql://...direct...?sslmode=require"
```

Also download the JSON export from **Settings → Export your data** regularly.
Recovery drill verified locally on 2026-10-27: backup → change data → restore → change reverted.

## 6. Recovery scenarios

| Event | What happens | Action |
|---|---|---|
| Render instance asleep | First request ~1 min; UI shows "waking up" and retries | None |
| Neon compute suspended | First query slower; transient 503 retried by UI | None |
| Render hours exhausted | API suspended until next month | Run API locally (`docker compose up -d`) pointed at Neon |
| Neon storage full | Writes blocked | Export, prune data, or move to another free Postgres; restore from dump |
| Provider removes free plan | Service stops | Restore latest dump into another free Postgres; redeploy API locally or elsewhere |
