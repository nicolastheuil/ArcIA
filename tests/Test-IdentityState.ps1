$ErrorActionPreference='Stop'
. (Join-Path (Split-Path $PSScriptRoot -Parent) 'scripts/ProtectedState.ps1')
$testRoot=Join-Path $env:LOCALAPPDATA ('ArcIA-Validation\identity-state-'+[guid]::NewGuid().ToString('N'))
$previousOverride=$env:ARCIA_STATE_ROOT
$env:ARCIA_STATE_ROOT=$null
$testFiles=@();$testDirectories=@()
function Assert-StateError {
    param([scriptblock]$Action,[string]$Code)
    $caught=$null
    try{& $Action|Out-Null}catch{$caught=$_.Exception.Message}
    if($caught -ne $Code){throw 'IDENTITY_STATE_ERROR_CONTRACT_FAILED'}
}
try{
    Initialize-PrivateDirectory $testRoot
    $legacy=Join-Path $testRoot 'legacy';$first=Join-Path $testRoot 'first'
    $second=Join-Path $testRoot 'second';$mismatch=Join-Path $testRoot 'mismatch'
    foreach($directory in @($legacy,$first,$second,$mismatch)){
        Initialize-PrivateDirectory $directory;$testDirectories+=,$directory
        $operationId=if($directory -eq $second){'synthetic-b'}else{'synthetic-a'}
        $operationPath=Join-Path $directory 'vmware-operation.dpapi'
        Save-ProtectedBundle $operationPath (@{id=$operationId}|ConvertTo-Json)
        $testFiles+=,$operationPath
        if($directory -eq $legacy){continue}
        $instancePath=Join-Path $directory 'instance.dpapi'
        Save-ProtectedBundle $instancePath (@{operation_id=$operationId;
            config=@{network=@{public_hostname='synthetic.example.invalid'}};
            endpoint_design=@{https_ip='192.0.2.1'}}|ConvertTo-Json -Depth 5)
        $testFiles+=,$instancePath
        $identityId=if($directory -eq $mismatch){'synthetic-foreign'}else{$operationId}
        $identityPath=Join-Path $directory 'identity.dpapi'
        Save-ProtectedBundle $identityPath (@{operation_id=$identityId;
            admin_username='synthetic-admin';admin_password='synthetic-fixture'}|ConvertTo-Json)
        $testFiles+=,$identityPath
    }
    # Substitute discovery only; DPAPI and canonical path resolution stay real.
    function Get-ArcIAStateCandidates {return $script:candidates}
    $script:candidates=@($legacy,$mismatch)
    Assert-StateError {Get-ArcIAStateRoot -Identity} 'PROTECTED_ARCIA_IDENTITY_STATE_NOT_FOUND'
    $script:candidates=@($legacy,$mismatch,$first)
    $expected=Get-PhysicalArcIARoot $first
    if((Get-ArcIAStateRoot -Identity) -ne $expected){throw 'LEGACY_STATE_NOT_FILTERED'}
    $script:candidates=@($first,$first.ToUpperInvariant())
    if((Get-ArcIAStateRoot -Identity) -ne $expected){throw 'STATE_ALIAS_NOT_DEDUPLICATED'}
    $script:candidates=@($first,$second)
    Assert-StateError {Get-ArcIAStateRoot -Identity} 'MULTIPLE_PROTECTED_ARCIA_STATES_REFUSED'
    Assert-StateError {Get-ArcIAStateRoot -SelectLocally} 'MULTIPLE_PROTECTED_ARCIA_STATES_REFUSED'
    $script:selectionCalls=0
    function Select-ArcIAStateRootLocally {
        param([string[]]$Candidates)
        $script:selectionCalls++
        return $Candidates[1]
    }
    if((Get-ArcIAStateRoot -Identity -SelectLocally) -ne (Get-PhysicalArcIARoot $second) -or
        $script:selectionCalls -ne 1){throw 'EXPLICIT_LOCAL_SELECTION_NOT_USED'}
    $env:ARCIA_STATE_ROOT=$legacy
    Assert-StateError {Get-ArcIAStateRoot -Identity} 'PROTECTED_ARCIA_IDENTITY_STATE_NOT_FOUND'
    $env:ARCIA_STATE_ROOT=$mismatch
    Assert-StateError {Get-ArcIAStateRoot -Identity} 'PROTECTED_ARCIA_IDENTITY_STATE_NOT_FOUND'
    $env:ARCIA_STATE_ROOT=$first
    if((Get-ArcIAStateRoot -Identity) -ne $first){throw 'EXPLICIT_STATE_NOT_RESPECTED'}
    Write-Host 'IDENTITY_STATE_SELECTION_VERIFIED; LEGACY_FILTERED; SCOPE_CHECKED; ALIASES_DEDUPLICATED; AMBIGUITY_REFUSED; LOCAL_CHOICE_EXPLICIT'
}finally{
    $env:ARCIA_STATE_ROOT=$previousOverride
    # Exact synthetic paths only; no recursive deletion or real state mutation.
    foreach($path in $testFiles){if(Test-Path -LiteralPath $path){Remove-Item -LiteralPath $path}}
    foreach($directory in $testDirectories){if(Test-Path -LiteralPath $directory){Remove-Item -LiteralPath $directory}}
    if(Test-Path -LiteralPath $testRoot){Remove-Item -LiteralPath $testRoot}
}
