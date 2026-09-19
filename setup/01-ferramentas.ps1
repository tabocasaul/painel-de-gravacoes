# 01 - Instala as ferramentas base e o SDK do Android.
# Rode no PowerShell. Nao precisa ser administrador (o winget instala no usuario).
#
#   powershell -ExecutionPolicy Bypass -File .\01-ferramentas.ps1

$ErrorActionPreference = "Stop"
$SDK = "$env:LOCALAPPDATA\Android\Sdk"

. "$PSScriptRoot\comum.ps1"

function Passo($t) { Write-Host "`n=== $t ===" -ForegroundColor Cyan }

Passo "Ferramentas base (Git, JDK e Python)"
# JDK: o sdkmanager e o javac precisam dele. Python: roda o camvideo.py.
winget install --id Git.Git -e --accept-source-agreements --accept-package-agreements --silent
winget install --id EclipseAdoptium.Temurin.21.JDK -e --accept-source-agreements --accept-package-agreements --silent
winget install --id Python.Python.3.12 -e --accept-package-agreements --silent

Passo "Conferindo o Python"
$py = Achar-Python
if (-not $py) {
    Write-Host @"

  Nao achei um python.exe utilizavel.

  O winget pode ter pedido reinicio, ou o unico "python" do PATH e o atalho da
  Microsoft Store. Abra um PowerShell NOVO, confira com

      (Get-Command python).Source

  e, se apontar para ...\WindowsApps\, desligue o alias em
  Configuracoes > Aplicativos > Configuracoes avancadas > Aliases de execucao.
  Depois rode este script de novo.
"@ -ForegroundColor Red
    exit 1
}
Write-Host "  usando $py"
& $py -m pip install --upgrade pip

Passo "Ferramentas de linha de comando do Android"
$cmdlineZip = "$env:TEMP\cmdline-tools.zip"
$destino = "$SDK\cmdline-tools"
if (-not (Test-Path "$destino\latest\bin\sdkmanager.bat")) {
    New-Item -ItemType Directory -Force -Path $destino | Out-Null
    Invoke-WebRequest -Uri "https://dl.google.com/android/repository/commandlinetools-win-11076708_latest.zip" -OutFile $cmdlineZip
    Expand-Archive -Path $cmdlineZip -DestinationPath $destino -Force
    # o zip extrai como "cmdline-tools"; o sdkmanager exige que esteja em "latest"
    if (Test-Path "$destino\cmdline-tools") {
        Move-Item "$destino\cmdline-tools" "$destino\latest" -Force
    }
    Remove-Item $cmdlineZip -Force
} else {
    Write-Host "ja instalado, pulando"
}

Passo "Componentes do SDK (demora, sao alguns GB)"
$sdkmanager = "$SDK\cmdline-tools\latest\bin\sdkmanager.bat"
$env:ANDROID_SDK_ROOT = $SDK
$env:ANDROID_HOME = $SDK

# sem isso o sdkmanager.bat nao acha o java e o passo inteiro falha calado
$jdk = Preparar-Java
Write-Host "  JAVA_HOME = $jdk"

# build-tools 37: as versoes antigas (34) quebram com class files de JDK novo,
# o d8 estoura NullPointerException ao ler classe anonima.
# As licencas travam a instalacao se nao forem aceitas antes.
#
# ARMADILHA: `$texto | & $sdkmanager` NAO funciona. O sdkmanager.bat e um
# wrapper que chama java, e o pipe do PowerShell nao entrega o stdin ate la: o
# prompt "Review licenses that have not been accepted (y/N)?" le EOF e recusa
# tudo. O sintoma e "7 of 7 SDK package licenses not accepted", seguido de
# "Skipping following packages as the license is not accepted" em cada pacote
# -- e o sdkmanager SAI 0 assim mesmo. Redirecionar um arquivo pelo cmd entrega.
Write-Host "  aceitando licencas"
$sim = Join-Path $env:TEMP "sdk-yes.txt"
(1..100 | ForEach-Object { "y" }) -join "`r`n" | Set-Content $sim -Encoding ASCII
cmd /c "`"$sdkmanager`" --sdk_root=`"$SDK`" --licenses < `"$sim`""
if (-not (Test-Path "$SDK\licenses\android-sdk-license")) {
    Write-Host "  ERRO: as licencas do SDK nao foram aceitas." -ForegroundColor Red
    exit 1
}

$pacotes = @(
    "platform-tools",
    "emulator",
    "platforms;android-34",
    "build-tools;37.0.0",
    "system-images;android-33;google_apis_playstore;x86_64",
    # driver de aceleracao: sem hipervisor o emulador x86_64 nao sobe, morre com
    # "x86_64 emulation currently requires hardware acceleration!". Baixar da
    # para fazer aqui; INSTALAR precisa de admin -- ver o aviso no fim do script.
    "extras;google;Android_Emulator_Hypervisor_Driver"
)
foreach ($p in $pacotes) {
    Write-Host "  instalando $p"
    cmd /c "`"$sdkmanager`" --sdk_root=`"$SDK`" `"$p`" < `"$sim`""
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  ERRO: falhou ao instalar '$p' (codigo $LASTEXITCODE)." -ForegroundColor Red
        exit 1
    }
}

# confere no disco: sdkmanager ja saiu 0 sem ter baixado nada
Write-Host "  conferindo o que chegou no disco"
$esperado = @{
    "platform-tools"                                    = "platform-tools\adb.exe"
    "emulator"                                          = "emulator\emulator.exe"
    "platforms;android-34"                              = "platforms\android-34\android.jar"
    "build-tools;37.0.0"                                = "build-tools\37.0.0\d8.bat"
    "system-images;android-33;google_apis_playstore;x86_64" = "system-images\android-33\google_apis_playstore\x86_64\system.img"
    "extras;google;Android_Emulator_Hypervisor_Driver"  = "extras\google\Android_Emulator_Hypervisor_Driver\silent_install.bat"
}
$faltando = @()
foreach ($p in $esperado.Keys) {
    if (Test-Path "$SDK\$($esperado[$p])") {
        Write-Host "    ok  $p"
    } else {
        Write-Host "    FALTANDO  $p" -ForegroundColor Red
        $faltando += $p
    }
}
if ($faltando) {
    Write-Host "`n  ERRO: $($faltando.Count) pacote(s) do SDK nao chegaram no disco." -ForegroundColor Red
    exit 1
}

Passo "ffmpeg"
# A versao atual usa video pre-gravado diretamente na HAL customizada.
# OBS, DroidCam e Iriun nao sao necessarios para esse fluxo.
$programas = @(
    @{ id = "Gyan.FFmpeg";                   nome = "ffmpeg" }
)
foreach ($prog in $programas) {
    Write-Host "  instalando $($prog.nome)"
    winget install --id $($prog.id) -e --accept-package-agreements --accept-source-agreements --silent
}

Write-Host @"

  OPCIONAL - NAO USADO PELO PAINEL ATUAL:

    Iriun Webcam  ->  https://iriun.com/
    (baixe o cliente de Windows e o app no celular)

  Iriun e OBS pertencem ao experimento antigo de camera ao vivo.
  Para os videos pre-gravados deste projeto, nao instale nenhum deles.

  Se decidir testar o fluxo antigo, instale o OBS separadamente e ligue:
      OBS > Ferramentas > Configuracoes do WebSocket > ativar servidor
  O camvideo.py le a senha sozinho de
      %APPDATA%\obs-studio\plugin_config\obs-websocket\config.json
"@ -ForegroundColor Yellow

Passo "PATH"
# o bin do JDK entra junto: o lentes/build.sh chama javac e keytool pelo PATH,
# e o winget --silent nao os coloca la.
$novos = "$SDK\platform-tools", "$SDK\emulator", "$jdk\bin"
$atual = [Environment]::GetEnvironmentVariable("Path", "User")
foreach ($n in $novos) {
    if ($atual -notlike "*$n*") {
        $atual = "$atual;$n"
    }
}
[Environment]::SetEnvironmentVariable("Path", $atual, "User")
[Environment]::SetEnvironmentVariable("ANDROID_SDK_ROOT", $SDK, "User")
[Environment]::SetEnvironmentVariable("ANDROID_HOME", $SDK, "User")
[Environment]::SetEnvironmentVariable("JAVA_HOME", $jdk, "User")

Passo "Aceleracao por hardware"
# O emulador x86_64 nao sobe sem hipervisor -- morre com "x86_64 emulation
# currently requires hardware acceleration!". Instalar o driver exige admin,
# entao este script so diagnostica e diz o que fazer.
$acel = & "$SDK\emulator\emulator.exe" -accel-check 2>&1 | Out-String
if ($acel -match "is installed and usable|HAXM version|WHPX .*installed") {
    Write-Host "  ok, aceleracao disponivel" -ForegroundColor Green
} else {
    $vt = (Get-CimInstance Win32_Processor | Select-Object -First 1).VirtualizationFirmwareEnabled
    Write-Host "  SEM aceleracao. O emulador nao vai subir." -ForegroundColor Yellow
    Write-Host "  VirtualizationFirmwareEnabled = $vt"

    if (-not $vt) {
        Write-Host @"

  A virtualizacao esta DESLIGADA no firmware. Entre no BIOS/UEFI e ligue
  VT-x (Intel) ou SVM/AMD-V (AMD). Sem isso nao ha o que fazer no Windows,
  nem com WHPX nem com AEHD.
"@ -ForegroundColor Yellow
    } else {
        # WHPX e AEHD sao mutuamente exclusivos. Se Hyper-V, WSL2, Sandbox ou a
        # Integridade de memoria estiverem ativos, o AEHD instala e o driver NAO
        # carrega -- fica 0% de CPU e um driver kernel a mais no sistema. Entao
        # so sugerimos o AEHD depois de confirmar que o campo esta livre.
        $hyperv = [bool](Get-Service vmcompute, vmms -ErrorAction SilentlyContinue)
        $hvci = [bool](Get-CimInstance Win32_DeviceGuard -Namespace root\Microsoft\Windows\DeviceGuard `
                        -ErrorAction SilentlyContinue).SecurityServicesRunning
        $present = (Get-CimInstance Win32_ComputerSystem).HypervisorPresent
        $pro = (Get-CimInstance Win32_OperatingSystem).Caption -notmatch "Home"

        Write-Host "  Hyper-V/WSL2 presente : $hyperv"
        Write-Host "  Integridade de memoria: $hvci"
        Write-Host "  Edicao Pro/Enterprise : $pro"

        if ($pro) {
            Write-Host @"

  Caminho recomendado: WHPX (recurso do Windows, sem driver de terceiros).
  Num PowerShell COMO ADMINISTRADOR:

      dism /online /enable-feature /featurename:HypervisorPlatform /all /norestart

  Reinicie e rode 'emulator -accel-check'.
"@ -ForegroundColor Yellow
        }
        if ($hyperv -or $hvci -or $present) {
            Write-Host @"

  NAO use o AEHD nesta maquina: ja existe hipervisor/Integridade de memoria
  ativo. O instalador passa, mas o driver nao carrega e o emulador continua
  travado. Use o WHPX acima.
"@ -ForegroundColor Red
        } else {
            Write-Host @"

  Alternativa (so se o WHPX nao servir, ex.: Windows Home). O campo esta livre
  -- sem Hyper-V e sem Integridade de memoria. Como ADMINISTRADOR:

      cd "$SDK\extras\google\Android_Emulator_Hypervisor_Driver"
      .\silent_install.bat

  (o pacote ja foi baixado acima).
"@ -ForegroundColor Yellow
        }
    }
}

Write-Host "`nPronto. SDK em $SDK" -ForegroundColor Green
Write-Host "Abra um PowerShell NOVO (pro PATH valer) e rode 02-criar-avd.ps1"
