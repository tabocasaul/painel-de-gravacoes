param(
    [Parameter(Mandatory = $true)]
    [string] $Video,
    [ValidatePattern('^emulator-\d+$')]
    [string] $Serial = 'emulator-5554',
    [switch] $I420Pronto
)

$ErrorActionPreference = 'Stop'
$adb = Join-Path $env:LOCALAPPDATA 'Android\Sdk\platform-tools\adb.exe'
$ffmpeg = (Get-Command ffmpeg -ErrorAction Stop).Source
$videoPath = (Resolve-Path -LiteralPath $Video).Path
$safeSerial = $Serial -replace '[^a-zA-Z0-9_-]', '_'
$output = Join-Path $env:TEMP "emu_camera_video_$safeSerial.i420"

# The HAL consumes planar I420 and performs its normal per-request scaling,
# therefore its Camera2 metadata and physical camera identities are unchanged.
if ($I420Pronto) {
    $output = $videoPath
} else {
    & $ffmpeg -y -i $videoPath `
        -vf 'scale=640:360:force_original_aspect_ratio=decrease,pad=640:360:(ow-iw)/2:(oh-ih)/2:black,setsar=1' `
        -r 30 -an -pix_fmt yuv420p -f rawvideo $output
    if ($LASTEXITCODE -ne 0) { throw 'ffmpeg could not create the I420 frame stream.' }
}

& $adb -s $Serial get-state 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Emulador fechado. Abra o MinutePlay antes de enviar o video.' }
& $adb -s $Serial push $output /data/local/tmp/emu_camera_video.i420
if ($LASTEXITCODE -ne 0) { throw 'Falha ao enviar video; verifique o espaco do emulador.' }
$rootScript = @'
mkdir -p /data/adb/modules/videocam/system/vendor/etc/config
mv -f /data/local/tmp/emu_camera_video.i420 /data/adb/modules/videocam/system/vendor/etc/config/emu_camera_video.i420
printf '%s\n' 'play 0' > /data/adb/modules/videocam/system/vendor/etc/config/emu_camera_control.txt
chown 0:0 /data/adb/modules/videocam/system/vendor/etc/config/emu_camera_video.i420 /data/adb/modules/videocam/system/vendor/etc/config/emu_camera_control.txt
chcon u:object_r:system_file:s0 /data/adb/modules/videocam/system/vendor/etc/config/emu_camera_video.i420 /data/adb/modules/videocam/system/vendor/etc/config/emu_camera_control.txt
chmod 644 /data/adb/modules/videocam/system/vendor/etc/config/emu_camera_video.i420 /data/adb/modules/videocam/system/vendor/etc/config/emu_camera_control.txt
'@
$rootScript | & $adb -s $Serial shell su
if ($LASTEXITCODE -ne 0) { throw 'Could not install the I420 stream into the Magisk module.' }

& $adb -s $Serial reboot
if ($LASTEXITCODE -ne 0) { throw 'Video instalado, mas nao foi possivel reiniciar o emulador.' }
Write-Host 'Video instalado. Aguarde o Android reiniciar.'

if (-not $I420Pronto) {
    Remove-Item -LiteralPath $output -Force -ErrorAction SilentlyContinue
}
