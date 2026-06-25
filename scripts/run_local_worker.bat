@echo off
setlocal EnableExtensions

REM Worker solveur distribué — lancement local (contourne ExecutionPolicy PowerShell)
cd /d "%~dp0.."

if exist ".venv\Scripts\activate.bat" (
    call ".venv\Scripts\activate.bat"
)

if exist ".venv\Scripts\python.exe" (
    set "PYTHON=.venv\Scripts\python.exe"
) else (
    set "PYTHON=python"
)

if not defined SOLVER_API_URL set "SOLVER_API_URL=https://api-4mation.lab211.fr"
REM 8-10 processus : equilibre CPU local vs charge API/SQLite (eviter 12+ flood).
if not defined SOLVER_WORKERS set "SOLVER_WORKERS=10"
if not defined SOLVER_IDLE_SLEEP set "SOLVER_IDLE_SLEEP=2"
REM Positions par claim HTTP — reduit la latence reseau (max serveur : 50).
if not defined SOLVER_CLAIM_BATCH set "SOLVER_CLAIM_BATCH=25"
REM Threads de resolution par processus (hybride local avant submit-batch).
if not defined SOLVER_SOLVE_THREADS set "SOLVER_SOLVE_THREADS=2"

set "PYTHONPATH=%CD%;%CD%\script"

echo ========================================
echo  4mation — Worker solveur distribue
echo ========================================
echo API      : %SOLVER_API_URL%
echo Workers  : %SOLVER_WORKERS% processus
echo Batch    : %SOLVER_CLAIM_BATCH% positions/claim
echo Threads  : %SOLVER_SOLVE_THREADS% resolution/processus
echo Machine  : %COMPUTERNAME%
echo.
echo Appuyez sur Ctrl+C pour arreter.
echo.

"%PYTHON%" script\solver\distributed_worker.py --api-url %SOLVER_API_URL% --workers %SOLVER_WORKERS% --claim-batch %SOLVER_CLAIM_BATCH% --solve-threads %SOLVER_SOLVE_THREADS%

endlocal
