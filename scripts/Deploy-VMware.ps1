[CmdletBinding()]
param([switch]$ValidateOnly, [string]$ImageRoot=(Join-Path $env:LOCALAPPDATA 'ArcIA-Harness\images'))
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'ProtectedState.ps1')
$privateRoot=Join-Path $env:LOCALAPPDATA 'ArcIA-Harness'
$statusPath=Join-Path $privateRoot 'vmware-deploy-status.json'
$python=Join-Path $env:LOCALAPPDATA 'ArcIA-Validation\venv\Scripts\python.exe'
$process=$null
$workerStarted=$false
$lockStream=$null
try {
    Initialize-PrivateDirectory -Path $privateRoot
    $lockStream=[IO.File]::Open((Join-Path $privateRoot 'vmware-deploy.lock'),[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::Write,[IO.FileShare]::None)
    $connection=(Read-ProtectedBundle -Path (Join-Path $privateRoot 'vmware.dpapi'))|ConvertFrom-Json
    $target=(Read-ProtectedBundle -Path (Join-Path $privateRoot 'vmware-target.dpapi'))|ConvertFrom-Json
    $operationPath=Join-Path $privateRoot 'vmware-operation.dpapi'
    if (Test-Path -LiteralPath $operationPath) { $operation=(Read-ProtectedBundle -Path $operationPath)|ConvertFrom-Json }
    else {
        $operation=@{id=[guid]::NewGuid().ToString()}
        Save-ProtectedBundle -Path $operationPath -Bundle ($operation|ConvertTo-Json)
    }
    $payload=@{connection=$connection;target=$target;operation_id=$operation.id;
        disk_path=(Join-Path $ImageRoot 'arcia-debian-13-base.vmdk');receipt_path=(Join-Path $ImageRoot 'image-receipt.json')}
    $start=New-Object Diagnostics.ProcessStartInfo
    $start.FileName=$python
    $start.Arguments='"'+(Join-Path $PSScriptRoot 'vmware_deploy.py')+'"'
    if ($ValidateOnly) {$start.Arguments+=' --validate-only'}
    $start.UseShellExecute=$false; $start.CreateNoWindow=$true
    $start.RedirectStandardInput=$true; $start.RedirectStandardOutput=$true; $start.RedirectStandardError=$true
    $start.StandardInputEncoding=New-Object Text.UTF8Encoding($false)
    $start.StandardOutputEncoding=[Text.Encoding]::UTF8
    $process=New-Object Diagnostics.Process; $process.StartInfo=$start
    $null=$process.Start()
    $workerStarted=$true
    $process.StandardInput.Write(($payload|ConvertTo-Json -Depth 12)); $process.StandardInput.Close()
    $outputTask=$process.StandardOutput.ReadToEndAsync(); $errorTask=$process.StandardError.ReadToEndAsync()
    # Wait in the background helper; the calling agent reads safe status only.
    $pending=@{status='running';code='VM_PREFLIGHT_RUNNING';deployed=$false;created_count=0}
    if (-not $ValidateOnly) {$pending.code='VM_CREATION_RUNNING'}
    [IO.File]::WriteAllText($statusPath,($pending|ConvertTo-Json),[Text.Encoding]::UTF8)
    $process.WaitForExit()
    $privateResult=$outputTask.GetAwaiter().GetResult(); $null=$errorTask.GetAwaiter().GetResult()
    $result=$privateResult|ConvertFrom-Json
    $temporary=Join-Path $privateRoot ('deployment-'+[guid]::NewGuid().ToString('N')+'.dpapi')
    Save-ProtectedBundle -Path $temporary -Bundle $privateResult
    $resultPath=Join-Path $privateRoot 'vmware-deployment.dpapi'
    if (Test-Path -LiteralPath $resultPath) {[IO.File]::Replace($temporary,$resultPath,[NullString]::Value)}
    else {Move-Item -LiteralPath $temporary -Destination $resultPath}
    # Worker codes are constants from source, never raw exceptions/values.
    if ($result.code -notmatch '^[A-Z][A-Z0-9_]{1,80}$') {throw 'INVALID_WORKER_RESULT'}
    $safe=@{status=$result.status;code=$result.code;deployed=[bool]$result.deployed;created_count=[int]$result.created_count;
        boot_verified=$false;k3s_installed=$false;partial_or_uncertain=[bool]$result.partial_or_uncertain;worker_failure_line=[int]$result.failure_line}
    if ($ValidateOnly) {$safe.distinct_host_count=[int]$result.distinct_host_count}
    [IO.File]::WriteAllText($statusPath,($safe|ConvertTo-Json),[Text.Encoding]::UTF8)
    if ($process.ExitCode -ne 0) {exit 2}
} catch {
    $safe=@{status='blocked';code='LOCAL_VM_DEPLOYMENT_LAUNCHER_FAILED';deployed=$false;partial_or_uncertain=($workerStarted -and -not $ValidateOnly)}
    if ($lockStream) {[IO.File]::WriteAllText($statusPath,($safe|ConvertTo-Json),[Text.Encoding]::UTF8)}
    exit 2
} finally {
    $payload=$null;$connection=$null;$target=$null;$privateResult=$null;$result=$null
    if ($process) {$process.Dispose()}
    if ($lockStream) {$lockStream.Dispose()}
}
