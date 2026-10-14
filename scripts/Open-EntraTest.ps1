# Open the explicitly requested human login test without exposing private settings.
[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'ProtectedState.ps1')
$entraStateRoot=Get-ArcIAStateRoot
$instance=(Read-ProtectedBundle (Join-Path $entraStateRoot 'instance.dpapi'))|ConvertFrom-Json
$status=Get-Content -LiteralPath (Join-Path $entraStateRoot 'cluster-verify_entra_test-status.json') -Raw|ConvertFrom-Json
if($status.code -ne 'ENTRA_TEST_VERIFIED'){throw 'ENTRA_TEST_DEPLOYMENT_VERIFICATION_REQUIRED'}
$hostValue=$instance.config.network.public_hostname
if($hostValue -notmatch '^[a-z0-9][a-z0-9.-]+[a-z0-9]$'){throw 'ENTRA_TEST_HOST_INVALID'}
$address=[Net.IPAddress]::Parse($instance.endpoint_design.https_ip)
$browser=@((Join-Path ${env:ProgramFiles(x86)} 'Microsoft\Edge\Application\msedge.exe'),
    (Join-Path $env:ProgramFiles 'Microsoft\Edge\Application\msedge.exe'))|
    Where-Object {Test-Path -LiteralPath $_}|Select-Object -First 1
if(-not $browser){throw 'EXISTING_BROWSER_REQUIRED'}
$profile=Join-Path $entraStateRoot 'entra-test-browser';Initialize-PrivateDirectory $profile
Start-Process -FilePath $browser -WindowStyle Normal -ArgumentList @(
    ('--user-data-dir="'+$profile+'"'),('--host-resolver-rules="MAP '+$hostValue+' '+$address.ToString()+'"'),
    '--no-proxy-server','--no-first-run','--no-default-browser-check','--new-window',
    ('https://'+$hostValue+'/entra-test/auth/login?provider=entra'))|Out-Null
$instance=$null
