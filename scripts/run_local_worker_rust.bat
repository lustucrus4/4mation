@echo off
setlocal EnableExtensions

REM Worker solveur Rust haute performance — Ryzen 16 coeurs
cd /d "%~dp0.."

if exist "%USERPROFILE%\.cargo\bin" (
    set "PATH=%USERPROFILE%\.cargo\bin;%PATH%"
)

if not defined SOLVER_API_URL set "SOLVER_API_URL=https://api-4mation.lab211.fr"
if not defined SOLVER_THREADS set "SOLVER_THREADS=16"
if not defined SOLVER_CLAIM_BATCH set "SOLVER_CLAIM_BATCH=25"

set "WORKER_BIN=script\solver_rust\target\release\4mation-worker.exe"
if not exist "%WORKER_BIN%" (
    echo Binaire absent — compilation release...
    pushd script\solver_rust
    cargo build --release
    if errorlevel 1 (
        echo Echec compilation Rust.
        echo - rustup : https://rustup.rs
        echo - MSVC Build Tools (C++) : https://visualstudio.microsoft.com/fr/downloads/
        echo   Cochez « Developpement Desktop en C++ » puis relancez ce script.
        popd
        exit /b 1
    )
    popd
)

echo ========================================
echo  4mation — Worker Rust (4mation-worker)
echo ========================================
echo API      : %SOLVER_API_URL%
echo Threads  : %SOLVER_THREADS% (rayon)
echo Batch    : %SOLVER_CLAIM_BATCH% positions/claim
echo Machine  : %COMPUTERNAME%
echo.
echo Mode local DB : ajouter --local-db script\solver\data\tablebase.db
echo Appuyez sur Ctrl+C pour arreter.
echo.

"%WORKER_BIN%" --api-url %SOLVER_API_URL% --threads %SOLVER_THREADS% --claim-batch %SOLVER_CLAIM_BATCH% %*

endlocal
