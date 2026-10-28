# Recovery drill: prove that a backup can actually be restored.
#  1. pg_dump the live database (custom format, like backup-db.ps1)
#  2. restore it into a scratch database
#  3. compare migration version and row counts of every table
#  4. drop the scratch database
# Nothing in the live database is changed.
#   Local Compose DB: powershell -ExecutionPolicy Bypass -File scripts\recovery-drill.ps1
#   Neon (direct, non-pooler URL; restores into a local scratch DB):
#     powershell -File scripts\recovery-drill.ps1 -SourceUrl "postgresql://...neon.tech/neondb?sslmode=require"
param(
    [string]$SourceUrl = "",
    [switch]$SimulateCorruption  # deletes a row from the restored copy to prove the check catches it
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
$scratch = "aja_recovery_drill"
$dump = "/tmp/recovery-drill.dump"
try {
    $sw = [Diagnostics.Stopwatch]::StartNew()
    if ($SourceUrl) {
        docker compose exec -T db sh -c "pg_dump --format=custom --no-owner --file $dump '$SourceUrl'"
    } else {
        docker compose exec -T db sh -c 'pg_dump --format=custom --no-owner -U "$POSTGRES_USER" -f /tmp/recovery-drill.dump "$POSTGRES_DB"'
    }
    if ($LASTEXITCODE -ne 0) { throw "Backup failed" }
    $size = docker compose exec -T db sh -c "stat -c %s $dump"
    Write-Host "1. Backup: $([math]::Round([int]$size / 1KB, 1)) KB in $([math]::Round($sw.Elapsed.TotalSeconds, 1)) s"

    $sw.Restart()
    docker compose exec -T db sh -c "dropdb -U aja --if-exists $scratch 2>/dev/null; createdb -U aja $scratch && pg_restore --no-owner -U aja -d $scratch $dump"
    if ($LASTEXITCODE -ne 0) { throw "Restore reported errors" }
    Write-Host "2. Restore into '$scratch': $([math]::Round($sw.Elapsed.TotalSeconds, 1)) s"

    $source = if ($SourceUrl) { "'$SourceUrl'" } else { '"$POSTGRES_DB"' }
    function Query($database, $sql) {
        $out = docker compose exec -T db sh -c "psql -U aja -tA -d $database -c '$sql'"
        if ($LASTEXITCODE -ne 0) { throw "Query failed on ${database}: $sql" }
        return ($out | Out-String).Trim()
    }
    $tables = (Query $scratch "select tablename from pg_tables where schemaname = current_schema() order by 1") -split "`r?`n" |
        Where-Object { $_ }
    if ($tables.Count -lt 10) { throw "Only $($tables.Count) tables restored; expected the full schema" }
    if ($SimulateCorruption) { Query $scratch "delete from jobs where id = (select id from jobs limit 1)" | Out-Null }
    $rows = 0
    foreach ($t in $tables) {
        # Plain identifiers only, so no quoting is needed across PowerShell -> sh -> psql.
        if ($t -notmatch '^[a-z_][a-z0-9_]*$') { throw "Unexpected table name: $t" }
        $a = [int](Query $source "select count(*) from $t")
        $b = [int](Query $scratch "select count(*) from $t")
        if ($a -ne $b) { throw "Row count differs for ${t}: source $a, restored $b" }
        $rows += $b
    }
    if ($rows -eq 0) { throw "No rows found: nothing was verified" }
    $srcVer = Query $source "select version_num from alembic_version"
    $dstVer = Query $scratch "select version_num from alembic_version"
    if ($srcVer -ne $dstVer) { throw "Migration version differs: $srcVer vs $dstVer" }
    Write-Host "3. Verified: $($tables.Count) tables, $rows rows, identical counts, migration version $dstVer"
    Write-Host "Recovery drill PASSED"
} finally {
    docker compose exec -T db sh -c "dropdb -U aja --if-exists $scratch 2>/dev/null; rm -f $dump" | Out-Null
    Write-Host "4. Scratch database and dump removed"
    Pop-Location
}
