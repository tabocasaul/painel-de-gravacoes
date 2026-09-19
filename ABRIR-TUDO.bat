@echo off
setlocal
cd /d "%~dp0"

where pythonw.exe >nul 2>nul
if not errorlevel 1 if exist "camvideo\modern_server.pyw" (
  start "" pythonw.exe "camvideo\modern_server.pyw" --abrir-tudo
  exit /b 0
)

if exist "dist\CameraEmulador.exe" (
  start "" "dist\CameraEmulador.exe" --abrir-tudo
  exit /b 0
)

echo Nao achei Python nem CameraEmulador.exe.
echo Execute setup\01-ferramentas.ps1.
pause
exit /b 1
