@echo off
chcp 65001 >nul
cd /d "%~dp0"
title SMI Pro - gravador
set PY=
py -3 -c "import sys" 2>nul && set PY=py -3
if not defined PY python -c "import sys" 2>nul && set PY=python
if not defined PY (
  echo Rode INSTALAR.bat primeiro. Precisa Python 3.8+.
  pause
  exit /b 1
)
echo Abrindo a mesa SMI Pro...
echo Deixe esta janela aberta. Fechar = parar o gravador.
echo.
if exist SMI-Pro.py (
  %PY% SMI-Pro.py
) else (
  %PY% iniciar.py
)
if errorlevel 1 (
  echo.
  echo Falha ao iniciar. Rode INSTALAR.bat e tente de novo.
  pause
)
