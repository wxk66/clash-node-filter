$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot "backend\clash-speedtest.exe"))) {
    & .\build.ps1
}

Write-Host "正在打包桌面 GUI..." -ForegroundColor Cyan
pyinstaller --noconfirm --clean --onefile --windowed --name "Clash节点筛选器" `
    --add-binary "backend\clash-speedtest.exe;backend" `
    --add-data "backend\desktop-config.yaml;backend" `
    desktop_app.py
Write-Host "打包完成：$projectRoot\dist\Clash节点筛选器.exe" -ForegroundColor Green
