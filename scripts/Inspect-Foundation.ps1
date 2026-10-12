[CmdletBinding()]
param([switch]$Network,[switch]$ServicePermissions,[switch]$ReadOnly,[switch]$VerifyOnly,[switch]$FlushDnsCache)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'ProtectedState.ps1')
$privateRoot=Get-ArcIAStateRoot
$process=$null;$lockStream=$null
try {
    Initialize-PrivateDirectory -Path $privateRoot
    if($FlushDnsCache -and -not $Network){throw 'DNS_CACHE_ACTION_REQUIRES_NETWORK_MODE'}
    if($ServicePermissions){$lockStream=[IO.File]::Open((Join-Path $privateRoot 'service-permissions.lock'),[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::Write,[IO.FileShare]::None)}
    $connection=(Read-ProtectedBundle (Join-Path $privateRoot 'vmware.dpapi'))|ConvertFrom-Json
    $target=(Read-ProtectedBundle (Join-Path $privateRoot 'vmware-target.dpapi'))|ConvertFrom-Json
    $operation=(Read-ProtectedBundle (Join-Path $privateRoot 'vmware-operation.dpapi'))|ConvertFrom-Json
    $payload=@{connection=$connection;target=$target;operation_id=$operation.id}
    $prefix='foundation'
    $worker='vmware_foundation.py'
    if($Network){
        $prefix='network';$worker='network_preflight.py'
        $payload.trust=(Read-ProtectedBundle (Join-Path $privateRoot 'ssh-trust.dpapi'))|ConvertFrom-Json
        $payload.private_root=$privateRoot
        $payload.flush_dns_cache=[bool]$FlushDnsCache
        $payload.controller_routes=@(Get-NetRoute -AddressFamily IPv4 -ErrorAction Stop|ForEach-Object {$_.DestinationPrefix}|Sort-Object -Unique)
        $instancePath=Join-Path $privateRoot 'instance.dpapi'
        if(Test-Path -LiteralPath $instancePath){$payload.instance=(Read-ProtectedBundle $instancePath)|ConvertFrom-Json}
        $dnsAccessPath=Join-Path $privateRoot 'dns-access.dpapi'
        if(Test-Path -LiteralPath $dnsAccessPath){
            $dnsAccess=(Read-ProtectedBundle $dnsAccessPath)|ConvertFrom-Json
            $payload.authoritative_dns=@([Net.Dns]::GetHostAddresses($dnsAccess.server)|Where-Object {$_.AddressFamily -eq [Net.Sockets.AddressFamily]::InterNetwork}|ForEach-Object {$_.IPAddressToString})
            $dnsAccess=$null
        }
    }
    if($ServicePermissions){
        if($Network){throw 'ONE_WORKER_MODE_REQUIRED'}
        $prefix='service-permissions';$worker='vmware_service_permissions.py'
        $payload.service=(Read-ProtectedBundle (Join-Path $privateRoot 'sso-service.dpapi'))|ConvertFrom-Json
        if($payload.service.status -ne 'created_verified' -or $payload.service.operation_id -ne $operation.id){throw 'OWNED_SERVICE_ACCOUNT_REQUIRED'}
        $intentPath=Join-Path $privateRoot 'service-permissions-intent.dpapi'
        if(-not (Test-Path -LiteralPath $intentPath)){
            Save-ProtectedBundle $intentPath (@{operation_id=$operation.id;target=$target;principal=$payload.service.username}|ConvertTo-Json -Depth 12 -Compress)
        }
        $payload.intent=(Read-ProtectedBundle $intentPath)|ConvertFrom-Json
        $payload.read_only=[bool]$ReadOnly
        $payload.verify_only=[bool]$VerifyOnly
    }
    $start=New-Object Diagnostics.ProcessStartInfo
    $start.FileName=Join-Path $env:LOCALAPPDATA 'ArcIA-Validation\venv\Scripts\python.exe'
    $start.Arguments='"'+(Join-Path $PSScriptRoot $worker)+'"'
    $start.UseShellExecute=$false;$start.CreateNoWindow=$true
    $start.RedirectStandardInput=$true;$start.RedirectStandardOutput=$true;$start.RedirectStandardError=$true
    if($PSVersionTable.PSEdition -eq 'Core'){$start.StandardInputEncoding=New-Object Text.UTF8Encoding($false)}
    $start.StandardOutputEncoding=[Text.Encoding]::UTF8
    $process=New-Object Diagnostics.Process;$process.StartInfo=$start
    $null=$process.Start()
    $process.StandardInput.Write(($payload|ConvertTo-Json -Depth 20 -Compress))
    $process.StandardInput.Close()
    $output=$process.StandardOutput.ReadToEndAsync();$errors=$process.StandardError.ReadToEndAsync()
    if(-not $process.WaitForExit(300000)){$process.Kill();throw 'WORKER_TIMEOUT'}
    $response=$output.GetAwaiter().GetResult()|ConvertFrom-Json
    $null=$errors.GetAwaiter().GetResult()
    if($response.private){
        $temporary=Join-Path $privateRoot ('foundation-'+[guid]::NewGuid().ToString('N')+'.dpapi')
        Save-ProtectedBundle $temporary ($response.private|ConvertTo-Json -Depth 16 -Compress)
        $destination=if($response.private.failure){Join-Path $privateRoot ($prefix+'-fault-'+[guid]::NewGuid().ToString('N')+'.dpapi')}else{Join-Path $privateRoot ($prefix+'-inventory.dpapi')}
        if(Test-Path -LiteralPath $destination){[IO.File]::Replace($temporary,$destination,[NullString]::Value)}
        else{Move-Item -LiteralPath $temporary -Destination $destination}
    }
    [IO.File]::WriteAllText((Join-Path $privateRoot ($prefix+'-status.json')),($response.safe|ConvertTo-Json -Depth 8),[Text.Encoding]::UTF8)
    if($Network -and @($response.safe.nodes).Count -eq 3){
        $matches=@($response.safe.nodes|Where-Object {$_.endpoint_dns_matches -eq $true}).Count
        $dnsSummary=@{status=if($matches -eq 3){'verified'}else{'pending'};code=if($matches -eq 3){'DNS_RECORDS_RESOLVE_ON_THREE_NODES'}else{'DNS_RESOLUTION_NOT_YET_VERIFIED'};verified_node_count=$matches;k3s_installed=$false}
        [IO.File]::WriteAllText((Join-Path $privateRoot 'dns-resolution-status.json'),($dnsSummary|ConvertTo-Json),[Text.Encoding]::UTF8)
    }
    if($process.ExitCode -ne 0){exit 2}
} catch {
    if(-not $prefix){$prefix='foundation'}
    [IO.File]::WriteAllText((Join-Path $privateRoot ($prefix+'-status.json')),'{"status":"blocked","code":"LOCAL_FOUNDATION_INVENTORY_FAILED","k3s_installed":false}')
    exit 2
} finally{$connection=$null;$target=$null;$response=$null;$payload=$null;if($process){$process.Dispose()};if($lockStream){$lockStream.Dispose()}}
