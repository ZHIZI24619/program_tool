$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

# 统一使用系统 Python（不再使用项目内虚拟环境）
$Python = "C:\Users\35370\AppData\Local\Programs\Python\Python312\python.exe"
if (-not (Test-Path $Python)) { $Python = "python" }

& $Python -m pip install -r requirements.txt
& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name DAPFlashTool `
    --paths $ProjectRoot `
    --hidden-import dap_flash_tool.app `
    --add-data "assets;assets" `
    --icon assets\logo.ico `
    launcher.py

$PyOcdExe = Join-Path (Split-Path -Parent $Python) "pyocd.exe"
if (-not (Test-Path $PyOcdExe)) { $PyOcdExe = Join-Path (Split-Path -Parent $Python) "Scripts\pyocd.exe" }
if (-not (Test-Path $PyOcdExe)) {
    throw "pyocd.exe not found beside Python"
}
Copy-Item $PyOcdExe (Join-Path $ProjectRoot "dist\DAPFlashTool\pyocd.exe") -Force

Write-Host "EXE generated: $ProjectRoot\dist\DAPFlashTool\DAPFlashTool.exe"
