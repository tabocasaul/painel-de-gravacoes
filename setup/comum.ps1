# Funcoes compartilhadas pelos scripts de setup.
# Use com dot-source, para as funcoes virem para o escopo de quem chama:
#
#   . "$PSScriptRoot\comum.ps1"
#
# Tudo aqui existe por causa da mesma armadilha: o winget instala com --silent,
# o PATH do processo atual nao e atualizado, e falha de .exe/.bat nativo NAO
# dispara o $ErrorActionPreference = "Stop". A combinacao faz o script seguir
# adiante achando que deu certo.

# O winget escreve o PATH novo no registro, mas o processo atual continua com o
# PATH antigo. Sem recarregar, nada que foi instalado agora e visivel aqui.
function Recarregar-Path {
    $maquina = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $usuario = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = @($maquina, $usuario | Where-Object { $_ }) -join ";"
}

# Num Windows limpo, "python" no PATH e o atalho da Microsoft Store
# (%LOCALAPPDATA%\Microsoft\WindowsApps\python.exe, um stub de 0 byte que abre a
# loja). Chamar "python -m pip" logo depois do winget cai nele, e o script
# seguia sem instalar nada -- o camvideo.py so quebrava muito depois com
# ModuleNotFoundError.
function Achar-Python {
    Recarregar-Path
    $candidatos = @("$env:LOCALAPPDATA\Programs\Python\Python312\python.exe")
    foreach ($raiz in "$env:LOCALAPPDATA\Programs\Python", "$env:ProgramFiles") {
        $candidatos += Get-ChildItem "$raiz\Python3*\python.exe" -ErrorAction SilentlyContinue |
                       Sort-Object FullName -Descending | ForEach-Object { $_.FullName }
    }
    $candidatos += Get-Command python.exe -All -ErrorAction SilentlyContinue |
                   ForEach-Object { $_.Source }

    foreach ($c in $candidatos) {
        if (-not $c) { continue }
        if ($c -like "*\WindowsApps\*") { continue }          # stub da Store
        if (-not (Test-Path $c)) { continue }
        if ((Get-Item $c).Length -eq 0) { continue }          # stub tem 0 byte
        return $c
    }
    return $null
}

# O winget instala o Temurin com --silent, e nesse modo o MSI NAO poe o java no
# PATH nem cria o JAVA_HOME (sao features opcionais, desligadas por padrao).
# Todo .bat do SDK -- sdkmanager, avdmanager, apksigner -- morre no ato com
# "JAVA_HOME is not set", e o javac/keytool do lentes/build.sh tambem.
function Achar-Java {
    if ($env:JAVA_HOME -and (Test-Path "$env:JAVA_HOME\bin\java.exe")) {
        return $env:JAVA_HOME
    }
    $raizes = @(
        "$env:ProgramFiles\Eclipse Adoptium",
        "${env:ProgramFiles(x86)}\Eclipse Adoptium",
        "$env:LOCALAPPDATA\Programs\Eclipse Adoptium",
        "$env:ProgramFiles\Java"
    )
    foreach ($r in $raizes) {
        $achado = Get-ChildItem "$r\jdk*" -Directory -ErrorAction SilentlyContinue |
                  Where-Object { Test-Path "$($_.FullName)\bin\java.exe" } |
                  Sort-Object Name -Descending | Select-Object -First 1
        if ($achado) { return $achado.FullName }
    }
    $cmd = Get-Command java.exe -ErrorAction SilentlyContinue
    if ($cmd) { return (Split-Path (Split-Path $cmd.Source -Parent) -Parent) }
    return $null
}

# Acha o JDK e ja deixa o ambiente pronto. Aborta com mensagem util se nao tiver.
function Preparar-Java {
    $jdk = Achar-Java
    if (-not $jdk) {
        Write-Host @"

  Nao achei um JDK. Nenhuma ferramenta do SDK roda sem Java.

  Confira se o Temurin 21 entrou:
      winget list --id EclipseAdoptium.Temurin.21.JDK
  e onde ele foi parar (normalmente C:\Program Files\Eclipse Adoptium\jdk-21...).
  Se faltar, rode o 01-ferramentas.ps1 primeiro.
"@ -ForegroundColor Red
        exit 1
    }
    $env:JAVA_HOME = $jdk
    if ($env:Path -notlike "*$jdk\bin*") { $env:Path = "$jdk\bin;$env:Path" }
    return $jdk
}
