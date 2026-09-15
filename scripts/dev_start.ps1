# Copilot-Lite one-click local startup (Windows)
# Starts: backend (uvicorn) + web (vite dev), then opens browser.
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts\dev_start.ps1
# Optional: -SkipWeb $true (backend only)

param([switch]$SkipWeb)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$web = Join-Path $root "web"

Write-Host "=== Copilot-Lite one-click startup ===" -ForegroundColor Cyan

# 0. Check prerequisites
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: uv not found. Install: https://docs.astral.sh/uv/" -ForegroundColor Red
    exit 1
}

# 1. Backend deps
Write-Host "[1/4] Installing backend dependencies..." -ForegroundColor Cyan
Push-Location $backend
uv sync 2>&1 | Out-Null
Pop-Location

# 2. Schema: local mode creates tables on startup (create_all) - no alembic needed
#    (also the migration chain cannot run on SQLite); only cloud mode needs alembic.
$runMode = "local"
$envFile = Join-Path $backend ".env"
if (Test-Path $envFile) {
    $m = Select-String -Path $envFile -Pattern '^\s*RUN_MODE\s*=\s*(\w+)' | Select-Object -First 1
    if ($m) { $runMode = $m.Matches[0].Groups[1].Value.ToLower() }
}
if ($runMode -eq "cloud") {
    Write-Host "[2/4] RUN_MODE=cloud: applying alembic migrations..." -ForegroundColor Cyan
    Push-Location $backend
    uv run alembic upgrade head 2>&1 | Out-Null
    Pop-Location
} else {
    Write-Host "[2/4] Local mode: tables created on startup (no alembic needed)" -ForegroundColor Cyan
}

# 3. Start backend in a new window
Write-Host "[3/4] Starting backend on :8000 (new window)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "Set-Location '$backend'; uv run uvicorn app.main:app --reload"
)

if ($SkipWeb) {
    Write-Host "Backend ready: http://127.0.0.1:8000/docs (API docs)" -ForegroundColor Green
    exit 0
}

# 4. Frontend deps + dev server
Write-Host "[4/4] Preparing frontend..." -ForegroundColor Cyan
Push-Location $web
if (-not (Test-Path "node_modules")) {
    Write-Host "  Installing frontend deps (first run, may take a while)..."
    npm install 2>&1 | Out-Null
}
Pop-Location

Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "Set-Location '$web'; npm run dev"
)

Start-Sleep -Seconds 4
Write-Host "Opening browser: http://localhost:5173" -ForegroundColor Green
Start-Process "http://localhost:5173"
Write-Host "Done. Backend :8000 | Web :5173 | API docs: http://127.0.0.1:8000/docs" -ForegroundColor Green
