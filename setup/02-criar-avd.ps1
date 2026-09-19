# 02 - Cria o AVD "MinutePlay" com a configuracao que funciona.
#
#   powershell -ExecutionPolicy Bypass -File .\02-criar-avd.ps1

$ErrorActionPreference = "Stop"
$SDK = "$env:LOCALAPPDATA\Android\Sdk"
$env:ANDROID_SDK_ROOT = $SDK
$env:ANDROID_HOME = $SDK
$AVD = "MinutePlay"

. "$PSScriptRoot\comum.ps1"

# o avdmanager.bat tambem e um wrapper que chama java: sem JAVA_HOME ele morre
# com "JAVA_HOME is not set", nao cria o AVD, e como falha de .bat nao dispara o
# $ErrorActionPreference o script seguia ate estourar la na frente, no
# Get-Content do config.ini que nunca chegou a existir.
$jdk = Preparar-Java
Write-Host "JAVA_HOME = $jdk" -ForegroundColor DarkGray
$avdPath = "$env:USERPROFILE\.android\avd\$AVD.avd"

if (Test-Path $avdPath) {
    Write-Host "AVD '$AVD' ja existe em $avdPath" -ForegroundColor Yellow
    $r = Read-Host "Apagar e recriar? (s/N)"
    if ($r -ne "s") { exit }
    Remove-Item -Recurse -Force $avdPath
    Remove-Item -Force "$env:USERPROFILE\.android\avd\$AVD.ini" -ErrorAction SilentlyContinue
}

Write-Host "`n=== Criando o AVD ===" -ForegroundColor Cyan
# A imagem TEM que ser google_apis_playstore: o Minute e protegido por PAIRIP e
# so passa se for instalado pela Play Store com conta logada. Imagem sem Play
# trava no "Something went wrong / Check that Google Play is enabled".
$avdmanager = "$SDK\cmdline-tools\latest\bin\avdmanager.bat"
# stdin por arquivo, nao por pipe: o pipe do PowerShell nao atravessa o .bat ate
# o java (foi o que fazia as licencas do sdkmanager serem todas recusadas).
$nao = Join-Path $env:TEMP "avd-no.txt"
(1..5 | ForEach-Object { "no" }) -join "`r`n" | Set-Content $nao -Encoding ASCII
cmd /c "`"$avdmanager`" create avd -n `"$AVD`" -k `"system-images;android-33;google_apis_playstore;x86_64`" -d pixel_5 < `"$nao`""

$cfg = "$avdPath\config.ini"
if (-not (Test-Path $cfg)) {
    Write-Host @"

  ERRO: o AVD nao foi criado ($cfg nao existe).

  Confira se a system image esta no disco:
      $SDK\system-images\android-33\google_apis_playstore\x86_64\system.img
  Se faltar, rode o 01-ferramentas.ps1 de novo -- ele agora confere isso no fim.
"@ -ForegroundColor Red
    exit 1
}

Write-Host "`n=== Ajustando config.ini ===" -ForegroundColor Cyan
$ajustes = @{
    "hw.camera.back"  = "emulated"     # sintetica: unica fonte que aceita a ultra-wide
    "hw.camera.front" = "webcam0"      # webcam do PC (DroidCam/OBS), se houver
    "hw.keyboard"     = "yes"
    "hw.ramSize"      = "2048"
    "hw.gpu.enabled"  = "yes"
    "hw.gpu.mode"     = "auto"
    "PlayStore.enabled" = "yes"
    "disk.dataPartition.size" = "128G"
    # o avdmanager default e 228M. O AVD que funcionou aqui tinha 512 (esta no
    # MinutePlay-config.ini) -- o Minute e React Native + Expo, nao e leve.
    "vm.heapSize"     = "512"
}
$linhas = Get-Content $cfg
foreach ($k in $ajustes.Keys) {
    $v = $ajustes[$k]
    if ($linhas -match "^$([regex]::Escape($k))\s*=") {
        $linhas = $linhas -replace "^$([regex]::Escape($k))\s*=.*", "$k = $v"
    } else {
        $linhas += "$k = $v"
    }
}
# SEM BOM. `Set-Content -Encoding UTF8` no PowerShell 5.1 escreve os 3 bytes
# EF BB BF na frente do arquivo, e como PlayStore.enabled cai na primeira linha
# (maiuscula ordena antes das minusculas), a chave vira "﻿PlayStore.enabled".
# O emulador nao reconhece, a Play Store fica desligada, e o Minute nao instala
# -- sem nenhuma mensagem de erro. WriteAllLines grava UTF-8 puro.
[System.IO.File]::WriteAllLines($cfg, $linhas, (New-Object System.Text.UTF8Encoding $false))

# confere que os ajustes que importam pegaram mesmo
$final = Get-Content $cfg
$criticos = @{
    "hw.camera.back"    = "emulated"   # sem isso o Minute nao acha a ultra-wide
    "PlayStore.enabled" = "yes"        # sem isso o Minute nao instala (PAIRIP)
}
$ruim = @()
foreach ($k in $criticos.Keys) {
    $linha = $final | Where-Object { $_ -match "^$([regex]::Escape($k))\s*=" } | Select-Object -First 1
    if ($linha -and $linha -match "=\s*$([regex]::Escape($criticos[$k]))\s*$") {
        Write-Host "  ok  $k = $($criticos[$k])"
    } else {
        Write-Host "  RUIM  $k -> '$linha'" -ForegroundColor Red
        $ruim += $k
    }
}
if ($ruim) {
    Write-Host "`nERRO: o config.ini nao ficou como devia." -ForegroundColor Red
    exit 1
}

Write-Host "`nAVD criado." -ForegroundColor Green
Write-Host @"

PROXIMOS PASSOS (manuais, precisam de voce):

  1. Suba o emulador:
       emulator -avd $AVD -no-snapshot -timezone America/Sao_Paulo -gpu auto

  2. Abra a Play Store dentro dele e faca login na sua conta Google.

  3. Instale o Minute PELA PLAY STORE (procure "Minute Data").
     Nao use adb install com os APKs de /apk - eles sao so backup.
     Sideload NAO passa no PAIRIP.

  4. Faca login no Minute.

  5. Rode 03-rootear.sh (no Git Bash) para instalar o Magisk.
"@
