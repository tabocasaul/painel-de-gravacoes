$ErrorActionPreference = 'Stop'
$pythonTikTok = Join-Path $env:LOCALAPPDATA 'emulation-cam/omnivoice-runtime/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonTikTok)) { throw 'Instale primeiro o ambiente de voz local.' }
& $pythonTikTok -m pip install pyvirtualcam==0.15.0 pycaw==20251023
if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar dependencias de video.' }
& $pythonTikTok -m pip install --no-deps opencv-python-headless==4.11.0.86
if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar conversor de imagem.' }
Write-Host 'Instale o driver com setup/INSTALAR-TIKTOK-CAMERA.ps1. VB-CABLE tambem precisa estar instalado no Windows.'
