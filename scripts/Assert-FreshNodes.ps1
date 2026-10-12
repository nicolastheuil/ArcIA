$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'ProtectedState.ps1')
$root=Get-ArcIAStateRoot
& pwsh -NoProfile -File (Join-Path $PSScriptRoot 'Invoke-ClusterFoundation.ps1') -Action inspect_k3s
if($LASTEXITCODE -ne 0){throw 'FRESH_NODE_INSPECTION_FAILED'}
$status=Get-Content (Join-Path $root 'cluster-inspect_k3s-status.json') -Raw|ConvertFrom-Json
if(@($status.nodes).Count -ne 3 -or @($status.nodes|Where-Object {$_.binary_present -or $_.config_present}).Count){throw 'FRESH_REQUIRES_THREE_EMPTY_NODES_USE_RECONCILE'}
