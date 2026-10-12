[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'ProtectedState.ps1')
$privateRoot=Get-ArcIAStateRoot
$targetPath=Join-Path $privateRoot 'vmware-target.dpapi'
try {
    $target=(Read-ProtectedBundle -Path $targetPath)|ConvertFrom-Json
    $publicPath=[IO.Path]::GetFullPath($target.ssh_public_key_path)
    $sourceRoot=[IO.Path]::GetFullPath((Join-Path (Split-Path $PSScriptRoot -Parent) 'secrets')).TrimEnd('\')+'\'
    if (-not $publicPath.EndsWith('.pub',[StringComparison]::OrdinalIgnoreCase)) {throw 'PUBLIC_KEY_REQUIRED'}
    $keyRoot=Join-Path $privateRoot 'ssh'
    Initialize-PrivateDirectory -Path $keyRoot
    $destinationRoot=[IO.Path]::GetFullPath($keyRoot).TrimEnd('\')+'\'
    if((Split-Path -Parent $publicPath) -eq [IO.Path]::GetFullPath($keyRoot)){
        if(-not(Test-Path -LiteralPath $publicPath) -or -not(Test-Path -LiteralPath $publicPath.Substring(0,$publicPath.Length-4))){throw 'KEY_PAIR_REQUIRED'}
        Write-Host 'PROTECTED_SSH_KEY_PAIR_READY';exit 0
    }
    $privatePath=$publicPath.Substring(0,$publicPath.Length-4)
    foreach ($source in @($privatePath,$publicPath)) {
        $sourceFull=[IO.Path]::GetFullPath($source)
        $destination=[IO.Path]::GetFullPath((Join-Path $keyRoot ([IO.Path]::GetFileName($sourceFull))))
        # Verify both absolute targets before each exact, non-recursive move.
        if (-not $destination.StartsWith($destinationRoot,[StringComparison]::OrdinalIgnoreCase)) {throw 'KEY_PATH_OUTSIDE_DESIGNATED_DIRECTORY'}
        if (-not (Test-Path -LiteralPath $sourceFull)) {throw 'KEY_PAIR_REQUIRED'}
        $sourceItem=Get-Item -LiteralPath $sourceFull
        # OneDrive cloud placeholders also carry ReparsePoint. Refuse links to
        # other paths, while permitting hydration/move of this user's cloud file.
        if ($sourceItem.LinkType -in @('SymbolicLink','Junction') -or $sourceItem.Target) {throw 'KEY_REPARSE_POINT_REFUSED'}
        if(Test-Path -LiteralPath $destination){
            if((Get-FileHash -LiteralPath $sourceFull).Hash -ne (Get-FileHash -LiteralPath $destination).Hash){throw 'EXISTING_DIFFERENT_KEY_REFUSED'}
        }elseif($sourceFull.StartsWith($sourceRoot,[StringComparison]::OrdinalIgnoreCase)){
            Move-Item -LiteralPath $sourceFull -Destination $destination
        }else{
            # Keep an engineer's original key intact; copy only the selected pair.
            Copy-Item -LiteralPath $sourceFull -Destination $destination
        }
        $file=Get-Item -LiteralPath $destination
        $acl=[IO.FileSystemAclExtensions]::GetAccessControl($file,[Security.AccessControl.AccessControlSections]::Access)
        $acl.SetAccessRuleProtection($true,$false)
        foreach($rule in @($acl.Access)){if($null -ne $rule){$null=$acl.RemoveAccessRuleSpecific($rule)}}
        $sid=[Security.Principal.WindowsIdentity]::GetCurrent().User
        $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($sid,'FullControl','Allow')))
        [IO.FileSystemAclExtensions]::SetAccessControl($file,$acl)
    }
    $target.ssh_public_key_path=Join-Path $keyRoot ([IO.Path]::GetFileName($publicPath))
    $temporary=Join-Path $privateRoot ('target-'+[guid]::NewGuid().ToString('N')+'.dpapi')
    Save-ProtectedBundle -Path $temporary -Bundle ($target|ConvertTo-Json -Depth 8)
    [IO.File]::Replace($temporary,$targetPath,[NullString]::Value)
    Write-Host 'PROTECTED_SSH_KEY_PAIR_READY; TARGET_REFERENCE_UPDATED; ACL_RESTRICTED'
} catch {
    Write-Host ('SSH_KEY_PROTECTION_BLOCKED; LOCAL_FAILURE_LINE='+$_.InvocationInfo.ScriptLineNumber+'; TYPE='+$_.Exception.GetType().Name)
    exit 2
} finally {$target=$null}
