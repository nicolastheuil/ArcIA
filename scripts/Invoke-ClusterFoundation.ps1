[CmdletBinding()]
param([ValidateSet('inspect','qualify_ports','install_vip','qualify_vip','inspect_vip','install_k3s','inspect_k3s','pause_k3s','inspect_cluster','install_vmware','inspect_vmware','qualify_storage','install_postgres','install_hermes','inspect_apps','qualify_apps','qualify_live_vip','inspect_hermes_tools','install_hermes_tools','verify_hermes_tools','cleanup_failed_hermes_tools','install_knowledge','verify_knowledge','inspect_knowledge','connect_knowledge')][string]$Action='inspect')
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'ProtectedState.ps1')
$root=Join-Path $env:LOCALAPPDATA 'ArcIA-Harness'
$process=$null;$lockStream=$null
try{
    Initialize-PrivateDirectory $root
    if($Action -notin @('inspect_cluster','inspect_vmware','inspect_k3s','inspect_vip','inspect','inspect_apps','inspect_hermes_tools','cleanup_failed_hermes_tools','inspect_knowledge')){
        $lockStream=[IO.File]::Open((Join-Path $root 'cluster-operation.lock'),[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::Write,[IO.FileShare]::None)
    }
    $payload=@{action=$Action;private_root=$root}
    foreach($mapping in @(@('target','vmware-target.dpapi'),@('trust','ssh-trust.dpapi'),@('instance','instance.dpapi'))){
        $payload[$mapping[0]]=(Read-ProtectedBundle (Join-Path $root $mapping[1]))|ConvertFrom-Json
    }
    $operation=(Read-ProtectedBundle (Join-Path $root 'vmware-operation.dpapi'))|ConvertFrom-Json
    $payload.operation_id=$operation.id
    if($Action -in @('install_postgres','install_hermes')){
        $payload.storage_qualification=(Read-ProtectedBundle (Join-Path $root 'cluster-qualify_storage.dpapi'))|ConvertFrom-Json
    }
    if($Action -eq 'install_hermes'){
        . (Join-Path $PSScriptRoot 'PilotCredentials.ps1')
        $decisions=(Read-ProtectedBundle (Join-Path $root 'installation-decisions.dpapi'))|ConvertFrom-Json
        if($decisions.operation_id -ne $operation.id -or $decisions.authentication_mode -ne 'local' -or $decisions.tls_mode -notin @('self_signed_pilot','public_acme') -or $decisions.public_access_enabled){throw 'LOCAL_PILOT_DECISIONS_REQUIRED'}
        $payload.pilot=Get-PilotCredentials $root $operation.id $payload.instance.config.network.public_hostname
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
