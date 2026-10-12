# Open the existing browser with a private hostname mapping; never emit credentials.
[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'ProtectedState.ps1')
$taskRoot=Get-ArcIAPrivateRoot
$taskPilot=(Read-ProtectedBundle (Join-Path $taskRoot 'pilot-credentials.dpapi'))|ConvertFrom-Json
$taskInstance=(Read-ProtectedBundle (Join-Path $taskRoot 'instance.dpapi'))|ConvertFrom-Json
if($taskPilot.operation_id -ne $taskInstance.operation_id){throw 'DASHBOARD_SCOPE_CONFLICT'}
if($taskPilot.hostname -ne 'arcia.arcitek.io'){throw 'EXPECTED_DASHBOARD_HOST_REQUIRED'}
$taskAddress=$null
if(-not [Net.IPAddress]::TryParse($taskInstance.endpoint_design.https_ip,[ref]$taskAddress) -or
    $taskAddress.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork){throw 'PRIVATE_IPV4_REQUIRED'}
$taskBrowser=@((Join-Path ${env:ProgramFiles(x86)} 'Microsoft\Edge\Application\msedge.exe'),
    (Join-Path $env:ProgramFiles 'Microsoft\Edge\Application\msedge.exe')) |
    Where-Object {Test-Path -LiteralPath $_} | Select-Object -First 1
if(-not $taskBrowser){throw 'EXISTING_EDGE_BROWSER_REQUIRED'}
$taskProfile=Join-Path $taskRoot 'dashboard-browser'
Initialize-PrivateDirectory $taskProfile
$taskArguments=@('--user-data-dir="'+$taskProfile+'"','--host-resolver-rules="MAP arcia.arcitek.io '+$taskAddress.IPAddressToString+'"',
    '--no-proxy-server','--no-first-run','--no-default-browser-check','--new-window','https://arcia.arcitek.io')
# Interactive browser requested by the user; TLS validation remains enabled.
Start-Process -FilePath $taskBrowser -ArgumentList $taskArguments -WindowStyle Normal | Out-Null
$taskPilot=$null;$taskInstance=$null;$taskArguments=$null
