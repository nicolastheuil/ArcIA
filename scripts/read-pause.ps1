. 'C:\Users\NicolasTHEUIL\OneDrive - Arcitek\Projets\arcia\scripts\ProtectedState.ps1'
$result = Read-ProtectedBundle 'C:\Users\NicolasTHEUIL\AppData\Local\ArcIA-Harness\cluster-pause_k3s.dpapi'
$obj = $result | ConvertFrom-Json -Depth 20
$obj | ConvertTo-Json -Depth 20 -Compress