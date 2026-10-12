[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'ProtectedState.ps1')
$stateRoot=Join-Path $env:LOCALAPPDATA 'ArcIA-Harness'
Initialize-PrivateDirectory $stateRoot
$configRoot=if($env:CODEX_HOME){$env:CODEX_HOME}else{Join-Path $env:USERPROFILE '.codex'}
$configPath=Join-Path $configRoot 'config.toml'
$entry=Join-Path $env:LOCALAPPDATA 'ArcIA-Builder/npm/node_modules/@upstash/context7-mcp/dist/index.js'
if(-not(Test-Path -LiteralPath $entry)){throw 'PINNED_CONTEXT7_INSTALL_REQUIRED'}
if(Test-Path -LiteralPath $configPath){
    Save-ProtectedBundle (Join-Path $stateRoot ('codex-config-before-'+[guid]::NewGuid().ToString('N')+'.dpapi')) `
        (@{config=[IO.File]::ReadAllText($configPath)}|ConvertTo-Json -Compress)
}
$payload=@{config_path=$configPath;node=(Get-Command node.exe).Source;entry=$entry}
$start=[Diagnostics.ProcessStartInfo]::new()
$start.FileName=Join-Path $env:LOCALAPPDATA 'ArcIA-Validation/venv/Scripts/python.exe'
$start.Arguments='"'+(Join-Path $PSScriptRoot 'register_builder_mcp.py')+'"'
$start.UseShellExecute=$false;$start.CreateNoWindow=$true
$start.RedirectStandardInput=$true;$start.RedirectStandardOutput=$true;$start.RedirectStandardError=$true
$start.StandardInputEncoding=[Text.UTF8Encoding]::new($false)
$process=[Diagnostics.Process]::new();$process.StartInfo=$start
try{
    $null=$process.Start()
    $process.StandardInput.Write(($payload|ConvertTo-Json -Compress));$process.StandardInput.Close()
    $output=$process.StandardOutput.ReadToEndAsync();$errors=$process.StandardError.ReadToEndAsync()
    if(-not $process.WaitForExit(30000)){$process.Kill();throw 'BUILDER_MCP_REGISTRATION_TIMEOUT'}
    $safe=$output.GetAwaiter().GetResult()|ConvertFrom-Json;$null=$errors.GetAwaiter().GetResult()
    $safe|ConvertTo-Json -Compress
    if($process.ExitCode -ne 0){exit 2}
}finally{$process.Dispose();$payload=$null}
