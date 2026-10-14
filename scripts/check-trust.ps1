. 'C:\Users\NicolasTHEUIL\OneDrive - Arcitek\Projets\arcia\scripts\ProtectedState.ps1'
$root = Get-ArcIAStateRoot
$trust = (Read-ProtectedBundle (Join-Path $root 'ssh-trust.dpapi')) | ConvertFrom-Json
$trust | ConvertTo-Json -Depth 10