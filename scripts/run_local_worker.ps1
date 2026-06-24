# Worker solveur distribué — lancement local (Windows)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Python = if (Test-Path $VenvPython) { $VenvPython } else { "python" }

$ApiUrl = if ($env:SOLVER_API_URL) { $env:SOLVER_API_URL } else { "https://api-4mation.lab211.fr" }
$Workers = if ($env:SOLVER_WORKERS) { $env:SOLVER_WORKERS } else { "16" }

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " 4mation — Worker solveur distribué" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "API      : $ApiUrl"
Write-Host "Workers  : $Workers processus"
Write-Host "Machine  : $env:COMPUTERNAME"
Write-Host ""
Write-Host "Appuyez sur Ctrl+C pour arrêter." -ForegroundColor Yellow
Write-Host ""

$env:PYTHONPATH = "$ProjectRoot;$ProjectRoot\script"
& $Python script\solver\distributed_worker.py --api-url $ApiUrl --workers $Workers
