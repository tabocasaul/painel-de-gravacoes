@echo off
setlocal
set "EMU=%LOCALAPPDATA%\Android\Sdk\emulator\emulator.exe"

if not exist "%EMU%" (
    echo Android Emulator nao encontrado em:
    echo %EMU%
    pause
    exit /b 1
)

start "MinutePlay" "%EMU%" -avd MinutePlay -port 5554 -no-snapshot -timezone America/Sao_Paulo -camera-back emulated -camera-front emulated -gpu auto
timeout /t 5 /nobreak >nul
start "MinutePlay2" "%EMU%" -avd MinutePlay2 -port 5556 -no-snapshot -timezone America/Sao_Paulo -camera-back emulated -camera-front emulated -gpu auto
