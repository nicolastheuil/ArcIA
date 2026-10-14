[CmdletBinding()]
param([ValidateSet('inspect','qualify_ports','install_vip','qualify_vip','inspect_vip','install_k3s','inspect_k3s','pause_k3s','inspect_cluster','install_vmware','inspect_vmware','qualify_storage','install_postgres','install_hermes','install_hermes_base','inspect_apps','qualify_apps','qualify_live_vip','inspect_hermes_tools','install_hermes_tools','install_hermes_tools_base','verify_hermes_tools','cleanup_failed_hermes_tools','install_knowledge','verify_knowledge','inspect_knowledge','connect_knowledge','install_privacy','verify_privacy','inspect_privacy','install_multiuser','verify_multiuser','install_identity','verify_identity','inspect_identity','connect_identity','cleanup_identity_fixture','verify_identity_access','install_personal_portal','verify_personal_portal','inspect_personal_portal','plan_identity_microsoft_egress','apply_identity_microsoft_egress_repair','inspect_identity_microsoft_egress','plan_identity_access_repair','apply_identity_access_repair','inspect_identity_access_policy','install_identity_public_https_egress','plan_personal_cleanup','apply_personal_cleanup','install_omniroute','inspect_omniroute','verify_omniroute','read_omniroute_access')][string]$Action='inspect',
    [ValidatePattern('^[a-f0-9]{64}$')][string]$AuthorizedRepairPlanSha256,
    [string]$RecoveryUsername, [switch]$RepairUnqualifiedRouter, [switch]$AuthorizePrivateRouterController, [switch]$AuthorizeAllPrivateRouterSources)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'ProtectedState.ps1')
$root=Get-ArcIAStateRoot
$process=$null;$lockStream=$null
try{
    Initialize-PrivateDirectory $root
    if($Action -notin @('inspect_cluster','inspect_vmware','inspect_k3s','inspect_vip','inspect','inspect_omniroute','read_omniroute_access','inspect_apps','inspect_hermes_tools','cleanup_failed_hermes_tools','inspect_knowledge','inspect_privacy','plan_identity_microsoft_egress','inspect_identity_microsoft_egress','plan_identity_access_repair','inspect_identity_access_policy','plan_personal_cleanup')){
        $lockStream=[IO.File]::Open((Join-Path $root 'cluster-operation.lock'),[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::Write,[IO.FileShare]::None)
    }
    $payload=@{action=$Action;private_root=$root};if($AuthorizeAllPrivateRouterSources){if($Action -ne 'install_omniroute'){throw 'ROUTING_NETWORK_ENROLLMENT_ACTION_REQUIRED'};$payload.authorize_all_private_router_sources=$true};if($AuthorizePrivateRouterController){if($Action -ne 'install_omniroute'){throw 'ROUTING_NETWORK_ENROLLMENT_ACTION_REQUIRED'};$payload.authorize_private_router_controller=$true};if($RepairUnqualifiedRouter){if($Action -ne 'install_omniroute'){throw 'ROUTING_REPAIR_ACTION_REQUIRED'};$payload.repair_unqualified_runtime=$true}
    foreach($mapping in @(@('target','vmware-target.dpapi'),@('trust','ssh-trust.dpapi'),@('instance','instance.dpapi'))){
        $payload[$mapping[0]]=(Read-ProtectedBundle (Join-Path $root $mapping[1]))|ConvertFrom-Json
    }
    $operation=(Read-ProtectedBundle (Join-Path $root 'vmware-operation.dpapi'))|ConvertFrom-Json
    $payload.operation_id=$operation.id
    if($Action -in @('install_omniroute','verify_omniroute','read_omniroute_access','inspect_omniroute')){
        $routingCertificate=Join-Path $root 'routing-ip-tls.dpapi'
        if(Test-Path -LiteralPath $routingCertificate){
            $payload.routing_ip_tls=(Read-ProtectedBundle $routingCertificate)|ConvertFrom-Json
            if($payload.routing_ip_tls.operation_id -ne $operation.id){throw 'ROUTING_IP_TLS_SCOPE_CONFLICT'}
        }
    }
    if($Action -eq 'apply_personal_cleanup'){
        if(-not $AuthorizedRepairPlanSha256){throw 'PERSONAL_CLEANUP_EXPLICIT_NAMED_EXCEPTION_REQUIRED'}
        $payload.cleanup_plan=(Read-ProtectedBundle (Join-Path $root 'cluster-plan_personal_cleanup.dpapi'))|ConvertFrom-Json
        if($payload.cleanup_plan.operation_id -ne $operation.id -or $payload.cleanup_plan.plan.plan_sha256 -ne $AuthorizedRepairPlanSha256){throw 'PERSONAL_CLEANUP_PLAN_SCOPE'}
        $payload.authorized_plan_sha256=$AuthorizedRepairPlanSha256
    }
    if($Action -eq 'inspect_identity_access_policy'){
        $policyPath=Join-Path $root 'identity-access-policy.dpapi'
        if(Test-Path -LiteralPath $policyPath){$payload.access_policy=(Read-ProtectedBundle $policyPath)|ConvertFrom-Json}
    }
    if($Action -eq 'plan_identity_access_repair'){
        if(-not $RecoveryUsername){throw 'IDENTITY_ACCESS_USERNAME_REQUIRED'}
        $payload.recovery_username=$RecoveryUsername
    }
    if($Action -eq 'apply_identity_access_repair'){
        if(-not $AuthorizedRepairPlanSha256){throw 'IDENTITY_ACCESS_EXPLICIT_NAMED_EXCEPTION_REQUIRED'}
        $payload.access_repair=(Read-ProtectedBundle (Join-Path $root 'cluster-plan_identity_access_repair.dpapi'))|ConvertFrom-Json
        if($payload.access_repair.operation_id -ne $operation.id -or $payload.access_repair.plan.plan_sha256 -ne $AuthorizedRepairPlanSha256){throw 'IDENTITY_ACCESS_REPAIR_PLAN_SCOPE'}
        $payload.authorized_plan_sha256=$AuthorizedRepairPlanSha256
    }
    if($Action -eq 'apply_identity_microsoft_egress_repair'){
        if(-not $AuthorizedRepairPlanSha256){throw 'IDENTITY_EGRESS_EXPLICIT_EXCEPTION_REQUIRED'}
        $payload.repair=(Read-ProtectedBundle (Join-Path $root 'cluster-plan_identity_microsoft_egress.dpapi'))|ConvertFrom-Json
        if($payload.repair.operation_id -ne $operation.id -or $payload.repair.plan.plan_sha256 -ne $AuthorizedRepairPlanSha256){throw 'IDENTITY_EGRESS_REPAIR_SCOPE'}
        $payload.authorized_plan_sha256=$AuthorizedRepairPlanSha256
    }
    if($Action -eq 'verify_personal_portal'){
        $fixturePath=Join-Path $root 'portal-fixtures.dpapi'
        if(-not(Test-Path -LiteralPath $fixturePath)){
            $fixtures=@()
            foreach($suffix in @('a','b')){
                $bytes=[byte[]]::new(32);[Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
                $fixtures+=@{username=('arcia-portal-validation-'+$suffix);password=[Convert]::ToBase64String($bytes)}
                [Array]::Clear($bytes,0,$bytes.Length)
            }
            Save-ProtectedBundle $fixturePath (@{operation_id=$operation.id;fixtures=$fixtures}|ConvertTo-Json -Depth 6 -Compress)
            $fixtures=$null
        }
        $payload.portal_fixtures=(Read-ProtectedBundle $fixturePath)|ConvertFrom-Json
        if($payload.portal_fixtures.operation_id -ne $operation.id){throw 'PERSONAL_PORTAL_FIXTURE_SCOPE'}
    }
    if($Action -in @('install_identity','verify_identity','inspect_identity','connect_identity','cleanup_identity_fixture','verify_identity_access','install_personal_portal','verify_personal_portal','inspect_personal_portal','plan_identity_access_repair','apply_identity_access_repair','inspect_identity_access_policy','plan_personal_cleanup','apply_personal_cleanup')){
        $identityPath=Join-Path $root 'identity.dpapi'
        if(-not(Test-Path -LiteralPath $identityPath)){
            if($Action -ne 'install_identity'){throw 'IDENTITY_ENROLLMENT_REQUIRED'}
            function New-IdentityCredential {
                $bytes=[byte[]]::new(32);[Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
                return [Convert]::ToBase64String($bytes)
            }
            $identity=@{operation_id=$operation.id;bootstrap_username='arcia-bootstrap';
                bootstrap_password=(New-IdentityCredential);admin_username='arcia-admin-initial';
                admin_password=(New-IdentityCredential);db_password=(New-IdentityCredential);
                reconciler_secret=(New-IdentityCredential)}
            Save-ProtectedBundle $identityPath ($identity|ConvertTo-Json -Compress)
            $identity=$null
        }
        if($Action -in @('connect_identity','verify_identity_access')){$payload.second_pilot=(Read-ProtectedBundle (Join-Path $root 'multiuser-credentials.dpapi'))|ConvertFrom-Json;if($payload.second_pilot.operation_id -ne $operation.id){throw 'IDENTITY_SECOND_RUNTIME_SCOPE'}}
        $payload.identity=(Read-ProtectedBundle $identityPath)|ConvertFrom-Json
        if($payload.identity.operation_id -ne $operation.id){throw 'IDENTITY_ENROLLMENT_SCOPE_CONFLICT'}
        $payload.pilot=(Read-ProtectedBundle (Join-Path $root 'pilot-credentials.dpapi'))|ConvertFrom-Json
        if($payload.pilot.operation_id -ne $operation.id){throw 'IDENTITY_TLS_SCOPE_CONFLICT'}
    }
    if($Action -in @('install_multiuser','verify_multiuser')){
        $payload.pilot=(Read-ProtectedBundle (Join-Path $root 'pilot-credentials.dpapi'))|ConvertFrom-Json
        if($payload.pilot.operation_id -ne $operation.id){throw 'MULTIUSER_PILOT_SCOPE_CONFLICT'}
        $identityPath=Join-Path $root 'multiuser-credentials.dpapi'
        if(-not(Test-Path -LiteralPath $identityPath)){
            if($Action -ne 'install_multiuser'){throw 'MULTIUSER_CREDENTIALS_REQUIRED'}
            function New-IdentityRandom([int]$Length){$bytes=[byte[]]::new($Length);[Security.Cryptography.RandomNumberGenerator]::Fill($bytes);return [Convert]::ToBase64String($bytes)}
            $identity=@{operation_id=$operation.id;hostname=$payload.pilot.hostname;username='qualification-b';password=(New-IdentityRandom 24);password_salt=(New-IdentityRandom 16);session_secret=(New-IdentityRandom 32)}
            Save-ProtectedBundle $identityPath ($identity|ConvertTo-Json -Compress)
            $identity=$null
        }
        $payload.second_pilot=(Read-ProtectedBundle $identityPath)|ConvertFrom-Json
        if($payload.second_pilot.operation_id -ne $operation.id -or $payload.second_pilot.hostname -ne $payload.pilot.hostname){throw 'MULTIUSER_IDENTITY_SCOPE_CONFLICT'}
    }
    if($Action -in @('install_postgres','install_hermes','install_hermes_base')){
        $payload.storage_qualification=(Read-ProtectedBundle (Join-Path $root 'cluster-qualify_storage.dpapi'))|ConvertFrom-Json
    }
    if($Action -in @('install_hermes','install_hermes_base')){
        . (Join-Path $PSScriptRoot 'PilotCredentials.ps1')
        $decisions=(Read-ProtectedBundle (Join-Path $root 'installation-decisions.dpapi'))|ConvertFrom-Json
        if($decisions.operation_id -ne $operation.id -or $decisions.authentication_mode -ne 'local' -or $decisions.tls_mode -notin @('self_signed_pilot','public_acme') -or $decisions.public_access_enabled){throw 'LOCAL_PILOT_DECISIONS_REQUIRED'}
        $payload.pilot=Get-PilotCredentials $root $operation.id $payload.instance.config.network.public_hostname
    }
    if($Action -eq 'install_privacy'){
        $integrations=(Read-ProtectedBundle (Join-Path $root 'integrations.dpapi'))|ConvertFrom-Json
        if($integrations.operation_id -ne $operation.id -or -not $integrations.values.openrouter_api_key){throw 'PROTECTED_OPENROUTER_KEY_REQUIRED'}
        $payload.cloud_api_key=$integrations.values.openrouter_api_key
        $integrations=$null
    }
    if($Action -eq 'install_vmware'){
        foreach($mapping in @(@('connection','vmware.dpapi'),@('service','sso-service.dpapi'),@('foundation','foundation-inventory.dpapi'))){
            $payload[$mapping[0]]=(Read-ProtectedBundle (Join-Path $root $mapping[1]))|ConvertFrom-Json
        }
    }
    if($Action -eq 'qualify_live_vip'){
        $payload.pilot=(Read-ProtectedBundle (Join-Path $root 'pilot-credentials.dpapi'))|ConvertFrom-Json
        if($payload.pilot.operation_id -ne $operation.id){throw 'PILOT_SCOPE_CONFLICT'}
    }
    if($Action -in @('install_vip','qualify_vip','inspect_vip','qualify_live_vip')){
        $journal=Join-Path $root 'vip-journal.dpapi'
        if(-not(Test-Path -LiteralPath $journal)){
            if($Action -ne 'install_vip'){throw 'VIP_JOURNAL_REQUIRED'}
            $bytes=New-Object byte[] 16;$rng=[Security.Cryptography.RandomNumberGenerator]::Create()
            try{$rng.GetBytes($bytes)}finally{$rng.Dispose()}
            $password=([BitConverter]::ToString($bytes)).Replace('-','').Substring(0,8)
            $identity=@{operation_id=$operation.id;password=$password;vrid=(1+[int]$bytes[15]%255)}
            Save-ProtectedBundle $journal ($identity|ConvertTo-Json -Compress)
            $password=$null;$bytes=$null;$identity=$null
        }
        $payload.vip_journal=(Read-ProtectedBundle $journal)|ConvertFrom-Json
    }
    $start=New-Object Diagnostics.ProcessStartInfo
    $start.FileName=Join-Path $env:LOCALAPPDATA 'ArcIA-Validation\venv\Scripts\python.exe'
    $start.Arguments='"'+(Join-Path $PSScriptRoot 'cluster_foundation.py')+'"'
    $start.UseShellExecute=$false;$start.CreateNoWindow=$true
    $start.RedirectStandardInput=$true;$start.RedirectStandardOutput=$true;$start.RedirectStandardError=$true
    if($PSVersionTable.PSEdition -eq 'Core'){$start.StandardInputEncoding=New-Object Text.UTF8Encoding($false)}
    $start.StandardOutputEncoding=[Text.Encoding]::UTF8
    $process=New-Object Diagnostics.Process;$process.StartInfo=$start;$null=$process.Start()
    $process.StandardInput.Write(($payload|ConvertTo-Json -Depth 24 -Compress));$process.StandardInput.Close()
    $output=$process.StandardOutput.ReadToEndAsync();$errors=$process.StandardError.ReadToEndAsync()
    if(-not $process.WaitForExit(5400000)){$process.Kill();throw 'CLUSTER_ACTION_TIMEOUT'}
    $response=$output.GetAwaiter().GetResult()|ConvertFrom-Json;$null=$errors.GetAwaiter().GetResult()
    if($Action -eq 'verify_personal_portal' -and $response.private.fixtures){
        $fixtureUpdate=Join-Path $root ('portal-fixtures-'+[guid]::NewGuid().ToString('N')+'.dpapi')
        Save-ProtectedBundle $fixtureUpdate (@{operation_id=$operation.id;fixtures=$response.private.fixtures}|ConvertTo-Json -Depth 8 -Compress)
        [IO.File]::Replace($fixtureUpdate,(Join-Path $root 'portal-fixtures.dpapi'),[NullString]::Value)
    }
    if($Action -eq 'apply_identity_access_repair' -and $response.private.policy){
        $temporaryPolicy=Join-Path $root ('identity-access-policy-'+[guid]::NewGuid().ToString('N')+'.dpapi')
        Save-ProtectedBundle $temporaryPolicy ($response.private.policy|ConvertTo-Json -Depth 8 -Compress)
        $policyDestination=Join-Path $root 'identity-access-policy.dpapi'
        if(Test-Path -LiteralPath $policyDestination){[IO.File]::Replace($temporaryPolicy,$policyDestination,[NullString]::Value)}else{Move-Item -LiteralPath $temporaryPolicy -Destination $policyDestination}
    }
    if($response.private){
        $temporary=Join-Path $root ('cluster-'+[guid]::NewGuid().ToString('N')+'.dpapi')
        Save-ProtectedBundle $temporary ($response.private|ConvertTo-Json -Depth 24 -Compress)
        $destination=if($response.private.failure){Join-Path $root ('cluster-'+$Action+'-fault-'+[guid]::NewGuid().ToString('N')+'.dpapi')}else{Join-Path $root ('cluster-'+$Action+'.dpapi')}
        if(Test-Path -LiteralPath $destination){[IO.File]::Replace($temporary,$destination,[NullString]::Value)}else{Move-Item -LiteralPath $temporary -Destination $destination}
    }
    [IO.File]::WriteAllText((Join-Path $root ('cluster-'+$Action+'-status.json')),($response.safe|ConvertTo-Json -Depth 10),[Text.Encoding]::UTF8)
    if($process.ExitCode -ne 0){exit 2}
}catch{
    [IO.File]::WriteAllText((Join-Path $root ('cluster-'+$Action+'-status.json')),'{"status":"blocked","code":"LOCAL_CLUSTER_ACTION_FAILED"}')
    exit 2
}finally{$payload=$null;$response=$null;if($process){$process.Dispose()};if($lockStream){$lockStream.Dispose()}}
exit 0
