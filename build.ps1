$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendRoot = Join-Path $projectRoot "backend"
$outputPath = Join-Path $backendRoot "clash-speedtest.exe"

Write-Host "正在编译本地 Mihomo 测试核心..." -ForegroundColor Cyan
Push-Location $backendRoot
try {
    go build -trimpath -ldflags="-s -w" -o $outputPath .
} finally {
    Pop-Location
}
Write-Host "已生成：$outputPath" -ForegroundColor Green
Write-Host "启动桌面界面：python desktop_app.py" -ForegroundColor Yellow
