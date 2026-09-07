@echo off
chcp 65001 >nul
cd /d "%~dp0"
title SMI Pro - agendar vigia
echo.
echo  Cria duas tarefas no Windows:
echo   - a cada hora confere se o SMI esta no ar
echo   - ao ligar o Windows tambem confere
echo  Se estiver parado (antivirus, queda, reboot), religa sozinho.
echo  Para parar o historico: PARAR-AGENDAMENTO.bat
echo.

set VIGIA=%~dp0VIGIA.bat
if not exist "%VIGIA%" (
  echo  VIGIA.bat nao encontrado nesta pasta.
  pause
  exit /b 1
)

schtasks /Create /TN "SMI Pro vigia" /TR "\"%VIGIA%\"" /SC HOURLY /F /RL LIMITED
if errorlevel 1 (
  echo.
  echo  Nao consegui criar a tarefa. Tente "Executar como administrador".
  pause
  exit /b 1
)
schtasks /Create /TN "SMI Pro ao ligar" /TR "\"%VIGIA%\"" /SC ONLOGON /F /RL LIMITED >nul 2>&1

echo.
echo  Pronto. Tarefas:
echo    SMI Pro vigia      (de hora em hora)
echo    SMI Pro ao ligar   (quando voce entra no Windows)
echo.
echo  Conferindo agora...
call "%VIGIA%"
echo.
echo  Kaspersky: adicione esta pasta e o python.exe nas exclusoes,
echo  senao o antivirus pode derrubar de novo.
echo.
pause
