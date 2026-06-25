# Worker solveur distribué — lancement local (Windows)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Python = if (Test-Path $VenvPython) { $VenvPython } else { "python" }

$ApiUrl = if ($env:SOLVER_API_URL) { $env:SOLVER_API_URL } else { "https://api-4mation.lab211.fr" }
$Workers = if ($env:SOLVER_WORKERS) { $env:SOLVER_WORKERS } else { "10" }
if (-not $env:SOLVER_IDLE_SLEEP) { $env:SOLVER_IDLE_SLEEP = "2" }
$ClaimBatch = if ($env:SOLVER_CLAIM_BATCH) { $env:SOLVER_CLAIM_BATCH } else { "25" }
$SolveThreads = if ($env:SOLVER_SOLVE_THREADS) { $env:SOLVER_SOLVE_THREADS } else { "2" }

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " 4mation — Worker solveur distribué" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "API      : $ApiUrl"
Write-Host "Workers  : $Workers processus"
Write-Host "Batch    : $ClaimBatch positions/claim"
Write-Host "Threads  : $SolveThreads resolution/processus"
Write-Host "Machine  : $env:COMPUTERNAME"
Write-Host ""
Write-Host "Appuyez sur Ctrl+C pour arrêter." -ForegroundColor Yellow
Write-Host ""

$env:PYTHONPATH = "$ProjectRoot;$ProjectRoot\script"
& $Python script\solver\distributed_worker.py --api-url $ApiUrl --workers $Workers --claim-batch $ClaimBatch --solve-threads $SolveThreads
