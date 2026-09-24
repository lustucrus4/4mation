@echo off
setlocal EnableExtensions

REM Preuve exacte de 4mation depuis l'ouverture (symétries + transpositions)
cd /d "%~dp0.."

if exist "%USERPROFILE%\.cargo\bin" (
    set "PATH=%USERPROFILE%\.cargo\bin;%PATH%"
)

if not defined SOLVER_THREADS set "SOLVER_THREADS=%NUMBER_OF_PROCESSORS%"
if not defined PROOF_TT_MB set "PROOF_TT_MB=1024"
if not defined PROOF_SECONDS set "PROOF_SECONDS=0"

set "BIN=script\solver_rust\target\release\4mation-proof.exe"
if not exist "%BIN%" (
    echo Compilation release...
    pushd script\solver_rust
    cargo build --release --bin 4mation-proof
    if errorlevel 1 (
        echo Echec compilation Rust.
        popd
        exit /b 1
    )
    popd
)

echo ========================================
echo  4mation - preuve exacte (ouverture)
echo ========================================
echo Threads : %SOLVER_THREADS%
echo Memoire : %PROOF_TT_MB% Mo
echo Secondes: %PROOF_SECONDS% ^(0 = jusqu'a la preuve^)
echo.
echo Les rotations et les miroirs ne sont calcules qu'une fois.
echo Un motif decale vers un bord reste une position differente.
echo Dashboard : http://127.0.0.1:8770/
echo.

"%BIN%" --threads %SOLVER_THREADS% --tt-mb %PROOF_TT_MB% --seconds %PROOF_SECONDS% --port 8770
exit /b %ERRORLEVEL%
