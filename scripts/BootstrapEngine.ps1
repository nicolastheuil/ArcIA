# Pure orchestration helpers, also exercised with synthetic executors in CI.
function Assert-BootstrapDefinition($Definition,[string]$Workspace){
    if($Definition.schema_version -ne 1){throw 'BOOTSTRAP_SCHEMA_INVALID'}
    $identity=$Definition.configuration_contracts.identity
    if($null -eq $identity -or $identity.default_provider -ne 'keycloak_local' -or
       $identity.local_accounts -ne 'permanent' -or
       -not(Test-Path -LiteralPath (Join-Path $Workspace 'bootstrap/identity.lock.json'))){throw 'BOOTSTRAP_IDENTITY_DEFAULT_REQUIRED'}
    if($identity.microsoft_egress.automatic_deployment_enabled -ne $false -or
       $identity.microsoft_egress.approval_required -ne 'server_verified_teams'){
        throw 'BOOTSTRAP_IDENTITY_EGRESS_APPROVAL_REQUIRED'
    }
    $m365=$Definition.configuration_contracts.microsoft365
    if($null -eq $m365 -or $m365.runtime_implemented -ne $false -or
       $m365.lock -ne 'bootstrap/microsoft365.lock.json' -or
       -not(Test-Path -LiteralPath (Join-Path $Workspace $m365.lock))){throw 'BOOTSTRAP_M365_CONTRACT_INVALID'}
    $seen=@{}
    foreach($step in $Definition.steps){
        if($step.id -notmatch '^[a-z][a-z0-9_]+$' -or $seen.ContainsKey($step.id)){throw 'BOOTSTRAP_STEP_INVALID'}
        foreach($dependency in $step.after){if(-not $seen.ContainsKey($dependency)){throw 'BOOTSTRAP_DEPENDENCY_INVALID'}}
        if($step.script -notmatch '^scripts/[A-Za-z0-9-]+\.ps1$' -or -not(Test-Path -LiteralPath (Join-Path $Workspace $step.script))){throw 'BOOTSTRAP_SCRIPT_INVALID'}
        if($step.engine -notin @('pwsh','powershell') -or $step.timeout_seconds -lt 10 -or $step.timeout_seconds -gt 7200){throw 'BOOTSTRAP_EXECUTION_INVALID'}
        if($step.status_file -and $step.status_file -notmatch '^[a-z0-9_-]+-status\.json$'){throw 'BOOTSTRAP_STATUS_PATH_INVALID'}
        $seen[$step.id]=$true
    }
}

function Invoke-BootstrapSequence($Steps,[scriptblock]$Execute,[scriptblock]$Record){
    # A journal is evidence, never permission to skip a stage on another target.
    foreach($step in $Steps){
        & $Record $step.id 'running'
        $passed=& $Execute $step
        if($passed -ne $true){& $Record $step.id 'blocked';throw 'BOOTSTRAP_STAGE_FAILED'}
        & $Record $step.id 'verified'
    }
}
