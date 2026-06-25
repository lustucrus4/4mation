@echo off
REM Raccourci depuis n'importe quel dossier parent
cd /d "%~dp0"
call scripts\run_local_solver_stack.bat %*
