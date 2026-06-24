@echo off
setlocal EnableExtensions

REM Dashboard local solveur — http://127.0.0.1:8765/
cd /d "%~dp0.."

if not defined SOLVER_DASHBOARD_PORT set "SOLVER_DASHBOARD_PORT=8765"
if not defined TABLEBASE_DB set "TABLEBASE_DB=script\solver\data\tablebase.db"

echo ========================================
echo  4mation - Dashboard solveur LOCAL
echo ========================================
echo URL : http://127.0.0.1:%SOLVER_DASHBOARD_PORT%/
echo DB  : %TABLEBASE_DB%
echo.

python script\solver_rust\local_dashboard.py --db "%TABLEBASE_DB%" --port %SOLVER_DASHBOARD_PORT% %*

endlocal
