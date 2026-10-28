# Run the API with Render Free's limits (512 MB RAM, 0.1 CPU) against a throwaway database,
# measure cold start and peak memory under a realistic workload, then clean up.
# Needs the Compose stack running (for its PostgreSQL) and the API image built:
#   docker compose up -d --build
#   powershell -ExecutionPolicy Bypass -File scripts\resource-check.ps1
param([string]$Memory = "512m", [string]$Cpus = "0.1", [int]$Port = 8099)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
$name = "aja-resource-check"
$db = "aja_resource_check"
try {
    $pw = (Select-String -Path .env -Pattern '^POSTGRES_PASSWORD=(.*)$').Matches[0].Groups[1].Value
    $network = (docker inspect (docker compose ps -q db) --format '{{range $k, $v := .NetworkSettings.Networks}}{{$k}}{{end}}')
    $image = docker inspect (docker compose ps -q api) --format '{{.Config.Image}}'
    if (-not $image) { throw "API container not found: run 'docker compose up -d --build' first" }
    docker compose exec -T db sh -c "dropdb -U aja --if-exists $db 2>/dev/null; createdb -U aja $db" | Out-Null
    docker rm -f $name 2>$null | Out-Null

    $secret = & "services\api\.venv\Scripts\python.exe" -c "import secrets; print(secrets.token_urlsafe(48))"
    $sw = [Diagnostics.Stopwatch]::StartNew()
    docker run -d --name $name --network $network --memory $Memory --memory-swap $Memory --cpus $Cpus `
        -p "127.0.0.1:${Port}:8000" -e ENVIRONMENT=development -e SECRET_KEY=$secret `
        -e "DATABASE_URL=postgresql://aja:${pw}@db:5432/$db" $image | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "docker run failed" }

    # Cold start: process start, migrations, seed, first successful health check.
    $healthy = $false
    while ($sw.Elapsed.TotalSeconds -lt 300) {
        try {
            $r = Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$Port/api/health" -TimeoutSec 5
            if ($r.StatusCode -eq 200) { $healthy = $true; break }
        } catch { Start-Sleep -Milliseconds 500 }
    }
    $cold = [math]::Round($sw.Elapsed.TotalSeconds, 1)
    if (-not $healthy) { throw "API did not become healthy within 300 s" }
    Write-Host "Cold start (container start -> healthy, with migrations): $cold s"

    # Sample memory in the background while the workload runs.
    $sampler = Start-Job -ScriptBlock {
        param($n)
        $peak = 0.0
        while ($true) {
            $line = docker stats $n --no-stream --format "{{.MemUsage}}" 2>$null
            if ($line -match '^([\d.]+)(MiB|GiB)') {
                $mb = [double]$Matches[1]; if ($Matches[2] -eq "GiB") { $mb *= 1024 }
                if ($mb -gt $peak) { $peak = $mb; Set-Content -Path "$env:TEMP\aja-peak.txt" -Value $peak }
            }
            Start-Sleep -Milliseconds 700
        }
    } -ArgumentList $name
    $sw.Restart()
    & "services\api\.venv\Scripts\python.exe" scripts\workload.py "http://127.0.0.1:$Port"
    if ($LASTEXITCODE -ne 0) { throw "Workload failed" }
    $workload = [math]::Round($sw.Elapsed.TotalSeconds, 1)
    Stop-Job $sampler; Remove-Job $sampler
    $peak = [math]::Round([double](Get-Content "$env:TEMP\aja-peak.txt"), 0)
    $oom = docker inspect $name --format '{{.State.OOMKilled}}'
    $restarts = docker inspect $name --format '{{.RestartCount}}'
    Write-Host "Workload: $workload s; peak memory: $peak MB of $Memory; OOM killed: $oom; restarts: $restarts"
} finally {
    docker rm -f $name 2>$null | Out-Null
    docker compose exec -T db sh -c "dropdb -U aja --if-exists $db 2>/dev/null" | Out-Null
    Remove-Item "$env:TEMP\aja-peak.txt" -ErrorAction SilentlyContinue
    Pop-Location
}
