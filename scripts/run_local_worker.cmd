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
if not defined SOLVER_WORKERS set "SOLVER_WORKERS=16"

set "PYTHONPATH=%CD%;%CD%\script"

echo ========================================
echo  4mation — Worker solveur distribue
echo ========================================
echo API      : %SOLVER_API_URL%
echo Workers  : %SOLVER_WORKERS% processus
echo Machine  : %COMPUTERNAME%
echo.
echo Appuyez sur Ctrl+C pour arreter.
echo.

"%PYTHON%" script\solver\distributed_worker.py --api-url %SOLVER_API_URL% --workers %SOLVER_WORKERS%

endlocal
