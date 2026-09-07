@echo off
chcp 65001 >nul
cd /d "%~dp0"
title SMI Pro - parar vigia
echo.
echo  Remove o agendamento. O SMI que ja estiver aberto continua.
echo  Voce so deixa de religar sozinho.
echo.
schtasks /Delete /TN "SMI Pro vigia" /F
schtasks /Delete /TN "SMI Pro ao ligar" /F
echo.
echo  Se quiser desligar o gravador agora, feche a janela preta do SMI.
echo.
pause
