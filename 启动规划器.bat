@echo off
rem Launch the campus-run route planner with the bundled virtual environment.
chcp 65001 >nul
cd /d "%~dp0"
set "PY=.\work\.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo venv not found: %PY%
  pause
  exit /b 1
)
"%PY%" -B ".\outputs\run-planner\run_planner.py"
if errorlevel 1 pause