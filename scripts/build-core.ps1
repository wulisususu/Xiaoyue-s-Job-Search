$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$corePath = Join-Path $repoRoot "services/core-api"

python -m PyInstaller (Join-Path $corePath "packaging/xiaoyue-core-api.spec") --noconfirm `
    --distpath (Join-Path $corePath "dist") `
    --workpath (Join-Path $corePath "build/pyinstaller")

$exe = Join-Path $corePath "dist/xiaoyue-core-api/xiaoyue-core-api.exe"
if (-not (Test-Path $exe)) { throw "sidecar exe missing: $exe" }
Write-Host "Core sidecar built: $exe"
