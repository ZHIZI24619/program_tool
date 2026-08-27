$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$PythonCandidates = @(
    (Join-Path $ProjectRoot ".venv-win\Scripts\python.exe"),
    (Join-Path $ProjectRoot ".venv\Scripts\python.exe"),
    (Join-Path $ProjectRoot ".venv\bin\python.exe"),
    (Join-Path (Split-Path -Parent $ProjectRoot) ".venv\Scripts\python.exe"),
    (Join-Path (Split-Path -Parent $ProjectRoot) ".venv\bin\python.exe")
)

$Python = $PythonCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $Python) {
    $Python = "python"
}

& $Python -m pip install -r requirements.txt
& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name DAPFlashTool `
    --paths $ProjectRoot `
    --hidden-import dap_flash_tool.app `
    launcher.py

$PyOcdExe = Join-Path (Split-Path -Parent $Python) "pyocd.exe"
if (-not (Test-Path $PyOcdExe)) {
    throw "pyocd.exe not found beside Python: $PyOcdExe"
}
Copy-Item $PyOcdExe (Join-Path $ProjectRoot "dist\DAPFlashTool\pyocd.exe") -Force

Write-Host "EXE generated: $ProjectRoot\dist\DAPFlashTool\DAPFlashTool.exe"
