@echo off
setlocal EnableExtensions

REM Dashboard local solveur Rust - http://127.0.0.1:8765/
cd /d "%~dp0.."

if exist "%USERPROFILE%\.cargo\bin" (
    set "PATH=%USERPROFILE%\.cargo\bin;%PATH%"
)

if not defined SOLVER_DASHBOARD_PORT set "SOLVER_DASHBOARD_PORT=8765"
if not defined TABLEBASE_DB set "TABLEBASE_DB=script\solver\data\tablebase.db"

set "DASH_BIN=script\solver_rust\target\release\4mation-dashboard.exe"
if not exist "%DASH_BIN%" (
    echo Binaire absent - compilation release...
    pushd script\solver_rust
    cargo build --release
    if errorlevel 1 (
        echo Echec compilation Rust.
        popd
        exit /b 1
    )
    popd
)

echo ========================================
echo  4mation - Dashboard solveur LOCAL (Rust)
echo ========================================
echo URL : http://127.0.0.1:%SOLVER_DASHBOARD_PORT%/
echo DB  : %TABLEBASE_DB%
echo.
echo Gardez cette fenetre ouverte tant que vous utilisez le dashboard.
echo Astuce : le compteur de positions n augmente que si 4mation-local tourne.
echo          Lancez scripts\run_local_solver_rust.bat ou run_local_solver_stack.bat
echo.

REM Libere le port si un ancien dashboard tourne encore
call "%~dp0free_dashboard_port.bat"

"%DASH_BIN%" --db "%TABLEBASE_DB%" --port %SOLVER_DASHBOARD_PORT% %*
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
    echo.
    echo ERREUR : le dashboard s est arrete avec le code %EXIT_CODE%.
    pause
)
exit /b %EXIT_CODE%
