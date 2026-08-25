# 批量上传知识库文档脚本
# 用法（PowerShell）：
#   .\scripts\upload_all.ps1 -Path "D:\你的文件夹"
# 可选：-BaseUrl http://127.0.0.1:8000 （默认本机后端）
#
# 注意：后端需已启动（cd backend; uv run uvicorn app.main:app --reload）

param(
    [Parameter(Mandatory = $true)]
    [string]$Path,
    [string]$BaseUrl = "http://127.0.0.1:8000"
)

if (-not (Test-Path $Path)) {
    Write-Host "路径不存在: $Path" -ForegroundColor Red
    exit 1
}

$files = Get-ChildItem $Path -File
if ($files.Count -eq 0) {
    Write-Host "文件夹中没有文件: $Path" -ForegroundColor Yellow
    exit 0
}

Write-Host "共找到 $($files.Count) 个文件，开始上传..." -ForegroundColor Cyan
$ok = 0
$fail = 0

foreach ($f in $files) {
    Write-Host "上传: $($f.Name) ..." -NoNewline
    try {
        $resp = curl.exe -s -X POST "$BaseUrl/api/v1/documents/upload" -F "file=@$($f.FullName)"
        $obj = $resp | ConvertFrom-Json
        if ($obj.status -eq "ready") {
            Write-Host " OK [$($obj.status)] $($obj.chunk_count) 分块" -ForegroundColor Green
            $ok++
        } else {
            Write-Host " 状态=$($obj.status)" -ForegroundColor Yellow
            $ok++
        }
    } catch {
        Write-Host " 失败: $($_.Exception.Message)" -ForegroundColor Red
        $fail++
    }
}

Write-Host ""
Write-Host "完成：成功 $ok 个，失败 $fail 个" -ForegroundColor Cyan
