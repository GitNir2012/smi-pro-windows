@echo off
chcp 65001 >nul
cd /d "%~dp0"
title SMI Pro - instalar
echo.
echo  SMI Pro - checagem do Windows 10
echo  --------------------------------
echo.

set PY=
py -3 -c "import sys; raise SystemExit(0 if sys.version_info>=(3,8) else 1)" 2>nul && set PY=py -3
if not defined PY python -c "import sys; raise SystemExit(0 if sys.version_info>=(3,8) else 1)" 2>nul && set PY=python

if not defined PY (
  echo  Python 3.8 ou superior nao foi encontrado.
  echo  Instale em https://www.python.org/downloads/windows/
  echo  Marque a caixa "Add python.exe to PATH" na primeira tela.
  echo  Depois rode este INSTALAR.bat de novo.
  echo.
  start https://www.python.org/downloads/windows/
  pause
  exit /b 1
)

echo  Python ok:
%PY% -c "import sys; print(' ', sys.version)"
echo.
if not exist dados mkdir dados
echo  Pasta de dados: %cd%\dados
echo  Nao precisa pip. So a biblioteca padrao.
echo.
echo  Pronto. Agora dê dois cliques em INICIAR.bat
echo  (e deixe a janela preta aberta enquanto gravar).
echo.
pause
