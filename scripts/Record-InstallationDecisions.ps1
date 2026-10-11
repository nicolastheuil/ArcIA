# Records the user's explicit pilot decisions; never changes integration credentials.
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'ProtectedState.ps1')
$root=Join-Path $env:LOCALAPPDATA 'ArcIA-Harness'
try{
    Initialize-PrivateDirectory $root
    $operation=(Read-ProtectedBundle (Join-Path $root 'vmware-operation.dpapi'))|ConvertFrom-Json
    $decisions=@{operation_id=$operation.id;authentication_mode='local';entra_integration='deferred_keep_adapter';
        tls_mode='self_signed_pilot';recovery_mode='prepare_second_engineer_pending';public_access_enabled=$false;
        recorded_at=[DateTime]::UtcNow.ToString('o')}
    $destination=Join-Path $root 'installation-decisions.dpapi'
    $temporary=Join-Path $root ('decisions-'+[guid]::NewGuid().ToString('N')+'.dpapi')
    Save-ProtectedBundle $temporary ($decisions|ConvertTo-Json -Compress)
    if(Test-Path -LiteralPath $destination){[IO.File]::Replace($temporary,$destination,[NullString]::Value)}else{Move-Item -LiteralPath $temporary -Destination $destination}
    Write-Output 'LOCAL_AUTH_DEFERRED_ENTRA_SELF_SIGNED_TLS_DECISIONS_SAVED'
}catch{Write-Output 'INSTALLATION_DECISIONS_SAVE_FAILED';exit 2}
finally{$operation=$null;$decisions=$null}
