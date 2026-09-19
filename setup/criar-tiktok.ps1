$avdNameTikTok = 'TikTokAtual'
$imageTikTok = 'system-images;android-36;google_apis_playstore;x86_64'
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/comum.ps1"
Preparar-Java | Out-Null
$sdkTikTok = Join-Path $env:LOCALAPPDATA 'Android/Sdk'
$env:ANDROID_SDK_ROOT = $sdkTikTok
$env:ANDROID_HOME = $sdkTikTok
$avdTikTok = Join-Path $env:USERPROFILE ".android/avd/$avdNameTikTok.avd"
if (Test-Path -LiteralPath $avdTikTok) {
    throw "$avdNameTikTok ja existe. Nenhum dado foi substituido."
}
& "$sdkTikTok/cmdline-tools/latest/bin/sdkmanager.bat" $imageTikTok
if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar a imagem Android.' }
'no' | & "$sdkTikTok/cmdline-tools/latest/bin/avdmanager.bat" create avd -n $avdNameTikTok -k $imageTikTok -d pixel_5
if ($LASTEXITCODE -ne 0) { throw "Falha ao criar $avdNameTikTok." }
$configTikTok = Join-Path $avdTikTok 'config.ini'
$configText = Get-Content -LiteralPath $configTikTok -Raw
foreach ($entry in @{
    'hw.ramSize'='4096'; 'hw.cpu.ncore'='2'; 'disk.dataPartition.size'='32G';
    'hw.lcd.width'='720'; 'hw.lcd.height'='1280'; 'hw.lcd.density'='320';
    'hw.gpu.enabled'='yes'; 'hw.gpu.mode'='auto'; 'hw.keyboard'='yes';
    'avd.ini.displayname'='TikTok Android 16'; 'fastboot.forceColdBoot'='yes'
}.GetEnumerator()) {
    $patternTikTok = '(?m)^' + [regex]::Escape($entry.Key) + '\s*=.*$'
    $newLineTikTok = $entry.Key + '=' + $entry.Value
    if ($configText -match $patternTikTok) { $configText = [regex]::Replace($configText, $patternTikTok, $newLineTikTok) }
    else { $configText += "`n$newLineTikTok`n" }
}
[IO.File]::WriteAllText($configTikTok, $configText)
Write-Host "$avdNameTikTok criado."
