. 'C:\Users\NicolasTHEUIL\OneDrive - Arcitek\Projets\arcia\scripts\ProtectedState.ps1'
$root = Get-ArcIAStateRoot
$target = (Read-ProtectedBundle (Join-Path $root 'vmware-target.dpapi')) | ConvertFrom-Json
$target | ConvertTo-Json -Depth 10