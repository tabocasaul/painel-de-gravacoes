$ErrorActionPreference = 'Continue'
$sdk = Join-Path $env:LOCALAPPDATA 'Android\Sdk'
$avdHome = Join-Path $env:USERPROFILE '.android\avd'
$template = Join-Path $env:LOCALAPPDATA 'EmulationCamera\MinuteTemplate.avd'
$falhas = 0

function Testar($nome, $ok, $detalhe = '') {
    if ($ok) { Write-Host "[OK]    $nome $detalhe" -ForegroundColor Green }
    else { Write-Host "[FALTA] $nome $detalhe" -ForegroundColor Red; $script:falhas++ }
}

Write-Host "`n=== DIAGNOSTICO EMULATION CONTROL ===" -ForegroundColor Cyan
$vt = (Get-CimInstance Win32_Processor | Select-Object -First 1).VirtualizationFirmwareEnabled
$acelOk = $false
if (Test-Path "$sdk\emulator\emulator.exe") {
    $acel = & "$sdk\emulator\emulator.exe" -accel-check 2>&1 | Out-String
    $acelOk = $acel -match 'is installed and usable|WHPX .*installed|HAXM version'
}
Testar 'Virtualizacao disponivel' ($vt -or $acelOk)
Testar 'Git' ([bool](Get-Command git.exe -ErrorAction SilentlyContinue))
Testar 'Python 3.12' (Test-Path "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe")
Testar 'ffmpeg' ([bool](Get-Command ffmpeg.exe -ErrorAction SilentlyContinue))
Testar 'ADB' (Test-Path "$sdk\platform-tools\adb.exe")
Testar 'Android Emulator' (Test-Path "$sdk\emulator\emulator.exe")
Testar 'Imagem Android 13 + Play Store' (Test-Path "$sdk\system-images\android-33\google_apis_playstore\x86_64\system.img")
Testar 'Primeiro AVD MinutePlay' (Test-Path "$avdHome\MinutePlay.avd")

if (Test-Path "$sdk\emulator\emulator.exe") { Testar 'Aceleracao do emulador' $acelOk }

if (Test-Path $template) { Write-Host '[OK]    Modelo-base para adicionar celulares' -ForegroundColor Green }
else { Write-Host '[AVISO] Modelo-base ainda nao criado; o primeiro celular pode funcionar normalmente.' -ForegroundColor Yellow }

$adb = "$sdk\platform-tools\adb.exe"
if (Test-Path $adb) {
    $seriais = & $adb devices | Select-String '^emulator-\d+\s+device$' | ForEach-Object { ($_.Line -split '\s+')[0] }
    foreach ($serial in $seriais) {
        $root = (& $adb -s $serial shell 'su -c id' 2>$null | Out-String) -match 'uid=0'
        Testar "$serial com root Magisk" $root
        $hal = (& $adb -s $serial shell "su -c 'test -f /data/adb/modules/videocam/system/vendor/lib64/libgooglecamerahwl_impl.so && echo ok'" 2>$null | Out-String) -match 'ok'
        Testar "$serial com HAL de video" $hal
    }
    if (-not $seriais) { Write-Host '[AVISO] Nenhum emulador ligado; verificacoes internas foram puladas.' -ForegroundColor Yellow }
}

if ($falhas) {
    Write-Host "`nDiagnostico terminou com $falhas pendencia(s)." -ForegroundColor Red
    exit 1
}
Write-Host "`nAmbiente essencial pronto." -ForegroundColor Green
