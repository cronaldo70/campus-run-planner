@echo off
rem Open the obstacle-aware real-run planner. Prefers the project launcher, which
rem also builds work\.venv on a fresh machine; falls back to pyw.
setlocal
if exist "%~dp0..\..\Start-Real-Run.bat" (
    call "%~dp0..\..\Start-Real-Run.bat"
    exit /b
)
set "run_python=%~dp0..\..\work\.venv\Scripts\python.exe"
if exist "%run_python%" (
    start "" "%run_python%" -B "%~dp0real_run.py"
    exit /b
)
where pyw.exe >nul 2>&1
if not errorlevel 1 (
    start "" pyw.exe -3 -B "%~dp0real_run.py"
    exit /b
)
echo Python 3 with Tkinter is required. Run Start-Real-Run.bat in the project root.
pause
exit /b 1