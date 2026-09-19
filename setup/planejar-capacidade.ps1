param(
    [ValidateRange(1, 100)]
    [int] $Celulares = 3,
    [ValidateRange(1, 720)]
    [int] $DuracaoVideoMinutos = 3
)

$ErrorActionPreference = 'Stop'

# Medidas observadas no PC de referencia em 08/09/2026:
# SDK 4,39 GB; cada AVD 12,10 GB; modelo-base 8,10 GB.
# I420 640x360/30 fps usa 10.368.000 bytes/s, aproximadamente 0,58 GiB/min.
$fixoGB = 28.0
$avdsGB = 13.0 * $Celulares
$videoGB = 0.60 * $DuracaoVideoMinutos * ($Celulares + 1)
$recomendadoGB = [math]::Ceiling((($fixoGB + $avdsGB + $videoGB) * 1.15) / 5) * 5
$ramBaseGB = [math]::Max(16, 8 + (3 * $Celulares))
$ramGB = [math]::Ceiling($ramBaseGB / 16) * 16
$nucleos = [math]::Max(8, [math]::Ceiling($Celulares / 2) * 2)

Write-Host "`nPlanejamento para $Celulares celular(es) e video de $DuracaoVideoMinutos min" -ForegroundColor Cyan
Write-Host ('-' * 68)
Write-Host ("Ferramentas, SDK e modelo-base : {0,8:N0} GB" -f $fixoGB)
Write-Host ("Celulares no disco             : {0,8:N0} GB" -f $avdsGB)
Write-Host ("Video I420 local + aparelhos   : {0,8:N1} GB" -f $videoGB)
Write-Host ("SSD livre recomendado          : {0,8:N0} GB" -f $recomendadoGB) -ForegroundColor Green
Write-Host ("RAM recomendada para simultaneo: {0,8:N0} GB" -f $ramGB)
Write-Host ("Nucleos/logical CPUs sugeridos : {0,8:N0}+" -f $nucleos)
Write-Host ('-' * 68)
Write-Host 'A RAM e uma estimativa conservadora. Meca o uso real antes de ampliar.' -ForegroundColor DarkGray
Write-Host 'Para 50 celulares, use uma workstation/servidor; um desktop comum nao comporta.' -ForegroundColor Yellow

[pscustomobject]@{
    Celulares = $Celulares
    DuracaoVideoMinutos = $DuracaoVideoMinutos
    DiscoLivreRecomendadoGB = $recomendadoGB
    RamRecomendadaGB = $ramGB
    NucleosSugeridos = $nucleos
}
