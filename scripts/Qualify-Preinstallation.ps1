[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'ProtectedState.ps1')
$root=Get-ArcIAStateRoot;$mutex=$null
try{
    Initialize-PrivateDirectory $root
    $mutex=[IO.File]::Open((Join-Path $root 'cluster-operation.lock'),[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::Write,[IO.FileShare]::None)
    $operation=(Read-ProtectedBundle (Join-Path $root 'vmware-operation.dpapi'))|ConvertFrom-Json
    $instance=(Read-ProtectedBundle (Join-Path $root 'instance.dpapi'))|ConvertFrom-Json
    if($instance.operation_id -ne $operation.id){throw 'INSTANCE_SCOPE'}
    $proofs=@{}
    foreach($item in @(@('foundation','foundation-inventory.dpapi'),@('network','network-inventory.dpapi'),
        @('service-permissions','service-permissions-inventory.dpapi'),@('cluster-qualify_ports','cluster-qualify_ports.dpapi'),
        @('cluster-qualify_vip','cluster-qualify_vip.dpapi'))){
        $private=(Read-ProtectedBundle (Join-Path $root $item[1]))|ConvertFrom-Json
        if($private.operation_id -ne $operation.id){throw 'EVIDENCE_SCOPE'}
        $proofs[$item[0]]=Get-Content -LiteralPath (Join-Path $root ($item[0]+'-status.json')) -Raw|ConvertFrom-Json
    }
    $f=$proofs.foundation;$n=$proofs.network;$s=$proofs['service-permissions'];$p=$proofs['cluster-qualify_ports'];$v=$proofs['cluster-qualify_vip']
    if($f.code -ne 'FOUNDATION_INVENTORY_COLLECTED' -or $f.scoped_node_count -ne 3 -or
        -not $f.shared_datastore_accessible -or -not $f.storage_policy_query_succeeded -or $f.compatible_policy_count -lt 1){throw 'VMWARE_PREREQUISITES'}
    if($s.code -ne 'SCOPED_SERVICE_PRIVILEGES_VERIFIED' -or -not $s.required_privileges_present -or
        -not $s.vm_power_and_deletion_denied -or -not $s.outside_vm_disk_change_denied -or $s.permissions_propagate){throw 'SERVICE_PRIVILEGES'}
    if($n.code -ne 'BASIC_NETWORK_CHECKS_PASSED' -or -not $n.passed -or $n.controller_routes_overlap -or
        @($n.nodes|Where-Object {$_.endpoint_dns_matches -eq $true}).Count -ne 3){throw 'NETWORK_AND_DNS'}
    if($p.code -ne 'UNDERLAY_K3S_PORTS_VERIFIED' -or $p.passed_check_count -ne 54 -or -not $p.temporary_listeners_stopped){throw 'UNDERLAY_PORTS'}
    if($v.code -ne 'NODE_VIP_TRANSPORT_FAILOVER_VERIFIED' -or -not $v.single_owner_failover -or
        -not $v.vip_withdrawn_without_healthy_api -or -not $v.temporary_listeners_stopped){throw 'VIP_TRANSPORT'}
    foreach($gate in @('vmware_compatibility','api_failover','network_review','cpi_design')){
        $instance.config.gates.$gate='verified'
        $instance.qualification_evidence|Add-Member -Force -MemberType NoteProperty -Name $gate -Value @{
            status='verified';scope='preinstallation_synthetic_only';recorded_at=[DateTime]::UtcNow.ToString('o');
            evidence_ref='protected-foundation-network-service-ports-vip';production_qualified=$false
        }
    }
    $instance.config.network.existing_cidrs_reviewed=$true
    $instance|Add-Member -Force -MemberType NoteProperty -Name qualification_limits -Value @{
        vendor_vsphere_certification_verified=$false;csi_volume_operations_verified=$false;production_api_failover_verified=$false;
        future_client_networks_verified=$false;public_access_enabled=$false;synthetic_only=$true
    }
    $temporary=Join-Path $root ('qualification-'+[guid]::NewGuid().ToString('N')+'.dpapi')
    Save-ProtectedBundle $temporary ($instance|ConvertTo-Json -Depth 30 -Compress)
    [IO.File]::Replace($temporary,(Join-Path $root 'instance.dpapi'),[NullString]::Value)
    [IO.File]::WriteAllText((Join-Path $root 'preinstallation-status.json'),'{"status":"verified","code":"SYNTHETIC_BOOTSTRAP_PREREQUISITES_VERIFIED","production_qualified":false,"vendor_certification_verified":false,"csi_qualified":false}')
    Write-Host 'SYNTHETIC_BOOTSTRAP_PREREQUISITES_VERIFIED; PRODUCTION_NOT_QUALIFIED'
}catch{Write-Host 'PREINSTALLATION_QUALIFICATION_BLOCKED';exit 2}
finally{$private=$null;$instance=$null;if($mutex){$mutex.Dispose()}}
