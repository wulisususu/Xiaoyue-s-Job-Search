$ErrorActionPreference = "Stop"

if (-not $env:XIAOYUE_DATA_DIR) {
    $env:XIAOYUE_DATA_DIR = Join-Path $env:LOCALAPPDATA "XiaoyueJobSearch"
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$corePath = Join-Path $repoRoot "services/core-api"

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
