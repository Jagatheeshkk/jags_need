# Security

## Authentication

* Single owner account. `POST /api/auth/setup` works only while no user exists, and in
  production also requires `BOOTSTRAP_TOKEN` (constant-time compare). Otherwise whoever reaches
  a fresh deployment first could claim it.
* Passwords: Argon2id (`argon2-cffi`), minimum 12 characters, transparent rehash on login.
  Unknown e-mail and wrong password return the same error and take the same time.
* Sessions: signed, timestamped cookie (`itsdangerous`) holding only user id + session version.
  `HttpOnly`, `SameSite=Lax`, `Secure` in production, 12 h max age. Logout-all and password
  change bump `users.session_version`, revoking every earlier cookie. Nothing session-related is
  stored in the database.
* Login rate limit: 5 failures per 15 min per e-mail → 429 with `Retry-After`. In-memory
  (single free instance); a restart resets it, which never locks the owner out.

## Request protection

* CSRF: double-submit token (`aja_csrf` cookie + `X-CSRF-Token` header) on every
  POST/PUT/PATCH/DELETE, enforced globally.
* CORS: explicit origin list only (`CORS_ORIGINS`); normal traffic is same-origin via the proxy.
* Validation: Pydantic models with `extra="forbid"`, length caps, ranges, https-only links.
* Headers: `nosniff`, `X-Frame-Options: DENY`, restrictive CSP on API responses,
  `Cache-Control: no-store`, `Referrer-Policy`.
* API docs (`/api/docs`) are disabled in production.
* SSRF: the backend makes no requests to user-supplied URLs. The only outbound call is the
  optional Ollama readiness probe, and a non-local `OLLAMA_BASE_URL` is flagged.
* Path traversal: no filesystem paths are built from user input (files live in Postgres).
  Uploads are validated as described under "Uploaded files".

## Uploaded files

* PDF/DOCX only; size limit enforced while reading (never more than limit + 1 byte is read).
* Content sniffing must agree with the file extension; anything else is refused.
* DOCX: entry count and total uncompressed size are checked before parsing (zip-bomb guard).
* PDF: encrypted files refused; page count limited.
* No upload is ever written to disk or executed; bytes live in PostgreSQL behind authentication.
* Download filenames are sanitised before going into `Content-Disposition`.
* Extracted text is shown as plain text and parsed into *suggestions* only.

## Generated documents

* Built only from profile data; `verify_resume_facts` refuses output containing skills,
  employers or certifications that are not in the profile.
* PDF rendering escapes all text, so markup in profile or job text cannot alter the document.
* Legal declarations, salary commitments, sensitive attestations and unknown questions are
  never answered automatically.

## Data handling

* Audit log records field *names* changed, never values; IPs stored as keyed hashes.
* `GET /api/data/export` returns all personal data as JSON (no password hash).
* `POST /api/data/delete` needs the password and the phrase `DELETE MY DATA`; it removes the
  user and everything linked (FK cascades) including the audit trail.
* Backups made with `scripts/backup-db.ps1` contain personal data; `backups/` is git-ignored.

## Secrets

* Only environment variables (`.env` locally, Render/Vercel dashboards in production).
  `.env` is git-ignored; `.env.example` holds placeholders only.
* Production refuses to start with the default `SECRET_KEY`, without `BOOTSTRAP_TOKEN`, or on SQLite.
* No server secret is referenced from frontend code; there are no `NEXT_PUBLIC_` secrets.

## Untrusted content

Job descriptions and portal content are treated as data. They are never executed or
interpreted as instructions. When an optional local model is added, prompts will keep job text
in a clearly delimited data section, and model output will never trigger submissions directly:
every automated action still goes through the rule engine and approval checks.

## Portal automation

No CAPTCHA, MFA or anti-bot bypass, ever. No portal passwords stored. Real portal operations
stay disabled until Phase 5 verifies what each portal permits.
