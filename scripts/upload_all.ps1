# Batch upload documents to Copilot-Lite knowledge base
# Usage (PowerShell):
#   powershell -ExecutionPolicy Bypass -File scripts\upload_all.ps1 -Path "D:\your\folder"
# Optional: -BaseUrl http://127.0.0.1:8000 (default local backend)
#
# Note: backend must be running first (cd backend; uv run uvicorn app.main:app --reload)
# ASCII-only output for compatibility with Windows PowerShell 5.1 (GBK console).

param(
    [Parameter(Mandatory = $true)]
    [string]$Path,
    [string]$BaseUrl = "http://127.0.0.1:8000"
)

if (-not (Test-Path $Path)) {
    Write-Host "ERROR: path not found: $Path" -ForegroundColor Red
    exit 1
}

$files = Get-ChildItem $Path -File
if ($files.Count -eq 0) {
    Write-Host "No files found in: $Path" -ForegroundColor Yellow
    exit 0
}

Write-Host "Found $($files.Count) files. Uploading..." -ForegroundColor Cyan
$ok = 0
$fail = 0

foreach ($f in $files) {
    Write-Host "Uploading: $($f.Name) ..." -NoNewline
    try {
        $resp = curl.exe -s -X POST "$BaseUrl/api/v1/documents/upload" -F "file=@$($f.FullName)"
        $obj = $resp | ConvertFrom-Json
        if ($obj.status) {
            Write-Host " OK [$($obj.status)] chunks=$($obj.chunk_count)" -ForegroundColor Green
            $ok++
        } else {
            Write-Host " UNKNOWN response: $resp" -ForegroundColor Yellow
            $fail++
        }
    } catch {
        Write-Host " FAILED: $($_.Exception.Message)" -ForegroundColor Red
        $fail++
    }
}

Write-Host ""
Write-Host "Done. Succeeded: $ok, Failed: $fail" -ForegroundColor Cyan
