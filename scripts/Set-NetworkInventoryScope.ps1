# Correct an earlier exhaustive declaration without changing token, addresses or CIDRs.
[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'ProtectedState.ps1')
$privateRoot=Get-ArcIAStateRoot
try {
    $path=Join-Path $privateRoot 'instance.dpapi'
    $bundle=(Read-ProtectedBundle $path)|ConvertFrom-Json
    $bundle.endpoint_design.enterprise_vpn_cidrs_attested=$false
    foreach($entry in @(@('inventory_scope','current_underlay_and_known_routes'),
        @('future_networks_unknown',$true),@('vpn_activation_requires_route_guard',$true))){
        $bundle.endpoint_design|Add-Member -NotePropertyName $entry[0] -NotePropertyValue $entry[1] -Force
    }
    $bundle.config.network.existing_cidrs_reviewed=$false
    $bundle.config.gates.network_review='pending'
    $temporary=Join-Path $privateRoot ('network-scope-'+[guid]::NewGuid().ToString('N')+'.dpapi')
    Save-ProtectedBundle $temporary ($bundle|ConvertTo-Json -Depth 20 -Compress)
    [IO.File]::Replace($temporary,$path,[NullString]::Value)
    Write-Output 'KNOWN_NETWORK_SCOPE_RECORDED; NETWORK_GATE_PENDING; NO_DEPLOYMENT'
}catch{Write-Output 'NETWORK_SCOPE_UPDATE_FAILED';exit 2}
finally{$bundle=$null}
