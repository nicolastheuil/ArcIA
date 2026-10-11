[CmdletBinding()]
param([switch]$EnforcePlacement)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'ProtectedState.ps1')
$privateRoot=Join-Path $env:LOCALAPPDATA 'ArcIA-Harness'
$statusPath=Join-Path $privateRoot 'vmware-verify-status.json'
$process=$null
try {
    $connection=(Read-ProtectedBundle -Path (Join-Path $privateRoot 'vmware.dpapi'))|ConvertFrom-Json
    $target=(Read-ProtectedBundle -Path (Join-Path $privateRoot 'vmware-target.dpapi'))|ConvertFrom-Json
    $operation=(Read-ProtectedBundle -Path (Join-Path $privateRoot 'vmware-operation.dpapi'))|ConvertFrom-Json
    $start=New-Object Diagnostics.ProcessStartInfo
    $start.FileName=Join-Path $env:LOCALAPPDATA 'ArcIA-Validation\venv\Scripts\python.exe'
    $start.Arguments='"'+(Join-Path $PSScriptRoot 'vmware_verify.py')+'"'
    if($EnforcePlacement){$start.Arguments+=' --enforce-placement'}
    $start.UseShellExecute=$false;$start.CreateNoWindow=$true
    $start.RedirectStandardInput=$true;$start.RedirectStandardOutput=$true;$start.RedirectStandardError=$true
    $start.StandardInputEncoding=New-Object Text.UTF8Encoding($false)
    $process=New-Object Diagnostics.Process;$process.StartInfo=$start
    $null=$process.Start()
    $process.StandardInput.Write((@{connection=$connection;target=$target;operation_id=$operation.id}|ConvertTo-Json -Depth 12));$process.StandardInput.Close()
    $output=$process.StandardOutput.ReadToEndAsync();$errors=$process.StandardError.ReadToEndAsync()
    $process.WaitForExit();$response=$output.GetAwaiter().GetResult();$null=$errors.GetAwaiter().GetResult()
    $result=$response|ConvertFrom-Json
    # This worker returns only fixed codes, counts and booleans.
    [IO.File]::WriteAllText($statusPath,($result|ConvertTo-Json),[Text.Encoding]::UTF8)
    if($process.ExitCode -ne 0){exit 2}
} catch {
    [IO.File]::WriteAllText($statusPath,'{"status":"blocked","code":"LOCAL_VM_VERIFICATION_FAILED","deployed":false}')
    exit 2
} finally {$connection=$null;$target=$null;if($process){$process.Dispose()}}
