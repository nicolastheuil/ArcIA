$ErrorActionPreference='Stop'
. (Join-Path (Split-Path $PSScriptRoot -Parent) 'scripts/BootstrapEngine.ps1')
$root=Split-Path $PSScriptRoot -Parent
$definition=Get-Content (Join-Path $root 'bootstrap/qualification.json') -Raw|ConvertFrom-Json
Assert-BootstrapDefinition $definition $root
$steps=@([pscustomobject]@{id='first'},[pscustomobject]@{id='second'},[pscustomobject]@{id='third'})
$events=[Collections.Generic.List[string]]::new()
$blocked=$false
try{
    Invoke-BootstrapSequence $steps {param($step);return ($step.id -ne 'second')} {param($id,$state);$events.Add($id+':'+$state)}
}catch{$blocked=$true}
if(-not $blocked -or 'third:running' -in $events -or 'second:blocked' -notin $events){throw 'BOOTSTRAP_FAIL_CLOSED_FAILED'}
$events.Clear()
Invoke-BootstrapSequence $steps {param($step);return $true} {param($id,$state);$events.Add($id+':'+$state)}
if($events.Count -ne 6 -or $events[-1] -ne 'third:verified'){throw 'BOOTSTRAP_REPLAY_ORDER_FAILED'}
$bad=$definition|ConvertTo-Json -Depth 20|ConvertFrom-Json
$bad.steps[0].after=@('missing')
$blocked=$false
try{Assert-BootstrapDefinition $bad $root}catch{$blocked=$true}
if(-not $blocked){throw 'BOOTSTRAP_DEPENDENCY_GUARD_FAILED'}
$bad=$definition|ConvertTo-Json -Depth 20|ConvertFrom-Json
$bad.configuration_contracts.microsoft365.runtime_implemented=$true
$blocked=$false
try{Assert-BootstrapDefinition $bad $root}catch{$blocked=$true}
if(-not $blocked){throw 'BOOTSTRAP_M365_ACTIVATION_GUARD_FAILED'}
$bad=$definition|ConvertTo-Json -Depth 20|ConvertFrom-Json
$bad.configuration_contracts.identity.microsoft_egress.automatic_deployment_enabled=$true
$blocked=$false
try{Assert-BootstrapDefinition $bad $root}catch{$blocked=$true}
if(-not $blocked){throw 'BOOTSTRAP_IDENTITY_EGRESS_APPROVAL_GUARD_FAILED'}
Write-Output 'BOOTSTRAP_FAIL_CLOSED_REPLAY_AND_DEPENDENCY_GUARDS_VERIFIED'
$bad=$definition|ConvertTo-Json -Depth 20|ConvertFrom-Json
$bad.configuration_contracts|Add-Member -NotePropertyName portable_state -NotePropertyValue @{}
$blocked=$false
try{Assert-BootstrapDefinition $bad $root}catch{$blocked=$_.Exception.Message -eq 'BOOTSTRAP_PERSONAL_TRANSFER_OUT_OF_SCOPE'}
if(-not $blocked){throw 'BOOTSTRAP_PERSONAL_TRANSFER_SCOPE_GUARD_FAILED'}
Write-Output 'BOOTSTRAP_PERSONAL_TRANSFER_EXCLUDED'
