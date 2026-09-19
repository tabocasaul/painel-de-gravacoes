$ErrorActionPreference = 'Stop'
$voiceRuntime = Join-Path $env:LOCALAPPDATA 'emulation-cam\omnivoice-runtime'
$voicePython = Join-Path $voiceRuntime 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $voicePython)) {
    python -m venv $voiceRuntime
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao criar ambiente da voz.' }
}
& $voicePython -m pip install --disable-pip-version-check torch==2.8.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cu128
if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar PyTorch com CUDA.' }
& $voicePython -m pip install --disable-pip-version-check -r (Join-Path $PSScriptRoot 'omnivoice-requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar bibliotecas da voz.' }
& $voicePython (Join-Path $PSScriptRoot 'omnivoice_assets.py')
if ($LASTEXITCODE -ne 0) { throw 'Falha ao baixar os arquivos da voz.' }
& $voicePython (Join-Path $PSScriptRoot '..\camvideo\voice_worker.py') --check
if ($LASTEXITCODE -ne 0) { throw 'O teste da voz falhou.' }
Write-Host 'Voz local instalada. Abra TikTok Lives no painel.'
