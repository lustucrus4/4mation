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
REM 16 cœurs physiques ; monter a 24-32 si CPU bas (charge I/O API). Defaut code Python : 4.
if not defined SOLVER_WORKERS set "SOLVER_WORKERS=16"
REM Positions par claim HTTP — reduit la latence reseau (max serveur : 50).
if not defined SOLVER_CLAIM_BATCH set "SOLVER_CLAIM_BATCH=25"

set "PYTHONPATH=%CD%;%CD%\script"

echo ========================================
echo  4mation — Worker solveur distribue
echo ========================================
echo API      : %SOLVER_API_URL%
echo Workers  : %SOLVER_WORKERS% processus
echo Batch    : %SOLVER_CLAIM_BATCH% positions/claim
echo Machine  : %COMPUTERNAME%
echo.
echo Appuyez sur Ctrl+C pour arreter.
echo.

"%PYTHON%" script\solver\distributed_worker.py --api-url %SOLVER_API_URL% --workers %SOLVER_WORKERS% --claim-batch %SOLVER_CLAIM_BATCH%

endlocal
