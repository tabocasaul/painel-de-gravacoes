param(
    [switch] $NaoInstalarDependencias,
    [switch] $Diagnostico
)

$ErrorActionPreference = 'Stop'
$raiz = Split-Path -Parent $MyInvocation.MyCommand.Path
$entrada = Join-Path $raiz 'camvideo\modern_server.pyw'
$dist = Join-Path $raiz 'dist'
$work = Join-Path $raiz 'build\pyinstaller'
$buildName = if ($Diagnostico) { 'CameraEmuladorDiagnostico' } else { 'CameraEmulador' }
$windowMode = if ($Diagnostico) { '--console' } else { '--windowed' }

if (-not $NaoInstalarDependencias) {
    python -m pip install --disable-pip-version-check --quiet 'pyinstaller>=6.0,<7.0'
    if ($LASTEXITCODE -ne 0) { throw 'Nao foi possivel instalar o PyInstaller.' }
}

python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    $windowMode `
    --name $buildName `
    --distpath $dist `
    --workpath $work `
    --specpath (Join-Path $work 'spec') `
    --add-data "$(Join-Path $raiz 'camvideo\montar.py');." `
    --add-data "$(Join-Path $raiz 'camvideo\instalar-videocam.ps1');." `
    --add-data "$(Join-Path $raiz 'camvideo\controlar-videocam.ps1');." `
    --add-data "$(Join-Path $raiz 'camvideo\painel.pyw');." `
    --add-data "$(Join-Path $raiz 'camvideo\shared-camera.sh');." `
    --add-data "$(Join-Path $raiz 'camvideo\web');web" `
    --add-data "$(Join-Path $raiz 'camvideo\voice_worker.py');." `
    --hidden-import montar `
    --hidden-import tkinter `
    --hidden-import tkinter.filedialog `
    --hidden-import tkinter.messagebox `
    --hidden-import tkinter.simpledialog `
    --hidden-import tkinter.ttk `
    $entrada

if ($LASTEXITCODE -ne 0) { throw 'A criacao do executavel falhou.' }

$videos = Join-Path $dist 'videos'
New-Item -ItemType Directory -Path $videos -Force | Out-Null
Write-Host "Executavel pronto: $(Join-Path $dist 'CameraEmulador.exe')"
