@echo off
setlocal EnableExtensions
cd /d "%~dp0.."

if not defined TABLEBASE_DB set "TABLEBASE_DB=script\solver\data\tablebase.db"
if not defined SOLVER_DASHBOARD_PORT set "SOLVER_DASHBOARD_PORT=8765"
if not defined SOLVER_THREADS set "SOLVER_THREADS=%NUMBER_OF_PROCESSORS%"

echo ========================================
echo  4mation - Livre d'ouverture RUST (~2 Go)
echo ========================================
echo.
echo IMPORTANT : arretez le solveur endgame avant (meme SQLite).
echo Dashboard : http://127.0.0.1:%SOLVER_DASHBOARD_PORT%/
echo.

call "%~dp0run_local_solver_rust.bat" --opening-book --opening-estimate fast --opening-target-gb 2 %*

endlocal
