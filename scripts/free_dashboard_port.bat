@echo off
setlocal EnableExtensions

if not defined SOLVER_DASHBOARD_PORT set "SOLVER_DASHBOARD_PORT=8765"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0free_listen_port.ps1" -Port %SOLVER_DASHBOARD_PORT%

endlocal
