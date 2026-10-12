[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'ProtectedState.ps1')
$root=Get-ArcIAStateRoot
$images=Join-Path $root 'images';Initialize-PrivateDirectory $images
$source=Join-Path $PSScriptRoot 'prepare_debian_image.py'
$linuxSource=(& wsl.exe -e wslpath -a $source).Trim()
$linuxImages=(& wsl.exe -e wslpath -a $images).Trim()
& wsl.exe -e sh -c 'exec "$HOME/.local/share/arcia-validation/bin/python" "$1" --output "$2"' arcia-image $linuxSource $linuxImages
if($LASTEXITCODE -ne 0){throw 'PINNED_DEBIAN_IMAGE_PREPARATION_FAILED'}
