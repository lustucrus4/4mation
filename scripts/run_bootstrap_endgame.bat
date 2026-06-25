@echo off
setlocal EnableExtensions

REM Amorce la tablebase fin de partie (positions a <= N cases vides)
cd /d "%~dp0.."

if not defined TABLEBASE_DB set "TABLEBASE_DB=script\solver\data\tablebase.db"

echo ========================================
echo  4mation - Bootstrap tablebase endgame
echo ========================================
echo Base SQLite : %TABLEBASE_DB%
echo.

python script\solver\build_endgame_tablebase.py --db "%TABLEBASE_DB%" %*
if errorlevel 1 exit /b %ERRORLEVEL%

endlocal
