@echo off
rem Atalho para abrir o painel sem precisar de terminal.
rem Usa pythonw (sem janela preta) e cai no python normal se nao houver.
setlocal
set "PY="
for %%P in ("%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe"
            "%LOCALAPPDATA%\Programs\Python\Python311\pythonw.exe"
            "%LOCALAPPDATA%\Programs\Python\Python312\python.exe") do (
    if not defined PY if exist %%P set "PY=%%~P"
)
if not defined PY (
    echo Nao achei o Python. Rode setup\01-ferramentas.ps1 primeiro.
    pause
    exit /b 1
)
start "" "%PY%" "%~dp0painel.pyw"
