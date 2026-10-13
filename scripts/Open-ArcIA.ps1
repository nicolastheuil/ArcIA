# Open personal onboarding using protected instance settings; no credentials printed.
[CmdletBinding()]
param([switch]$UseExistingSession)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'ProtectedState.ps1')
$root=Get-ArcIAStateRoot -Identity -SelectLocally
$instance=(Read-ProtectedBundle (Join-Path $root 'instance.dpapi'))|ConvertFrom-Json
$hostValue=$instance.config.network.public_hostname
if($hostValue -notmatch '^[a-z0-9][a-z0-9.-]+[a-z0-9]$'){throw 'IDENTITY_HOST_INVALID'}
$address=[Net.IPAddress]::Parse($instance.endpoint_design.https_ip)
$browser=@((Join-Path ${env:ProgramFiles(x86)} 'Microsoft\Edge\Application\msedge.exe'),
    (Join-Path $env:ProgramFiles 'Microsoft\Edge\Application\msedge.exe'))|
    Where-Object {Test-Path -LiteralPath $_}|Select-Object -First 1
if(-not $browser){throw 'EXISTING_BROWSER_REQUIRED'}
$profile=Join-Path $root 'arcia-personal-browser';Initialize-PrivateDirectory $profile
$suffix=if($UseExistingSession){'/portal/'}else{'/portal/login?reauth=1'}
Start-Process -FilePath $browser -WindowStyle Normal -ArgumentList @(
    ('--user-data-dir="'+$profile+'"'),('--host-resolver-rules="MAP '+$hostValue+' '+$address.ToString()+'"'),
    '--no-proxy-server','--no-first-run','--no-default-browser-check','--new-window',('https://'+$hostValue+$suffix))|Out-Null
$instance=$null
