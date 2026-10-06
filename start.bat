@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title 日语语感训练

set "VPY=.venv\Scripts\python.exe"
if exist "%VPY%" goto check_deps

rem ---- 找 Python：优先 py 启动器，其次 python ----
set "PY="
py -3 --version >nul 2>nul && set "PY=py -3"
if not defined PY python --version >nul 2>nul && set "PY=python"
if not defined PY goto no_python

echo [首次运行] 正在创建虚拟环境 .venv ...
%PY% -m venv .venv
if errorlevel 1 goto fail

:check_deps
"%VPY%" -c "import panda3d" >nul 2>nul
if not errorlevel 1 goto run
echo [首次运行] 正在安装 Panda3D，需要一两分钟 ...
"%VPY%" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto fail

:run
"%VPY%" main.py
if errorlevel 1 goto fail
exit /b 0

:no_python
echo 没有找到 Python。请先安装 Python 3.10 以上版本：https://www.python.org/downloads/
echo 安装时勾选 "Add python.exe to PATH"。
pause
exit /b 1

:fail
echo.
echo 出错了，请把上面的错误信息截图发给我。
pause
exit /b 1
