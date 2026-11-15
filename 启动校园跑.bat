@echo off
setlocal EnableExtensions
rem 控制台是 GBK(936)，外部设了 PYTHONIOENCODING/PYTHONUTF8 会把中文搅成乱码，这里统一清掉
set "PYTHONIOENCODING="
set "PYTHONUTF8="
rem ==========================================================================
rem  校园跑 · 一键启动
rem
rem  双击            -> 实跑版（读打卡点 / 自动起点 / 模拟跑）
rem  ... planner     -> 旧版规划器（只画路线，不连手机）
rem  ... check       -> 环境自检（Python / 依赖 / 手机连接）
rem  ... debug       -> 前台运行实跑版，报错直接显示在控制台
rem
rem  第一次运行会自己建 work\.venv 并装 requirements.txt。
rem ==========================================================================
title 校园跑 · 一键启动
cd /d "%~dp0"

set "TARGET=outputs\real-run-planner\real_run.py"
set "MODE=实跑版"
for %%A in (%*) do (
  if /i "%%~A"=="planner" (
    set "TARGET=outputs\run-planner\run_planner.py"
    set "MODE=旧版规划器"
  )
  if /i "%%~A"=="check" set "CHECK_ONLY=1"
  if /i "%%~A"=="debug" set "DEBUG_RUN=1"
)

set "VENV=work\.venv"
set "PY=%VENV%\Scripts\python.exe"
set "PYW=%VENV%\Scripts\pythonw.exe"

rem ---------- 1. 找解释器，必要时建 venv ----------
if exist "%PY%" goto have_venv

echo 第一次运行：正在创建 work\.venv（大约 1 分钟，只需一次）...
set "PYCMD="
if defined CAMPUS_RUN_PYTHON set "PYCMD=%CAMPUS_RUN_PYTHON%"
if not defined PYCMD (
  for %%V in (3.13 3.12 3.11 3.10) do (
    if not defined PYCMD py -%%V -c "import sys" >nul 2>nul && set "PYCMD=py -%%V"
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
  echo 没找到可用的 Python 3.10-3.13。
  echo Windows 自带的 python 常常只是应用商店的占位符，请先装官方版本：
  echo   https://www.python.org/downloads/
  echo 安装时勾选 Add python.exe to PATH。已有 Python 在别处可以指定：
  echo   set CAMPUS_RUN_PYTHON=C:\path\to\python.exe
  echo.
  pause
  exit /b 1
)

echo 使用 %PYCMD% 建虚拟环境...
%PYCMD% -m venv "%VENV%"
if errorlevel 1 (
  echo 建 work\.venv 失败。
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
  echo 装 requirements.txt 失败：需要联网。国内网络可以先设镜像再运行：
  echo   set CAMPUS_RUN_PIP_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple
  pause
  exit /b 1
)

:have_venv
rem 依赖被手删过的话，这里自动补一次
"%PY%" -B -c "import pymobiledevice3, tkinter" >nul 2>nul
if errorlevel 1 (
  echo 依赖不完整，正在补装...
  "%PY%" -m pip install --quiet -r requirements.txt
  if errorlevel 1 (
    echo 补装失败，设 CAMPUS_RUN_PIP_INDEX 换镜像后重试。
    pause
    exit /b 1
  )
)

rem ---------- 2. 自检 ----------
if defined CHECK_ONLY (
  echo.
  "%PY%" -B tools\doctor.py
  echo.
  pause
  exit /b 0
)

rem ---------- 3. 启动 ----------
if defined DEBUG_RUN (
  echo 正在前台打开%MODE%（关闭窗口即结束）...
  echo.
  "%PY%" -B "%TARGET%"
  if errorlevel 1 (
    echo.
    echo 上面就是报错信息，把它发给我即可。
    pause
  )
  exit /b 0
)

if not exist "%PYW%" set "PYW=%PY%"
if not exist "work" mkdir "work"
start "" "%PYW%" -B "%TARGET%"
echo 已打开%MODE%。
echo 窗口没出现就看 work\last-launch.log，或在命令行跑：启动校园跑.bat debug
