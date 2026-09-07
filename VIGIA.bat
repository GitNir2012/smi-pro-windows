@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PY=
py -3 -c "import sys" 2>nul && set PY=py -3
if not defined PY python -c "import sys" 2>nul && set PY=python
if not defined PY exit /b 1
%PY% vigia.py
