$ErrorActionPreference = 'Stop'
$emulatorTikTok = Join-Path $env:LOCALAPPDATA 'Android/Sdk/emulator/emulator.exe'
$avdTikTok = Join-Path $env:USERPROFILE '.android/avd/TikTokAtual.avd'
if (-not (Test-Path -LiteralPath $emulatorTikTok)) { throw "Emulador nao encontrado: $emulatorTikTok" }
if (-not (Test-Path -LiteralPath $avdTikTok)) { throw 'Execute setup/criar-tiktok.ps1 primeiro.' }
$existingTikTok = Get-CimInstance Win32_Process -Filter "Name='qemu-system-x86_64.exe'" | Where-Object { $_.CommandLine -match '\bTikTokAtual\b' }
if ($existingTikTok) { Write-Host 'TikTokAtual ja esta aberto.'; exit 0 }
$logTikTok = Join-Path $env:LOCALAPPDATA 'emulation-cam'
New-Item -ItemType Directory -Force -Path $logTikTok | Out-Null
Start-Process -FilePath $emulatorTikTok -ArgumentList @('-avd','TikTokAtual','-no-snapshot-load','-no-snapshot-save') -WorkingDirectory (Split-Path $emulatorTikTok) -WindowStyle Hidden -RedirectStandardOutput "$logTikTok/tiktok-atual-startup.log" -RedirectStandardError "$logTikTok/tiktok-atual-error.log"
