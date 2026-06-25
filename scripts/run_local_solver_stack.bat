@echo off
setlocal EnableExtensions

REM UTILISEZ CE SCRIPT SEUL pour demarrer tout (dashboard + solveur Rust, 1 fenetre).
REM Ne lancez pas en plus run_local_dashboard.bat ni run_local_solver_rust.bat.
cd /d "%~dp0.."

if not defined SOLVER_DASHBOARD_PORT set "SOLVER_DASHBOARD_PORT=8765"
if not defined TABLEBASE_DB set "TABLEBASE_DB=script\solver\data\tablebase.db"
if not defined SOLVER_THREADS set "SOLVER_THREADS=%NUMBER_OF_PROCESSORS%"

echo ========================================
echo  4mation - Stack solveur LOCAL complet
echo ========================================
echo Dashboard : http://127.0.0.1:%SOLVER_DASHBOARD_PORT%/  (cette fenetre)
echo Solveur   : 4mation-local --dashboard (meme processus)
echo.
echo Stack 100%% Rust — plus de Python requis.
echo.

call "%~dp0run_local_solver_rust.bat" %*

endlocal
