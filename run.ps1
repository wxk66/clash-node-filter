$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendExe = Join-Path $projectRoot "backend\clash-speedtest.exe"
if (-not (Test-Path -LiteralPath $backendExe)) {
    & (Join-Path $projectRoot "build.ps1")
}
Set-Location $projectRoot
python .\desktop_app.py
