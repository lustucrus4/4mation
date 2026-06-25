@echo off
setlocal EnableExtensions
cd /d "%~dp0.."

set "DB=script\solver\data\tablebase.db"
set "BACKUP=script\solver\data\tablebase_pre_symmetry.db"

echo ========================================
echo  4mation - Activation symetries D4
echo ========================================
echo.

if exist "%DB%" (
    if not exist "%BACKUP%" (
        echo Sauvegarde ancienne base : %BACKUP%
        copy /Y "%DB%" "%BACKUP%" >nul
    ) else (
        echo Sauvegarde deja presente : %BACKUP%
    )
    echo Suppression de l ancienne base pour repartir en canonique...
    del /F "%DB%"
)

echo.
echo Bootstrap endgame (graines avec board_json)...
call "%~dp0run_bootstrap_endgame.bat"
if errorlevel 1 exit /b 1

echo.
echo Compilation 4mation-local (symetries ON par defaut)...
pushd script\solver_rust
cargo build --release --bin 4mation-local
if errorlevel 1 (
    popd
    exit /b 1
)
popd

echo.
echo Lancez maintenant : scripts\run_local_solver_stack.bat
echo Log attendu : "Symetries activees - forme canonique D4"
echo.
endlocal
