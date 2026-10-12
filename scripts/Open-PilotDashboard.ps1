# Open the existing browser with a private hostname mapping; never emit credentials.
[CmdletBinding()]
param([ValidateSet('A','B')][string]$User='A')
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'ProtectedState.ps1')
$taskRoot=Get-ArcIAPrivateRoot
$taskPilot=(Read-ProtectedBundle (Join-Path $taskRoot 'pilot-credentials.dpapi'))|ConvertFrom-Json
$taskInstance=(Read-ProtectedBundle (Join-Path $taskRoot 'instance.dpapi'))|ConvertFrom-Json
if($taskPilot.operation_id -ne $taskInstance.operation_id){throw 'DASHBOARD_SCOPE_CONFLICT'}
if($taskPilot.hostname -notmatch '^(?=.{1,253}$)[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])$'){throw 'VALID_DASHBOARD_HOST_REQUIRED'}
$taskAddress=$null
if(-not [Net.IPAddress]::TryParse($taskInstance.endpoint_design.https_ip,[ref]$taskAddress) -or
    $taskAddress.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork){throw 'PRIVATE_IPV4_REQUIRED'}
$taskBrowser=@((Join-Path ${env:ProgramFiles(x86)} 'Microsoft\Edge\Application\msedge.exe'),
    (Join-Path $env:ProgramFiles 'Microsoft\Edge\Application\msedge.exe')) |
    Where-Object {Test-Path -LiteralPath $_} | Select-Object -First 1
if(-not $taskBrowser){throw 'EXISTING_EDGE_BROWSER_REQUIRED'}
$taskProfile=Join-Path $taskRoot ('dashboard-browser-'+$User)
Initialize-PrivateDirectory $taskProfile
$taskSuffix=if($User -eq 'B'){'/qualification-b/'}else{'/'}
$taskArguments=@('--user-data-dir="'+$taskProfile+'"','--host-resolver-rules="MAP '+$taskPilot.hostname+' '+$taskAddress.IPAddressToString+'"',
    '--no-proxy-server','--no-first-run','--no-default-browser-check','--new-window',('https://'+$taskPilot.hostname+$taskSuffix))
# Interactive browser requested by the user; TLS validation remains enabled.
Start-Process -FilePath $taskBrowser -ArgumentList $taskArguments -WindowStyle Normal | Out-Null
$taskPilot=$null;$taskInstance=$null;$taskArguments=$null
