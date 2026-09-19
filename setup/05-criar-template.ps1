param(
    [string] $Origem = 'MinutePlay2'
)

$ErrorActionPreference = 'Stop'
$avdHome = Join-Path $env:USERPROFILE '.android\avd'
$origemDir = Join-Path $avdHome ($Origem + '.avd')
$templateRoot = Join-Path $env:LOCALAPPDATA 'EmulationCamera'
$destino = Join-Path $templateRoot 'MinuteTemplate.avd'
$adb = Join-Path $env:LOCALAPPDATA 'Android\Sdk\platform-tools\adb.exe'

if (-not (Test-Path -LiteralPath $origemDir -PathType Container)) {
    throw "AVD de origem nao encontrado: $origemDir"
}
if (Test-Path -LiteralPath $destino) {
    throw "O modelo-base ja existe: $destino"
}

$indice = if ($Origem -eq 'MinutePlay') { 1 } elseif ($Origem -match '^MinutePlay(\d+)$') { [int]$Matches[1] } else { 0 }
if ($indice -lt 1) { throw 'Use um AVD MinutePlay, MinutePlay2, MinutePlay3...' }
$serial = 'emulator-' + (5554 + ($indice - 1) * 2)

# O modelo nunca deve carregar a sessao de uma conta Minute. A conta Google e
# a Play Store nao sao tocadas.
& $adb -s $serial get-state 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) {
    & $adb -s $serial shell pm clear com.bakerdata.minute | Out-Null
    & $adb -s $serial emu kill | Out-Null
    Start-Sleep -Seconds 8
}

New-Item -ItemType Directory -Path $templateRoot -Force | Out-Null
New-Item -ItemType Directory -Path $destino -Force | Out-Null

& robocopy $origemDir $destino /E /R:2 /W:2 /NFL /NDL /NJH /NJS /NP `
    /XF hardware-qemu.ini emu-launch-params.txt *.lock `
    /XD snapshots tmpAdbCmds | Out-Host
if ($LASTEXITCODE -ge 8) { throw "Falha ao criar o modelo-base (robocopy $LASTEXITCODE)." }

Write-Host "Modelo-base pronto: $destino"
Write-Host 'O botao + ADICIONAR CELULAR ja pode criar novos aparelhos.'
