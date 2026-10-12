[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'ProtectedState.ps1')
$stateRoot=Join-Path $env:LOCALAPPDATA 'ArcIA-Harness'
Initialize-PrivateDirectory $stateRoot
$configRoot=if($env:CODEX_HOME){$env:CODEX_HOME}else{Join-Path $env:USERPROFILE '.codex'}
$config=Join-Path $configRoot 'config.toml'
if(Test-Path -LiteralPath $config){
    Save-ProtectedBundle (Join-Path $stateRoot ('codex-before-uninstall-'+[guid]::NewGuid().ToString('N')+'.dpapi')) `
        (@{config=[IO.File]::ReadAllText($config)}|ConvertTo-Json -Compress)
}
$start=[Diagnostics.ProcessStartInfo]::new()
$start.FileName=Join-Path $env:LOCALAPPDATA 'ArcIA-Validation/venv/Scripts/python.exe'
$start.ArgumentList.Add((Join-Path $PSScriptRoot 'register_builder_mcp.py'))
$start.UseShellExecute=$false;$start.CreateNoWindow=$true
$start.RedirectStandardInput=$true;$start.RedirectStandardOutput=$true;$start.RedirectStandardError=$true
$start.StandardInputEncoding=[Text.UTF8Encoding]::new($false)
$process=[Diagnostics.Process]::new();$process.StartInfo=$start
try{
    $null=$process.Start()
    $process.StandardInput.Write((@{action='unregister';config_path=$config;
        entry=(Join-Path $env:LOCALAPPDATA 'ArcIA-Builder/npm/node_modules/@upstash/context7-mcp/dist/index.js')}|ConvertTo-Json -Compress))
    $process.StandardInput.Close()
    $output=$process.StandardOutput.ReadToEndAsync();$errors=$process.StandardError.ReadToEndAsync()
    $process.WaitForExit();$result=$output.GetAwaiter().GetResult()|ConvertFrom-Json;$null=$errors.GetAwaiter().GetResult()
    if($process.ExitCode -ne 0){throw 'LOCAL_MCP_UNINSTALL_REFUSED'}
}finally{$process.Dispose()}
$localBase=[IO.Path]::GetFullPath($env:LOCALAPPDATA).TrimEnd('\')
$toolRoot=[IO.Path]::GetFullPath((Join-Path $localBase 'ArcIA-Builder'))
if($toolRoot -ne ($localBase+'\ArcIA-Builder')){throw 'LOCAL_UNINSTALL_BOUNDARY'}
if(Test-Path -LiteralPath $toolRoot){
    $entry=Get-Item -LiteralPath $toolRoot -Force
    if($entry.Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'LOCAL_UNINSTALL_REPARSE_REFUSED'}
    Remove-Item -LiteralPath $toolRoot -Recurse -Force
}
$code=@'
from pathlib import Path
import shutil
root=Path.home()/'.local/share/arcia-builder'
expected=Path.home().resolve()/'.local/share/arcia-builder'
if root.is_symlink() or root.resolve()!=expected:raise ValueError('WSL_UNINSTALL_BOUNDARY')
if root.exists():shutil.rmtree(root)
print('WSL_BUILDER_TOOLS_REMOVED')
'@
& wsl.exe -e sh -c 'exec "$HOME/.local/share/arcia-validation/bin/python" -c "$1"' arcia-cleanup $code
if($LASTEXITCODE -ne 0){throw 'WSL_TOOLS_UNINSTALL_FAILED'}
[IO.File]::WriteAllText((Join-Path $stateRoot 'workstation-tools-removal-status.json'),
    '{"status":"removed","code":"WORKSTATION_TOOLS_AND_CODEX_MCP_REMOVED","admin_runtime_preserved":true}')
'WORKSTATION_TOOLS_AND_CODEX_MCP_REMOVED'
