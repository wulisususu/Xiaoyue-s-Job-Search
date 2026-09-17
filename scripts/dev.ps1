$ErrorActionPreference = "Stop"

if (-not $env:XIAOYUE_DATA_DIR) {
    $env:XIAOYUE_DATA_DIR = Join-Path $env:LOCALAPPDATA "XiaoyueJobSearch"
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$corePath = Join-Path $repoRoot "services/core-api"

# tauri.conf.json references services/core-api/dist/xiaoyue-core-api as a
# bundle resource, and any cargo build (including `tauri dev`) validates it.
# Dev itself talks to the plain-python core below; build the exe once so the
# Rust side has something to point at.
$sidecarDist = Join-Path $corePath "dist/xiaoyue-core-api"
if (-not (Test-Path $sidecarDist)) {
    Write-Host "First run: building PyInstaller sidecar (services/core-api/dist/xiaoyue-core-api)..."
    & (Join-Path $PSScriptRoot "build-core.ps1")
}

Write-Host "Starting local core with XIAOYUE_DATA_DIR=$env:XIAOYUE_DATA_DIR"
$core = Start-Process -PassThru -NoNewWindow -FilePath "python" -ArgumentList @(
    "-m", "uvicorn", "app.main:app", "--app-dir", $corePath, "--host", "127.0.0.1", "--port", "8765", "--reload"
)

try {
    Set-Location $repoRoot
    npm run tauri:dev --workspace apps/desktop
}
finally {
    if ($core -and -not $core.HasExited) {
        Stop-Process -Id $core.Id -Force
    }
}
