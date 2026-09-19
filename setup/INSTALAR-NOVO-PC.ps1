param(
    [ValidateRange(1, 100)]
    [int] $CelularesPlanejados = 3,
    [ValidateRange(1, 720)]
    [int] $DuracaoVideoMinutos = 3
)

$ErrorActionPreference = 'Stop'
$raiz = Split-Path -Parent $PSScriptRoot

Write-Host "`n=== EMULATION CONTROL - INSTALACAO DO PC NOVO ===" -ForegroundColor Cyan
Write-Host 'Este script instala as ferramentas e cria o primeiro celular.'
Write-Host 'Login Google, instalacao do Minute e autorizacao Magisk continuam manuais.' -ForegroundColor Yellow

if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) {
    throw 'winget nao encontrado. Atualize o App Installer pela Microsoft Store.'
}

$vt = (Get-CimInstance Win32_Processor | Select-Object -First 1).VirtualizationFirmwareEnabled
if (-not $vt) {
    Write-Host 'O Windows nao confirmou VT-x/SVM pelo firmware. O teste definitivo do emulador sera feito depois de instalar o SDK.' -ForegroundColor Yellow
}

$fixoGB = 28.0
$necessarioGB = [math]::Ceiling((($fixoGB + 13.0 * $CelularesPlanejados + 0.60 * $DuracaoVideoMinutos * ($CelularesPlanejados + 1)) * 1.15) / 5) * 5
$drive = Get-PSDrive -Name ([System.IO.Path]::GetPathRoot($raiz).Substring(0, 1))
$livreGB = [math]::Floor($drive.Free / 1GB)
Write-Host "Disco livre: $livreGB GB | recomendado para seu plano: $necessarioGB GB"
if ($livreGB -lt $necessarioGB) {
    throw "Espaco insuficiente. Libere pelo menos $($necessarioGB - $livreGB) GB antes de continuar."
}

& (Join-Path $PSScriptRoot 'planejar-capacidade.ps1') -Celulares $CelularesPlanejados -DuracaoVideoMinutos $DuracaoVideoMinutos | Out-Host
& (Join-Path $PSScriptRoot '01-ferramentas.ps1')

$emulator = Join-Path $env:LOCALAPPDATA 'Android\Sdk\emulator\emulator.exe'
$acel = & $emulator -accel-check 2>&1 | Out-String
if ($acel -notmatch 'is installed and usable|WHPX .*installed|HAXM version') {
    Write-Host @"

As ferramentas foram instaladas, mas o hipervisor ainda nao esta pronto.
No PowerShell COMO ADMINISTRADOR execute:

  dism /online /enable-feature /featurename:HypervisorPlatform /all /norestart

Reinicie o Windows e rode este instalador novamente. Ele pulara o que ja existe.
"@ -ForegroundColor Yellow
    exit 2
}

& (Join-Path $PSScriptRoot 'INSTALAR-BUSCA-UNICODE.ps1')
& (Join-Path $PSScriptRoot '02-criar-avd.ps1')

Write-Host @"

Primeira etapa concluida.

Agora siga a secao 'Passo a passo no PC novo' do README.md:
  1. Abra o MinutePlay e entre na Play Store.
  2. Instale o Minute Data, mas NAO entre na conta Minute ainda.
  3. No Git Bash, rode setup/03-rootear.sh e setup/04-modulos.sh.
  4. Crie o modelo-base com setup/05-criar-template.ps1 -Origem MinutePlay.
  5. Abra novamente e entre na conta Minute do primeiro celular.
  6. Execute ABRIR-TUDO.bat.
"@ -ForegroundColor Green
