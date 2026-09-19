$ErrorActionPreference = 'Stop'
$cameraInstaller = Join-Path $env:TEMP 'DroidCam.Drivers.7.1.2.exe'
Invoke-WebRequest 'https://github.com/dev47apps/droidcam-obs-virtual-output/releases/download/0.2.2/DroidCam.Drivers.7.1.2.exe' -OutFile $cameraInstaller
$cameraSignature = Get-AuthenticodeSignature -LiteralPath $cameraInstaller
if ($cameraSignature.Status -ne 'Valid' -or $cameraSignature.SignerCertificate.Subject -notmatch 'CN=DEV47 APPS LTD\.') {
    throw 'O instalador nao tem a assinatura valida esperada da DEV47 APPS LTD.'
}
$cameraInstallProcess = Start-Process -FilePath $cameraInstaller -ArgumentList '/S' -Verb RunAs -WindowStyle Hidden -Wait -PassThru
if ($cameraInstallProcess.ExitCode -ne 0) { throw "Instalador encerrou com codigo $($cameraInstallProcess.ExitCode)." }
Write-Host 'Driver instalado. O emulador deve listar DroidCam Video em -webcam-list.'
