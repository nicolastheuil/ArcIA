# Windows PowerShell 5.1 only: pinned VMware .NET Framework client, exact TLS pin.
[CmdletBinding()]
param([switch]$Create,[switch]$RepairPasswordPolicy)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'ProtectedState.ps1')
$privateRoot=Join-Path $env:LOCALAPPDATA 'ArcIA-Harness'
$statusPath=Join-Path $privateRoot 'sso-service-status.json'
$stage='INITIALIZE';$server=$null;$journal=$null;$lockStream=$null
function Save-SsoJournal($Value){
    $temporary=Join-Path $privateRoot ('sso-'+[guid]::NewGuid().ToString('N')+'.dpapi')
    Save-ProtectedBundle $temporary ($Value|ConvertTo-Json -Depth 10 -Compress)
    $destination=Join-Path $privateRoot 'sso-service.dpapi'
    if(Test-Path -LiteralPath $destination){[IO.File]::Replace($temporary,$destination,[NullString]::Value)}
    else{Move-Item -LiteralPath $temporary -Destination $destination}
}
. (Join-Path $PSScriptRoot 'SsoSecurity.ps1')
try {
    if($PSVersionTable.PSEdition -ne 'Desktop'){throw 'WINDOWS_POWERSHELL_REQUIRED'}
    Initialize-PrivateDirectory $privateRoot
    $lockStream=[IO.File]::Open((Join-Path $privateRoot 'sso-service.lock'),[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::Write,[IO.FileShare]::None)
    $connection=(Read-ProtectedBundle (Join-Path $privateRoot 'vmware.dpapi'))|ConvertFrom-Json
    $operation=(Read-ProtectedBundle (Join-Path $privateRoot 'vmware-operation.dpapi'))|ConvertFrom-Json
    if($connection.port -ne 443 -or $connection.certificate_sha256 -notmatch '^[a-f0-9]{64}$'){throw 'PINNED_DEFAULT_ENDPOINT_REQUIRED'}
    $stage='LOAD_PINNED_CLIENT'
    $lock=Get-Content -LiteralPath (Join-Path $PSScriptRoot '../versions.lock.yaml') -Raw|ConvertFrom-Json
    $client=Join-Path $privateRoot ('tools\sso-'+$lock.sso_admin_client.revision)
    foreach($file in $lock.sso_admin_client.files){
        $path=Join-Path $client $file.name
        if((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLower() -ne $file.sha256){throw 'CLIENT_INTEGRITY_FAILED'}
    }
    Initialize-SsoCertificateValidator
    $null=[Reflection.Assembly]::LoadFrom((Join-Path $client 'VMware.vSphere.LsClient.dll'))
    $null=[Reflection.Assembly]::LoadFrom((Join-Path $client 'VMware.vSphere.SsoAdminClient.dll'))
    $validator=New-Object ArcIAPinnedCertificateValidator($connection.certificate_sha256)
    $password=ConvertTo-SecureString -String $connection.password -AsPlainText -Force
    $stage='CONNECT_SSO_WITH_PIN'
    $server=New-Object VMware.vSphere.SsoAdminClient.DataTypes.SsoAdminServer -ArgumentList @($connection.server,$connection.username,$password,$validator)
    $stage='READ_LOCAL_IDENTITY_SOURCE'
    $domains=@($server.Client.GetDomains()|Where-Object {$_.GetType().Name -eq 'SystemIdentitySource'})
    if($domains.Count -ne 1){throw 'LOCAL_SSO_DOMAIN_AMBIGUOUS'}
    $domain=$domains[0].Name
    $username='arcia-cpi-csi'
    $existing=@($server.Client.GetLocalUsers($username,$domain)|Where-Object {$_.Name -eq $username})
    $policy=$server.Client.GetPasswordPolicy()
    if(-not $Create){
        $safe=@{status='inspected';code='SSO_LOCAL_IDENTITY_ACCESS_VERIFIED';existing_service_account_count=$existing.Count;password_min_length=$policy.MinLength;password_max_length=$policy.MaxLength;created=$false;permissions_applied=$false;k3s_installed=$false}
    }else{
        $stage='CHECK_OPERATION_OWNERSHIP'
        $journalPath=Join-Path $privateRoot 'sso-service.dpapi'
        if(Test-Path -LiteralPath $journalPath){
            $journal=(Read-ProtectedBundle $journalPath)|ConvertFrom-Json
            if($journal.operation_id -ne $operation.id -or $journal.username -ne ($username+'@'+$domain)){throw 'SSO_JOURNAL_SCOPE_MISMATCH'}
        }else{
            if($existing.Count){throw 'EXISTING_ACCOUNT_NOT_OWNED'}
            $newPassword=New-ServicePassword ([Math]::Min(32,$policy.MaxLength))
            $journal=@{operation_id=$operation.id;username=($username+'@'+$domain);password=$newPassword;status='prepared';description=('ArcIA CPI CSI operation '+$operation.id)}
            Save-SsoJournal $journal
        }
        if($existing.Count -gt 1){throw 'ACCOUNT_COLLISION'}
        if($RepairPasswordPolicy){
            # The original request could not satisfy the server's length policy.
            # Require proven absence and that exact incompatibility before changing the journal.
            if($existing.Count -ne 0 -or $journal.status -ne 'dispatch_started' -or
               $journal.password.Length -le $policy.MaxLength){throw 'PASSWORD_REPAIR_NOT_APPLICABLE'}
            $journal.password=New-ServicePassword ([Math]::Min(32,$policy.MaxLength))
            $journal.status='prepared';Save-SsoJournal $journal
        }
        if($existing.Count -eq 0){
            # Dispatch once. An uncertain previous creation is reconciled, never blindly replayed.
            if($journal.status -ne 'prepared'){throw 'SSO_CREATION_RECONCILIATION_REQUIRED'}
            $journal.status='dispatch_started';Save-SsoJournal $journal
            $stage='CREATE_OWNED_SERVICE_ACCOUNT'
            $null=$server.Client.CreateLocalUser($username,$journal.password,$journal.description,$null,'ArcIA','CPI CSI')
            $existing=@($server.Client.GetLocalUsers($username,$domain)|Where-Object {$_.Name -eq $username})
        }
        if($existing.Count -ne 1 -or $existing[0].Description -ne $journal.description -or $existing[0].Disabled){throw 'SSO_ACCOUNT_OWNERSHIP_NOT_VERIFIED'}
        $journal.status='created_verified';Save-SsoJournal $journal
        $safe=@{status='created';code='OWNED_SSO_SERVICE_ACCOUNT_CREATED';created=$true;permissions_applied=$false;k3s_installed=$false}
    }
    [IO.File]::WriteAllText($statusPath,($safe|ConvertTo-Json),[Text.Encoding]::UTF8)
}catch{
    # Raw SDK faults remain encrypted locally; they may contain principals or passwords.
    try{
        $faultPath=Join-Path $privateRoot ('sso-fault-'+[guid]::NewGuid().ToString('N')+'.dpapi')
        Save-ProtectedBundle $faultPath (@{stage=$stage;exception=$_.Exception.ToString()}|ConvertTo-Json -Depth 5 -Compress)
    }catch{}
    $category='SSO_CLIENT_OR_SERVER_FAILURE'
    $exception=$_.Exception
    for($i=0;$i -lt 8 -and $exception;$i++){
        $message=$exception.Message
        if($message -match 'TLS_FINGERPRINT_CHANGED'){$category='SSO_TLS_PIN_CHANGED';break}
        if($message -match 'could not load file or assembly|Could not load type|method not found'){$category='SSO_CLIENT_RUNTIME_MISSING';break}
        if($message -match 'certificate|trust relationship|SSL/TLS|secure channel'){$category='SSO_TLS_VALIDATION_FAILED';break}
        if($message -match 'InvalidCredentials|InvalidLogin|not authorized|permission|Unauthorized'){$category='SSO_AUTHENTICATION_OR_PERMISSION_FAILED';break}
        if($message -match 'No such host|remote name could not be resolved|NameResolution'){$category='SSO_ENDPOINT_DNS_FAILED';break}
        if($message -match 'timed out|timeout|actively refused'){$category='SSO_ENDPOINT_UNREACHABLE';break}
        $exception=$exception.InnerException
    }
    $safe=@{status='blocked';code=$category;stage=$stage;created=$false;creation_may_be_uncertain=($stage -eq 'CREATE_OWNED_SERVICE_ACCOUNT');permissions_applied=$false;k3s_installed=$false}
    [IO.File]::WriteAllText($statusPath,($safe|ConvertTo-Json),[Text.Encoding]::UTF8)
    exit 2
}finally{
    $connection=$null;$journal=$null;$newPassword=$null
    if($password){$password.Dispose()}
    if($random){[Array]::Clear($random,0,$random.Length)}
    if($lockStream){$lockStream.Dispose()}
    $server=$null
}
