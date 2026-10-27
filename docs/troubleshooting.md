# Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| UI says "The backend is waking up" for ~1 min | Render Free spun the API down after 15 min idle | Wait; the UI retries automatically. Expected on the free plan. |
| `{"code":"db_unavailable"}` / HTTP 503 | Neon compute suspended or DB container stopped | Retry after a few seconds. Locally: `docker compose ps`, `docker compose start db`. |
| `Bind for 0.0.0.0:5432 failed: port is already allocated` | Another Postgres/app uses the port | Set `POSTGRES_HOST_PORT`, `API_HOST_PORT` or `WEB_HOST_PORT` in `.env` (e.g. 5433/8001/3001), then `docker compose up -d`. |
| `CSRF token missing or invalid` (403) | Calling the API without the header, or cookies blocked | Use the web UI, or first `GET /api/auth/csrf` and send the value as `X-CSRF-Token`. |
| `Too many failed attempts` (429) | 5 failed logins in 15 min | Wait for `Retry-After`, or restart the API (limiter is in memory). |
| Forgot the owner password | No e-mail reset (no free e-mail provider) | Export first if possible. Then reset via DB: run `services/api/.venv/Scripts/python.exe -c "from app.security.passwords import hash_password; print(hash_password('NEW-PASSPHRASE'))"` and `UPDATE users SET password_hash='<hash>', session_version=session_version+1;` with psql. |
| `SettingsError ... cors_origins` | Old build | Rebuild: `docker compose up -d --build`. `CORS_ORIGINS` is comma-separated. |
| `tomllib.TOMLDecodeError: Invalid statement (at line 1, column 1)` | File saved with a UTF-8 BOM (Windows PowerShell 5.1 `Set-Content -Encoding utf8`) | Re-save without BOM (VS Code: "UTF-8"), or write with `-Encoding ascii`. |
| Frontend calls the wrong backend | `BACKEND_URL` is baked in at build time | Set it before `npm run build` / in Vercel env vars, then redeploy. |
| Production API refuses to start | Safety checks: default `SECRET_KEY`, missing `BOOTSTRAP_TOKEN`, or SQLite | Set the variables listed in `infra/env.production.example`. |
| Neon: `prepared statement ... does not exist` | Pooled endpoint + prepared statements | Already disabled (`prepare_threshold=None`). Make sure you deployed the current code. |
| Render services suspended mid-month | 750 free instance hours used | Wait for the next month or run the API locally with Docker Compose. |
| "A refresh is already running" (409) | Another refresh is in progress | Wait. If the server slept mid-run, the run is marked *interrupted* after 10 minutes and a new refresh is allowed. |
| Refresh finds no jobs | Searches use your preferred roles, keywords and locations; only the mock connector is active | Add preferred roles/locations in My Profile, or widen them. Real portals arrive with Phase 5. |
| A job scores lower than expected | Missing profile data counts as neutral (0.5), not a match | Open the job and read "Why this score"; fill the fields shown as *unknown*. |
| "The file content is PDF, but its name ends in .docx" | Extension does not match the real file type | Save the file in its real format, or rename it correctly. |
| "Password-protected PDFs cannot be read" | Encrypted PDF | Export an unprotected copy, or upload the DOCX. |
| Resume suggestions miss fields | Rule-based reading of the text | Fill the missing fields in My Profile; scanned (image-only) PDFs have no text to read. |
| "Add your name to the profile before generating a resume" (409) | Profile has no full name | Set it in My Profile. |
| "Confirm that you submitted this application…" (400) | Marking a draft as submitted without confirmation | Tick "I submitted this application on the portal myself". |
| Playwright: `Executable doesn't exist` | Browser not installed | `cd apps/web; npx playwright install chromium` |
