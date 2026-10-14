$ROOT = 'C:\Users\NicolasTHEUIL\OneDrive - Arcitek\Projets\arcia'
$lock = Get-Content (Join-Path $ROOT 'versions.lock.yaml') -Raw | ConvertFrom-Json
Write-Host "K3s version: $($lock.components.k3s.version)"
Write-Host "K3s installer_url: $($lock.components.k3s.installer_url)"
Write-Host "K3s binary_url: $($lock.components.k3s.binary_url)"
Write-Host "K3s images_url: $($lock.components.k3s.images_url)"