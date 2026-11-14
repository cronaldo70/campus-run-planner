@echo off
rem Shared launcher: creates work\.venv on first run, then starts the chosen front end.
rem   Start-Planner.bat            -> route planner  (outputs\run-planner\run_planner.py)
rem   Start-Real-Run.bat           -> real-run planner (outputs\real-run-planner\real_run.py)
chcp 65001 >nul
cd /d "%~dp0"

if not defined CAMPUS_RUN_SCRIPT set "CAMPUS_RUN_SCRIPT=.\outputs\run-planner\run_planner.py"
set "VENV=.\work\.venv"
set "PY=%VENV%\Scripts\python.exe"

if exist "%PY%" goto run

echo First run: creating the virtual environment in work\.venv ...
set "PYCMD="

rem An explicit interpreter wins, handy when several Pythons are installed.
if defined CAMPUS_RUN_PYTHON set "PYCMD=%CAMPUS_RUN_PYTHON%"

rem Otherwise look for a CPython 3.10-3.13 through the py launcher, then PATH.
if not defined PYCMD (
  for %%V in (3.13 3.12 3.11 3.10) do (
    if not defined PYCMD (
      py -%%V -c "import sys" >nul 2>nul && set "PYCMD=py -%%V"
    )
  )
)
if not defined PYCMD (
  python -c "import sys" >nul 2>nul && set "PYCMD=python"
)
if not defined PYCMD (
  python3 -c "import sys" >nul 2>nul && set "PYCMD=python3"
)

if not defined PYCMD (
  echo.
  echo No usable Python 3.10-3.13 found.
  echo Windows' "python" entry is often just the Microsoft Store stub - install
  echo the real interpreter and tick "Add python.exe to PATH":
  echo   https://www.python.org/downloads/
  echo If you already have one in a custom place, point at it explicitly:
  echo   set CAMPUS_RUN_PYTHON=C:\path\to\python.exe
  echo.
  pause
  exit /b 1
)

echo Using: %PYCMD%
%PYCMD% -m venv "%VENV%"
if errorlevel 1 (
  echo Failed to create work\.venv
  pause
  exit /b 1
)
if defined CAMPUS_RUN_PIP_INDEX (
  "%PY%" -m pip install --quiet --upgrade pip -i %CAMPUS_RUN_PIP_INDEX%
  "%PY%" -m pip install --quiet -r requirements.txt -i %CAMPUS_RUN_PIP_INDEX%
) else (
  "%PY%" -m pip install --quiet --upgrade pip
  "%PY%" -m pip install --quiet -r requirements.txt
)
if errorlevel 1 (
  echo Failed to install requirements.txt - needs network, or set CAMPUS_RUN_PIP_INDEX
  pause
  exit /b 1
)

:run
"%PY%" -B "%CAMPUS_RUN_SCRIPT%"
if errorlevel 1 pause