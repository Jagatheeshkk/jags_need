# Run every check that CI runs. Usage: powershell -ExecutionPolicy Bypass -File scripts\test-all.ps1
# Optional: -PostgresUrl postgresql://user:pass@localhost:5432/throwaway_db  (all tables in it are dropped)
param([string]$PostgresUrl = "")
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

function Step($name, [scriptblock]$block) {
    Write-Host "`n== $name ==" -ForegroundColor Cyan
    & $block
    if ($LASTEXITCODE -ne 0) { throw "$name failed (exit $LASTEXITCODE)" }
}

Push-Location "$root\services\api"
try {
    $py = ".\.venv\Scripts"
    Step "ruff" { & "$py\ruff.exe" check . }
    Step "ruff format" { & "$py\ruff.exe" format --check . }
    Step "mypy" { & "$py\mypy.exe" }
    Step "pytest (SQLite)" { & "$py\python.exe" -m pytest -q }
    if ($PostgresUrl) {
        $env:TEST_DATABASE_URL = $PostgresUrl
        try { Step "pytest (PostgreSQL)" { & "$py\python.exe" -m pytest -q } }
        finally { Remove-Item Env:TEST_DATABASE_URL }
    }
} finally { Pop-Location }

Push-Location "$root\apps\web"
try {
    Step "eslint" { npm run lint }
    Step "typecheck" { npm run typecheck }
    Step "vitest" { npm test }
    Step "playwright e2e" { npm run test:e2e }
} finally { Pop-Location }

Write-Host "`nAll checks passed." -ForegroundColor Green
