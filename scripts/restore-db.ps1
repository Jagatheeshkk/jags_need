# Restore a backup created by backup-db.ps1. REPLACES the existing tables in the target database.
#   Local Compose DB:  powershell -File scripts\restore-db.ps1 -File backups\aja-20260101-120000.dump
#   Neon / any URL:    powershell -File scripts\restore-db.ps1 -File backups\x.dump -DatabaseUrl "postgresql://..."
param(
    [Parameter(Mandatory = $true)][string]$File,
    [string]$DatabaseUrl = "",
    [switch]$Force  # skip the typed confirmation (for scripted recovery drills)
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$full = (Resolve-Path $File).Path
if (-not $Force) {
    $answer = Read-Host "This replaces data in the target database. Type RESTORE to continue"
    if ($answer -ne "RESTORE") { Write-Host "Cancelled."; exit 1 }
}

if ($DatabaseUrl) {
    $dir = Split-Path -Parent $full
    docker run --rm -v "${dir}:/backups" postgres:17-alpine `
        pg_restore --clean --if-exists --no-owner --dbname "$DatabaseUrl" "/backups/$(Split-Path -Leaf $full)"
} else {
    Push-Location $root
    try {
        $id = docker compose ps -q db
        docker cp $full "${id}:/tmp/restore.dump"
        docker compose exec -T db sh -c 'pg_restore --clean --if-exists --no-owner -U "$POSTGRES_USER" -d "$POSTGRES_DB" /tmp/restore.dump; rm -f /tmp/restore.dump'
    } finally { Pop-Location }
}
if ($LASTEXITCODE -ne 0) { throw "Restore reported errors (see above)" }
Write-Host "Restore complete. Restart the API so it re-runs migrations: docker compose restart api"
