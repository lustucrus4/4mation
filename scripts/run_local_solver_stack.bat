@echo off
setlocal EnableExtensions

REM Lance le dashboard + worker Rust en mode local DB (Legion / Windows)
cd /d "%~dp0.."

if not defined SOLVER_DASHBOARD_PORT set "SOLVER_DASHBOARD_PORT=8765"
if not defined TABLEBASE_DB set "TABLEBASE_DB=script\solver\data\tablebase.db"
if not defined SOLVER_THREADS set "SOLVER_THREADS=16"

echo ========================================
echo  4mation - Stack solveur LOCAL complet
echo ========================================
echo Dashboard : http://127.0.0.1:%SOLVER_DASHBOARD_PORT%/  (cette fenetre)
echo Solveur   : 4mation-local --db %TABLEBASE_DB%  (2e fenetre)
echo.
echo Le filler de file n'est plus necessaire avec 4mation-local (exploration integree).
echo.

start "" cmd /k "%~dp0run_local_solver_rust.bat" %*

timeout /t 2 /nobreak >nul

call "%~dp0run_local_dashboard.bat" %*

endlocal
