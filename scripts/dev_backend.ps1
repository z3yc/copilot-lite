# Copilot-Lite backend launcher (Windows, venv only)
#
# Why this script exists:
#   We once started the backend with the SYSTEM python (WindowsApps\...\python.exe -m uvicorn)
#   and without --reload, so code edits silently had no effect. This script always uses
#   backend\.venv and prints self-check info (interpreter path + key source mtime).
#
# Usage (from repo root):
#   powershell -ExecutionPolicy Bypass -File scripts\dev_backend.ps1            # reload on (dev)
#   powershell -ExecutionPolicy Bypass -File scripts\dev_backend.ps1 -NoReload  # reload off
#   powershell -ExecutionPolicy Bypass -File scripts\dev_backend.ps1 -Port 8001
#
# Stop: Ctrl+C in this window, or:
#   Get-NetTCPConnection -LocalPort 8000 -State Listen | % { Stop-Process -Id $_.OwningProcess -Force }

param(
    [int]$Port = 8000,
    [string]$HostAddr = "127.0.0.1",
    [switch]$NoReload
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$python = Join-Path $backend ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Host "ERROR: venv interpreter not found: $python" -ForegroundColor Red
    Write-Host "       Install deps first: cd backend; uv sync" -ForegroundColor Yellow
    exit 1
}

# Port guard: fail fast instead of "thinking you restarted while an old process still serves".
if (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue) {
    $busy = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($busy) {
        $owner = ($busy | Select-Object -First 1).OwningProcess
        Write-Host "ERROR: port $Port is already in use by PID $owner (stale backend?)." -ForegroundColor Red
        Write-Host "       Stop it: Stop-Process -Id $owner -Force" -ForegroundColor Yellow
        exit 1
    }
}

# Self-check: interpreter + key source mtime (so "which code am I running" is verifiable).
$kbTool = Join-Path $backend "app\tools\kb_tool.py"
Write-Host "=== Copilot-Lite backend ===" -ForegroundColor Cyan
Write-Host "  venv python : $python"
if (Test-Path $kbTool) {
    Write-Host "  kb_tool.py  : $((Get-Item $kbTool).LastWriteTime)"
}
Write-Host "  listen      : http://${HostAddr}:$Port (reload=$(if ($NoReload) { 'off' } else { 'on' }))"
Write-Host "  health      : http://${HostAddr}:$Port/api/v1/health/ready"
Write-Host ""

$uvicornArgs = @("-m", "uvicorn", "app.main:app", "--host", $HostAddr, "--port", "$Port")
if (-not $NoReload) { $uvicornArgs += "--reload" }

Push-Location $backend
try {
    & $python @uvicornArgs
} finally {
    Pop-Location
}
