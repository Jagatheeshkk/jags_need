# One-time local setup on Windows: Python venv, Node packages, Playwright browser, .env file.
# Usage (from the repository root):  powershell -ExecutionPolicy Bypass -File scripts\setup-local.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

Write-Host "== Backend (Python venv) =="
Push-Location "$root\services\api"
if (-not (Test-Path .venv)) { python -m venv .venv }
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
Pop-Location

Write-Host "== Frontend (npm) =="
Push-Location "$root\apps\web"
npm ci
npx playwright install chromium
Pop-Location

if (-not (Test-Path "$root\.env")) {
    Write-Host "== Creating .env with random secrets =="
    $secret = & "$root\services\api\.venv\Scripts\python.exe" -c "import secrets; print(secrets.token_urlsafe(48))"
    $dbpw = & "$root\services\api\.venv\Scripts\python.exe" -c "import secrets; print(secrets.token_urlsafe(24))"
    (Get-Content "$root\.env.example") `
        -replace '^SECRET_KEY=.*', "SECRET_KEY=$secret" `
        -replace '^POSTGRES_PASSWORD=.*', "POSTGRES_PASSWORD=$dbpw" |
        Set-Content -Encoding ascii "$root\.env"  # ascii: Windows PowerShell's utf8 adds a BOM
} else {
    Write-Host ".env already exists; left unchanged."
}
Write-Host "Done. Next: docker compose up -d --build"
