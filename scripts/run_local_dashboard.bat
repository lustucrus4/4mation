@echo off
setlocal EnableExtensions

REM Dashboard local solveur - http://127.0.0.1:8765/
cd /d "%~dp0.."

if not defined SOLVER_DASHBOARD_PORT set "SOLVER_DASHBOARD_PORT=8765"
if not defined TABLEBASE_DB set "TABLEBASE_DB=script\solver\data\tablebase.db"

set "PYTHON_EXE="
set "PYTHON_LAUNCHER="

if exist "%CD%\.venv\Scripts\python.exe" (
  set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"
  set "PYTHON_LAUNCHER=venv"
)

if not defined PYTHON_EXE (
  py -3 -c "import sys" >nul 2>&1
  if not errorlevel 1 (
    set "PYTHON_LAUNCHER=py3"
  )
)

if not defined PYTHON_LAUNCHER (
  where python >nul 2>&1
  if not errorlevel 1 (
    set "PYTHON_EXE=python"
    set "PYTHON_LAUNCHER=python"
  )
)

echo ========================================
echo  4mation - Dashboard solveur LOCAL
echo ========================================
echo URL : http://127.0.0.1:%SOLVER_DASHBOARD_PORT%/
echo DB  : %TABLEBASE_DB%
if "%PYTHON_LAUNCHER%"=="py3" (
  echo Python : py -3
) else (
  echo Python : %PYTHON_EXE%
)
echo.
echo Gardez cette fenetre ouverte tant que vous utilisez le dashboard.
echo Astuce : le compteur de positions n augmente que si 4mation-local tourne.
echo          Lancez scripts\run_local_solver_rust.bat ou run_local_solver_stack.bat
echo.

if not defined PYTHON_LAUNCHER (
  echo ERREUR : Python introuvable.
  echo Creez un environnement virtuel a la racine du projet :
  echo   py -3 -m venv .venv
  echo   .venv\Scripts\pip install -r api\requirements.txt
  echo Ou installez Python 3.12+ et ajoutez-le au PATH.
  pause
  exit /b 1
)

if "%PYTHON_LAUNCHER%"=="py3" (
  py -3 -c "import flask" >nul 2>&1
) else (
  "%PYTHON_EXE%" -c "import flask" >nul 2>&1
)
if errorlevel 1 (
  echo ERREUR : le module flask est absent.
  if exist "%CD%\.venv\Scripts\pip.exe" (
    echo Installez les dependances : .venv\Scripts\pip install -r api\requirements.txt
  ) else (
    echo Installez les dependances : pip install -r api\requirements.txt
  )
  pause
  exit /b 1
)

REM Libere le port si un ancien dashboard tourne encore (evite routes obsoletes)
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-NetTCPConnection -LocalPort %SOLVER_DASHBOARD_PORT% -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"

if "%PYTHON_LAUNCHER%"=="py3" (
  py -3 script\solver_rust\local_dashboard.py --db "%TABLEBASE_DB%" --port %SOLVER_DASHBOARD_PORT% %*
) else (
  "%PYTHON_EXE%" script\solver_rust\local_dashboard.py --db "%TABLEBASE_DB%" --port %SOLVER_DASHBOARD_PORT% %*
)
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
  echo.
  echo ERREUR : le dashboard s est arrete avec le code %EXIT_CODE%.
  echo Verifiez : pip install -r api\requirements.txt
  pause
)
exit /b %EXIT_CODE%
