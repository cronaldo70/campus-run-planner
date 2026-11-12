@echo off
setlocal
set "planner_python=%~dp0..\..\work\.venv\Scripts\pythonw.exe"
if exist "%planner_python%" (
    start "" "%planner_python%" -B "%~dp0run_planner.py"
    exit /b
)
where pyw.exe >nul 2>&1
if not errorlevel 1 (
    start "" pyw.exe -3.12 -B "%~dp0run_planner.py"
    exit /b
)
echo Python 3.12 with Tkinter is required. See the project README.
pause
