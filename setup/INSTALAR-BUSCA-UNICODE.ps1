$ErrorActionPreference = 'Stop'
$searchRuntime = Join-Path $env:LOCALAPPDATA 'emulation-cam/automation-runtime'
python -m pip install --upgrade --target $searchRuntime 'uiautomator2==3.7.0'
if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar a busca com Unicode.' }
Write-Host 'Busca pelo nome completo com cedilha e acentos instalada.'
