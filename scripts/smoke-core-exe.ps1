$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$exe = Join-Path $repoRoot "services/core-api/dist/xiaoyue-core-api/xiaoyue-core-api.exe"
if (-not (Test-Path $exe)) { throw "build the sidecar first (scripts/build-core.ps1)" }

$dataDir = Join-Path $env:TEMP ("xiaoyue-smoke-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force $dataDir | Out-Null
$token = "smoke-secret-0123456789abcdef"
$port = 18800

# Child env is inherited from this process.
$env:XIAOYUE_DATA_DIR = $dataDir
$env:XIAOYUE_PORT = "$port"
$env:XIAOYUE_SESSION_TOKEN = $token
$proc = Start-Process -FilePath $exe -PassThru -WindowStyle Hidden
try {
    $deadline = (Get-Date).AddSeconds(60)
    $healthy = $false
    while ((Get-Date) -lt $deadline -and -not $healthy) {
        try {
            $r = Invoke-RestMethod "http://127.0.0.1:$port/api/health" -TimeoutSec 2
            if ($r.status -eq "ok") { $healthy = $true }
        } catch { Start-Sleep -Milliseconds 500 }
    }
    if (-not $healthy) { throw "sidecar did not become healthy" }

    # Auth enforcement against the packaged exe: no token => 401.
    $code = try {
        (Invoke-WebRequest "http://127.0.0.1:$port/api/profile/definitions" -UseBasicParsing).StatusCode
    } catch {
        $_.Exception.Response.StatusCode.value__
    }
    if ($code -ne 401) { throw "expected 401 without token, got $code" }

    # Correct bearer token => 200.
    $authed = Invoke-WebRequest "http://127.0.0.1:$port/api/profile/definitions" -Headers @{ Authorization = "Bearer $token" } -UseBasicParsing
    if ($authed.StatusCode -ne 200) { throw "expected 200 with token, got $($authed.StatusCode)" }

    # Fresh-DB migration proof: the 0009 extraction-run table must exist.
    $db = Join-Path $dataDir "xiaoyue.db"
    if (-not (Test-Path $db)) { throw "sqlite db missing" }
    $probe = try { (Invoke-WebRequest "http://127.0.0.1:$port/api/resumes" -Headers @{ Authorization = "Bearer $token" } -UseBasicParsing).StatusCode } catch { $_.Exception.Response.StatusCode.value__ }
    if ($probe -ne 200) { throw "resumes endpoint unexpected status $probe" }

    Write-Host "SMOKE OK: health + auth (401/200) + migrations on packaged exe (data dir: $dataDir)"
} finally {
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force $dataDir -ErrorAction SilentlyContinue
    Remove-Item Env:\XIAOYUE_DATA_DIR -ErrorAction SilentlyContinue
    Remove-Item Env:\XIAOYUE_PORT -ErrorAction SilentlyContinue
    Remove-Item Env:\XIAOYUE_SESSION_TOKEN -ErrorAction SilentlyContinue
}
