# Resume only the explicitly owned foundation; never reset a partial cluster.
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'ProtectedState.ps1')
$root=Get-ArcIAStateRoot
try{
    & pwsh -NoProfile -File (Join-Path $PSScriptRoot 'Invoke-ClusterFoundation.ps1') -Action inspect_cluster
    if($LASTEXITCODE -ne 0){
        $operation=(Read-ProtectedBundle (Join-Path $root 'vmware-operation.dpapi'))|ConvertFrom-Json
        $instance=(Read-ProtectedBundle (Join-Path $root 'instance.dpapi'))|ConvertFrom-Json
        foreach($file in @('cluster-qualify_ports.dpapi','cluster-qualify_vip.dpapi')){
            $proof=(Read-ProtectedBundle (Join-Path $root $file))|ConvertFrom-Json
            if($proof.operation_id -ne $operation.id){throw 'FOUNDATION_RECOVERY_EVIDENCE_SCOPE'}
        }
        if($instance.operation_id -ne $operation.id -or @($instance.config.gates.PSObject.Properties|Where-Object {$_.Value -ne 'verified'}).Count){throw 'FOUNDATION_RECOVERY_PREREQUISITES_REQUIRED'}
        & pwsh -NoProfile -File (Join-Path $PSScriptRoot 'Invoke-ClusterFoundation.ps1') -Action install_k3s
        if($LASTEXITCODE -ne 0){throw 'OWNED_FOUNDATION_RECOVERY_FAILED'}
        & pwsh -NoProfile -File (Join-Path $PSScriptRoot 'Invoke-ClusterFoundation.ps1') -Action inspect_cluster
        if($LASTEXITCODE -ne 0){throw 'FOUNDATION_RECOVERY_NOT_READY'}
    }
    [IO.File]::WriteAllText((Join-Path $root 'bootstrap-k3s-status.json'),'{"status":"verified","code":"OWNED_K3S_FOUNDATION_READY"}')
}catch{Write-Output 'OWNED_FOUNDATION_RECOVERY_BLOCKED';exit 2}
finally{$operation=$null;$instance=$null;$proof=$null}
