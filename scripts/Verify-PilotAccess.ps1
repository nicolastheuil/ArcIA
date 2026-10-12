[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'ProtectedState.ps1')
$root=Join-Path $env:LOCALAPPDATA 'ArcIA-Harness'
$pilot=(Read-ProtectedBundle (Join-Path $root 'pilot-credentials.dpapi'))|ConvertFrom-Json
$instance=(Read-ProtectedBundle (Join-Path $root 'instance.dpapi'))|ConvertFrom-Json
if($pilot.operation_id -ne $instance.operation_id){throw 'PILOT_CREDENTIAL_SCOPE_CONFLICT'}
$start=[Diagnostics.ProcessStartInfo]::new()
$start.FileName=Join-Path $env:LOCALAPPDATA 'ArcIA-Validation/venv/Scripts/python.exe'
$start.Arguments='"'+(Join-Path $PSScriptRoot 'verify_pilot_access.py')+'"'
$start.UseShellExecute=$false;$start.CreateNoWindow=$true
$start.RedirectStandardInput=$true;$start.RedirectStandardOutput=$true;$start.RedirectStandardError=$true
$start.StandardInputEncoding=[Text.UTF8Encoding]::new($false)
$process=[Diagnostics.Process]::new();$process.StartInfo=$start
try{
    $null=$process.Start()
    $process.StandardInput.Write((@{pilot=$pilot;address=$instance.endpoint_design.https_ip}|ConvertTo-Json -Depth 10 -Compress))
    $process.StandardInput.Close()
    $output=$process.StandardOutput.ReadToEndAsync();$errors=$process.StandardError.ReadToEndAsync()
    if(-not $process.WaitForExit(120000)){$process.Kill();throw 'PILOT_VERIFICATION_TIMEOUT'}
    $safe=$output.GetAwaiter().GetResult()|ConvertFrom-Json;$null=$errors.GetAwaiter().GetResult()
    [IO.File]::WriteAllText((Join-Path $root 'pilot-access-status.json'),($safe|ConvertTo-Json -Depth 8),[Text.Encoding]::UTF8)
    $safe|ConvertTo-Json -Depth 8
    if($process.ExitCode -ne 0){exit 2}
}finally{$process.Dispose();$pilot=$null;$instance=$null}
