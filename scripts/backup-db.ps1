# Back up PostgreSQL to backups\aja-<timestamp>.dump (custom format, compressed).
#   Local Compose DB:  powershell -File scripts\backup-db.ps1
#   Neon / any URL:    powershell -File scripts\backup-db.ps1 -DatabaseUrl "postgresql://...?...sslmode=require"
# Uses pg_dump from the postgres:17-alpine image, so nothing needs installing on Windows.
# Use the DIRECT (non "-pooler") Neon host for pg_dump.
param([string]$DatabaseUrl = "")
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
New-Item -ItemType Directory -Force "$root\backups" | Out-Null
$out = "$root\backups\aja-$(Get-Date -Format 'yyyyMMdd-HHmmss').dump"

if ($DatabaseUrl) {
    docker run --rm -v "${root}\backups:/backups" postgres:17-alpine `
        pg_dump --format=custom --no-owner --file "/backups/$(Split-Path -Leaf $out)" "$DatabaseUrl"
} else {
    Push-Location $root
    try {
        docker compose exec -T db sh -c 'pg_dump --format=custom --no-owner -U "$POSTGRES_USER" "$POSTGRES_DB" > /tmp/backup.dump'
        $id = docker compose ps -q db
        docker cp "${id}:/tmp/backup.dump" $out
        docker compose exec -T db rm -f /tmp/backup.dump
    } finally { Pop-Location }
}
if ($LASTEXITCODE -ne 0) { throw "Backup failed" }
Write-Host "Backup written: $out ($([math]::Round((Get-Item $out).Length / 1KB, 1)) KB)"
Write-Host "It contains personal data: store it somewhere private."
