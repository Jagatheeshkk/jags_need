# Read-only smoke test of a deployment, through the web app's /api proxy.
# It never signs in or creates anything, so it is safe to run against production.
#   powershell -ExecutionPolicy Bypass -File scripts\smoke-test.ps1 -WebUrl https://<project>.vercel.app
#   (local: -WebUrl http://localhost:3000)
param(
    [Parameter(Mandatory = $true)][string]$WebUrl,
    [int]$WakeTimeoutSeconds = 180
)
$ErrorActionPreference = "Stop"
$base = $WebUrl.TrimEnd("/")
$prod = $base.StartsWith("https://")
$results = New-Object System.Collections.Generic.List[object]

function Add-Result($name, $status, $detail) {
    $results.Add([pscustomobject]@{ Check = $name; Status = $status; Detail = $detail })
}

function Get-Response($path, $method = "GET", $headers = @{}) {
    try {
        return Invoke-WebRequest -UseBasicParsing -Uri "$base$path" -Method $method -Headers $headers -TimeoutSec 60
    } catch [System.Net.WebException] {
        if ($_.Exception.Response) { return $_.Exception.Response }
        throw
    }
}

function Status-Code($r) { if ($r -is [System.Net.HttpWebResponse]) { [int]$r.StatusCode } else { [int]$r.StatusCode } }
function Header($r, $name) { if ($r -is [System.Net.HttpWebResponse]) { $r.Headers[$name] } else { $r.Headers[$name] } }

# 1. Wake the backend (free instances sleep) and time it.
$sw = [Diagnostics.Stopwatch]::StartNew()
$health = $null
while ($sw.Elapsed.TotalSeconds -lt $WakeTimeoutSeconds) {
    try {
        $r = Invoke-WebRequest -UseBasicParsing -Uri "$base/api/health" -TimeoutSec 60
        if ($r.StatusCode -eq 200) { $health = $r; break }
    } catch { Start-Sleep -Seconds 3 }
}
$wake = [math]::Round($sw.Elapsed.TotalSeconds, 1)
if ($health) {
    $body = $health.Content | ConvertFrom-Json
    if ($body.database -eq "ok") { Add-Result "API + database reachable" "PASS" "healthy after $wake s" }
    else { Add-Result "API + database reachable" "FAIL" "database: $($body.database)" }
} else {
    Add-Result "API + database reachable" "FAIL" "no healthy response within $WakeTimeoutSeconds s"
}

# 2. Web app serves the sign-in page.
$login = Get-Response "/login"
if ((Status-Code $login) -eq 200) { Add-Result "Web app" "PASS" "/login returns 200" }
else { Add-Result "Web app" "FAIL" "/login returned $(Status-Code $login)" }

# 3. Security headers on the web app and the API.
foreach ($h in @("X-Frame-Options", "X-Content-Type-Options", "Referrer-Policy")) {
    $v = Header $login $h
    if ($v) { Add-Result "Web header $h" "PASS" $v } else { Add-Result "Web header $h" "FAIL" "missing" }
}
if ($health) {
    foreach ($h in @("Content-Security-Policy", "Cache-Control")) {
        $v = Header $health $h
        if ($v) { Add-Result "API header $h" "PASS" $v } else { Add-Result "API header $h" "FAIL" "missing" }
    }
}

# 4. Protected endpoints refuse anonymous access; state changes need CSRF.
foreach ($p in @("/api/auth/me", "/api/profile", "/api/settings/readiness", "/api/data/export")) {
    $c = Status-Code (Get-Response $p)
    if ($c -eq 401) { Add-Result "Auth required $p" "PASS" "401" } else { Add-Result "Auth required $p" "FAIL" "got $c" }
}
$csrf = Status-Code (Get-Response "/api/profile" "PATCH" @{ "Content-Type" = "application/json" })
if ($csrf -eq 403) { Add-Result "CSRF enforced" "PASS" "PATCH without token: 403" }
else { Add-Result "CSRF enforced" "FAIL" "PATCH without token: $csrf" }

# 5. Production-only expectations.
$docs = Status-Code (Get-Response "/api/docs")
$cookie = Header (Get-Response "/api/auth/csrf") "Set-Cookie"
if ($prod) {
    if ($docs -eq 404) { Add-Result "API docs hidden" "PASS" "404" } else { Add-Result "API docs hidden" "FAIL" "got $docs" }
    if ($cookie -match "(?i);\s*secure") { Add-Result "Secure cookies" "PASS" "Secure flag set" }
    else { Add-Result "Secure cookies" "FAIL" "Secure flag missing" }
} else {
    Add-Result "HTTPS" "WARN" "not https: development deployment assumed (docs $docs, cookie Secure flag not expected)"
}
$setup = (Get-Response "/api/auth/setup-status").Content | ConvertFrom-Json
if ($setup.setup_required -and -not $setup.bootstrap_token_required -and $prod) {
    Add-Result "Owner setup protected" "FAIL" "setup open without BOOTSTRAP_TOKEN"
} elseif ($setup.setup_required) {
    Add-Result "Owner setup" "WARN" "no owner yet: open $base/login and create it (token required: $($setup.bootstrap_token_required))"
} else {
    Add-Result "Owner setup" "PASS" "owner exists; setup closed"
}

$results | Format-Table -AutoSize | Out-String -Width 200 | Write-Host
$failed = @($results | Where-Object Status -eq "FAIL").Count
if ($failed) { Write-Host "$failed check(s) FAILED" -ForegroundColor Red; exit 1 }
Write-Host "Smoke test passed" -ForegroundColor Green
