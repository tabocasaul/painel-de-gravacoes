@echo off
setlocal
cd /d "%~dp0"
where pythonw.exe >nul 2>nul
if not errorlevel 1 (
  start "" pythonw.exe "camvideo\modern_server.pyw"
  exit /b 0
)
echo Python nao encontrado. Execute setup\01-ferramentas.ps1.
pause
exit /b 1
