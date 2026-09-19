param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('iniciar', 'pausar', 'reiniciar')]
    [string] $Acao,
    [ValidatePattern('^emulator-\d+$')]
    [string] $Serial = 'emulator-5554'
)

$ErrorActionPreference = 'Stop'
$adb = Join-Path $env:LOCALAPPDATA 'Android\Sdk\platform-tools\adb.exe'
$control = '/data/adb/modules/videocam/system/vendor/etc/config/emu_camera_control.txt'

& $adb -s $Serial get-state 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Emulador fechado. Abra o MinutePlay primeiro.' }
$current = [string] (& $adb -s $Serial shell su -c "cat $control" 2>$null | Select-Object -First 1)
$current = $current.Trim()
$generation = 0
if ($current -match '^(play|pause)\s+(\d+)$') {
    $generation = [uint64] $Matches[2]
}

switch ($Acao) {
    'pausar'   { $state = 'pause' }
    'iniciar'  { $state = 'play' }
    'reiniciar' { $state = 'play'; $generation++ }
}

$rootCommand = "printf '%s\n' '$state $generation' > $control; chown 0:0 $control; chcon u:object_r:system_file:s0 $control; chmod 644 $control"
$rootCommand | & $adb -s $Serial shell su
if ($LASTEXITCODE -ne 0) { throw 'Nao foi possivel controlar o video no emulador.' }
Write-Host "$state $generation"
