@echo off
setlocal EnableExtensions

REM Solveur 4mation 100%% local — Legion Ryzen 16 coeurs
cd /d "%~dp0.."

if exist "%USERPROFILE%\.cargo\bin" (
    set "PATH=%USERPROFILE%\.cargo\bin;%PATH%"
)

if not defined SOLVER_THREADS set "SOLVER_THREADS=16"
if not defined TABLEBASE_MAX_EMPTY set "TABLEBASE_MAX_EMPTY=12"
if not defined TABLEBASE_DB set "TABLEBASE_DB=script\solver\data\tablebase.db"

set "LOCAL_BIN=script\solver_rust\target\release\4mation-local.exe"
if not exist "%LOCAL_BIN%" (
    echo Binaire absent - compilation release...
    pushd script\solver_rust
    cargo build --release
    if errorlevel 1 (
        echo Echec compilation Rust.
        echo - rustup : https://rustup.rs
        echo - MSVC Build Tools C++ requis pour link.exe
        popd
        exit /b 1
    )
    popd
)

echo ========================================
echo  4mation - Solveur local Rust
echo ========================================
echo DB         : %TABLEBASE_DB%
echo Threads    : %SOLVER_THREADS% (rayon)
echo Max empty  : %TABLEBASE_MAX_EMPTY%
echo Machine    : %COMPUTERNAME%
echo.
echo Aucun reseau requis. Ctrl+C pour arreter.
echo.

"%LOCAL_BIN%" --db "%TABLEBASE_DB%" --threads %SOLVER_THREADS% --max-empty %TABLEBASE_MAX_EMPTY% %*

endlocal
