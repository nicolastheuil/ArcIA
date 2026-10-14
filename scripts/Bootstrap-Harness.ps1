[CmdletBinding()]
param([ValidateSet('Plan','Apply','Verify','Audit')][string]$Mode='Plan',
    [ValidateSet('Fresh','Reconcile')][string]$Profile='Reconcile',[switch]$ProvisionVMs,
    [switch]$PlanMicrosoftEgress,[switch]$PlanPersonalCleanup)
$ErrorActionPreference='Stop'
if($PSVersionTable.PSVersion -lt [version]'7.4'){throw 'POWERSHELL_7_4_REQUIRED'}
. (Join-Path $PSScriptRoot 'ProtectedState.ps1')
. (Join-Path $PSScriptRoot 'BootstrapEngine.ps1')
$workspace=Split-Path $PSScriptRoot -Parent
$definition=Get-Content -LiteralPath (Join-Path $workspace 'bootstrap/qualification.json') -Raw|ConvertFrom-Json
Assert-BootstrapDefinition $definition $workspace
if($ProvisionVMs -and ($Profile -ne 'Fresh' -or $Mode -notin @('Apply','Plan'))){throw 'PROVISION_REQUIRES_FRESH_APPLY'}
$selection=if($Mode -eq 'Apply' -or $Mode -eq 'Plan'){$Profile.ToLowerInvariant()}else{$Mode.ToLowerInvariant()}
if($PlanMicrosoftEgress -and $Mode -ne 'Audit'){throw 'MICROSOFT_EGRESS_PLAN_REQUIRES_AUDIT'}
if($PlanPersonalCleanup -and $Mode -ne 'Audit'){throw 'PERSONAL_CLEANUP_PLAN_REQUIRES_AUDIT'}
$steps=@($definition.steps|Where-Object {$selection -in $_.profiles -and (-not $_.provision_only -or $ProvisionVMs) -and
    ($_.id -ne 'plan_identity_microsoft_egress' -or $PlanMicrosoftEgress) -and
    ($_.id -ne 'plan_personal_cleanup' -or $PlanPersonalCleanup)})
if($Mode -eq 'Plan'){
    @{status='planned';profile=$Profile;target='qualification';steps=@($steps|ForEach-Object {$_.id});
      private_inputs=$definition.private_inputs;configuration_contracts=$definition.configuration_contracts;
      tenant_admission=$definition.configuration_contracts.identity.tenant_admission;
      identity_public_https=$definition.configuration_contracts.identity.public_https;
      personal_key_configuration=$definition.configuration_contracts.routing.personal_key_configuration;
      business_services_enabled=$false;fresh_cluster_tested=$false}|ConvertTo-Json -Depth 8
    exit 0
}
$root=Get-ArcIAStateRoot
Initialize-PrivateDirectory $root
$previousRoot=$env:ARCIA_STATE_ROOT;$env:ARCIA_STATE_ROOT=$root
$mutex=$null;$process=$null;$current='preflight';$journal=$null
function Save-BootstrapJournal([string]$Step,[string]$State){
    $script:current=$Step
    $script:journal.steps[$Step]=@{state=$State;at=[DateTime]::UtcNow.ToString('o')}
    $temporary=Join-Path $root ('bootstrap-'+[guid]::NewGuid().ToString('N')+'.dpapi')
    Save-ProtectedBundle $temporary ($script:journal|ConvertTo-Json -Depth 16 -Compress)
    $destination=Join-Path $root 'bootstrap-journal.dpapi'
    if(Test-Path -LiteralPath $destination){[IO.File]::Replace($temporary,$destination,[NullString]::Value)}else{Move-Item -LiteralPath $temporary -Destination $destination}
    [IO.File]::WriteAllText((Join-Path $root 'bootstrap-status.json'),(@{status=$State;code='BOOTSTRAP_STAGE_'+$State.ToUpperInvariant();stage=$Step;profile=$Profile}|ConvertTo-Json),[Text.UTF8Encoding]::new($false))
    Write-Output ('BOOTSTRAP '+$Step+' '+$State)
}
try{
    $mutex=[IO.File]::Open((Join-Path $root 'bootstrap-operation.lock'),[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::Write,[IO.FileShare]::None)
    foreach($inputName in @('vmware.dpapi','vmware-target.dpapi')){
        if(-not(Test-Path -LiteralPath (Join-Path $root $inputName))){throw 'PROTECTED_VMWARE_ENROLLMENT_REQUIRED'}
        $null=(Read-ProtectedBundle (Join-Path $root $inputName))|ConvertFrom-Json
    }
    if($Profile -eq 'Reconcile' -or $Mode -in @('Verify','Audit')){
        $operation=(Read-ProtectedBundle (Join-Path $root 'vmware-operation.dpapi'))|ConvertFrom-Json
        $instance=(Read-ProtectedBundle (Join-Path $root 'instance.dpapi'))|ConvertFrom-Json
        if($instance.operation_id -ne $operation.id){throw 'BOOTSTRAP_OPERATION_SCOPE'}
    }
    $sha=(& git -C $workspace rev-parse HEAD 2>$null)
    if($LASTEXITCODE -ne 0 -or $sha -notmatch '^[a-f0-9]{40}$'){throw 'BOOTSTRAP_GIT_COMMIT_REQUIRED'}
    $journal=@{schema_version=1;commit=$sha;manifest_sha256=(Get-FileHash (Join-Path $workspace 'bootstrap/qualification.json') -Algorithm SHA256).Hash.ToLower();
        profile=$Profile;mode=$Mode;started_at=[DateTime]::UtcNow.ToString('o');steps=@{}}
    Invoke-BootstrapSequence $steps {
        param($step)
        # Reject stale status success: every successful step needs a fresh write.
        $status=if($step.status_file){Join-Path $root $step.status_file}else{$null}
        $started=[DateTime]::UtcNow
        $start=[Diagnostics.ProcessStartInfo]::new()
        $start.FileName=$step.engine;$start.UseShellExecute=$false;$start.CreateNoWindow=$true
        $start.WorkingDirectory=$workspace;$start.RedirectStandardOutput=$true;$start.RedirectStandardError=$true
        foreach($arg in @('-NoProfile','-File',(Join-Path $workspace $step.script))+@($step.arguments)){$start.ArgumentList.Add([string]$arg)}
        $process=[Diagnostics.Process]::new();$process.StartInfo=$start
        try{
            $null=$process.Start();$stdout=$process.StandardOutput.ReadToEndAsync();$stderr=$process.StandardError.ReadToEndAsync()
            if(-not $process.WaitForExit([int]$step.timeout_seconds*1000)){$process.Kill($true);return $false}
            $output=$stdout.GetAwaiter().GetResult();$errorOutput=$stderr.GetAwaiter().GetResult()
            # Raw worker diagnostics are encrypted, never forwarded to the model.
            Save-ProtectedBundle (Join-Path $root ('bootstrap-log-'+[guid]::NewGuid().ToString('N')+'.dpapi')) (@{stage=$step.id;stdout=$output;stderr=$errorOutput}|ConvertTo-Json -Depth 8 -Compress)
            if($process.ExitCode -ne 0){return $false}
            if($status){
                if(-not(Test-Path -LiteralPath $status) -or (Get-Item -LiteralPath $status).LastWriteTimeUtc -lt $started.AddSeconds(-1)){return $false}
                $result=Get-Content -LiteralPath $status -Raw|ConvertFrom-Json
                if($result.code -notin $step.success_codes){return $false}
            }
            return $true
        }finally{$process.Dispose();$output=$null;$errorOutput=$null}
    } ${function:Save-BootstrapJournal}
    Save-BootstrapJournal 'complete' 'verified'
    @{status='verified';code='BOOTSTRAP_SELECTED_PROFILE_VERIFIED';profile=$Profile;mode=$Mode;commit=$sha;
      stages_verified=$steps.Count;fresh_cluster_tested=$false;data_restore_implemented=$false;business_services_enabled=$false}|ConvertTo-Json
}catch{
    if($journal){Save-BootstrapJournal $current 'blocked'}
    @{status='blocked';code='BOOTSTRAP_STOPPED';stage=$current;details='Voir le journal local protege et le runbook bootstrap.'}|ConvertTo-Json
    exit 2
}finally{$env:ARCIA_STATE_ROOT=$previousRoot;if($mutex){$mutex.Dispose()};$instance=$null;$operation=$null;$journal=$null}
