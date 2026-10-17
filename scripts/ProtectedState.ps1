# This file never returns a secret to stdout. Call only from a local trusted program.
Add-Type -AssemblyName System.Security

function Get-ArcIAStateCandidates {
    $primary=Join-Path $env:LOCALAPPDATA 'ArcIA-Harness'
    $candidates=@($primary)
    if($env:ARCIA_STATE_ROOT){
        $candidates+=@($env:ARCIA_STATE_ROOT)
    }
    return @($candidates|Select-Object -Unique)
}

function Test-ArcIAIdentityState {
    param([Parameter(Mandatory=$true)][string]$Path)
    $operation=$null;$instance=$null;$identity=$null
    try{
        $operation=(Read-ProtectedBundle (Join-Path $Path 'vmware-operation.dpapi'))|ConvertFrom-Json
        $instance=(Read-ProtectedBundle (Join-Path $Path 'instance.dpapi'))|ConvertFrom-Json
        $identity=(Read-ProtectedBundle (Join-Path $Path 'identity.dpapi'))|ConvertFrom-Json
        return [bool]($operation.id -and $operation.id -eq $instance.operation_id -and
            $operation.id -eq $identity.operation_id -and $identity.admin_username -and
            $identity.admin_password -and $instance.config.network.public_hostname -and
            $instance.endpoint_design.https_ip)
    }catch{return $false}finally{$operation=$null;$instance=$null;$identity=$null}
}

function Select-ArcIAStateRootLocally {
    param([Parameter(Mandatory=$true)][string[]]$Candidates)
    # Private hostnames and paths stay in this local UI. Never log a choice.
    Add-Type -AssemblyName System.Windows.Forms
    $form=[Windows.Forms.Form]::new();$form.Text="ArcIA — choisir l'instance à administrer"
    $form.Width=900;$form.Height=340;$form.StartPosition='CenterScreen'
    $note=[Windows.Forms.Label]::new()
    $note.Text="Plusieurs états protégés sont disponibles. Choisissez l'instance voulue ; aucun compte ni fichier ne sera modifié."
    $note.SetBounds(15,15,850,45);$form.Controls.Add($note)
    $list=[Windows.Forms.ListBox]::new();$list.SetBounds(15,65,850,170)
    $list.HorizontalScrollbar=$true
    foreach($candidate in $Candidates){
        $instance=$null
        try{
            $instance=(Read-ProtectedBundle (Join-Path $candidate 'instance.dpapi'))|ConvertFrom-Json
            $null=$list.Items.Add(($instance.config.network.public_hostname+' — '+$candidate))
        }finally{$instance=$null}
    }
    $form.Controls.Add($list)
    $open=[Windows.Forms.Button]::new();$open.Text='Utiliser cette instance';$open.Enabled=$false
    $open.SetBounds(430,250,220,30);$open.DialogResult=[Windows.Forms.DialogResult]::OK
    $cancel=[Windows.Forms.Button]::new();$cancel.Text='Annuler'
    $cancel.SetBounds(665,250,200,30);$cancel.DialogResult=[Windows.Forms.DialogResult]::Cancel
    $form.Controls.Add($open);$form.Controls.Add($cancel)
    $list.Add_SelectedIndexChanged({$open.Enabled=$list.SelectedIndex -ge 0})
    $form.AcceptButton=$open;$form.CancelButton=$cancel
    try{
        if($form.ShowDialog() -ne [Windows.Forms.DialogResult]::OK -or $list.SelectedIndex -lt 0){
            throw 'PROTECTED_ARCIA_STATE_SELECTION_CANCELLED'
        }
        return $Candidates[$list.SelectedIndex]
    }finally{$form.Dispose()}
}

function Get-ArcIAStateRoot {
    param([switch]$Identity,[switch]$SelectLocally)
    # Automated entry points still refuse ambiguity; only an interactive caller
    # explicitly requests a local choice. Identity requires all three scopes.
    if($env:ARCIA_STATE_ROOT){
        $candidate=[IO.Path]::GetFullPath($env:ARCIA_STATE_ROOT)
        if($Identity -and -not(Test-ArcIAIdentityState $candidate)){throw 'PROTECTED_ARCIA_IDENTITY_STATE_NOT_FOUND'}
        Initialize-PrivateDirectory $candidate
        return $candidate
    }
    $primary=Join-Path $env:LOCALAPPDATA 'ArcIA-Harness'
    $valid=@()
    foreach($candidate in (Get-ArcIAStateCandidates)){
        if(-not(Test-Path -LiteralPath $candidate)){continue}
        if((Get-Item -LiteralPath $candidate).Attributes -band [IO.FileAttributes]::ReparsePoint){continue}
        if($Identity -and -not(Test-ArcIAIdentityState $candidate)){continue}
        foreach($name in @('vmware-operation.dpapi','vmware.dpapi','instance.dpapi')){
            $path=Join-Path $candidate $name
            if(-not(Test-Path -LiteralPath $path)){continue}
            try{
                $value=(Read-ProtectedBundle $path)|ConvertFrom-Json
                if(-not $value){continue}
                $resolved=if(Test-Path -LiteralPath (Join-Path $candidate 'vmware-operation.dpapi')){Get-PhysicalArcIARoot $candidate}else{$candidate}
                $valid+=,$resolved
                break
            }catch{}finally{$value=$null}
        }
    }
    # Windows paths are case insensitive.
    $unique=[Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    $valid=@($valid|Where-Object {$unique.Add([IO.Path]::GetFullPath($_).TrimEnd('\'))})
    if($valid.Count -gt 1){
        if($Identity -and $SelectLocally){return Select-ArcIAStateRootLocally -Candidates $valid}
        throw 'MULTIPLE_PROTECTED_ARCIA_STATES_REFUSED'
    }
    if($valid.Count -eq 1){return $valid[0]}
    if($Identity){throw 'PROTECTED_ARCIA_IDENTITY_STATE_NOT_FOUND'}
    return $primary
}

function Get-PhysicalArcIARoot {
    param([Parameter(Mandatory=$true)][string]$Path)
    if(-not ('ArcIAProtectedPath.Native' -as [type])){
        Add-Type -TypeDefinition @'
using System;
using System.Text;
using System.Runtime.InteropServices;
namespace ArcIAProtectedPath {
 public static class Native {
  [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
  public static extern uint GetFinalPathNameByHandleW(IntPtr handle, StringBuilder path, uint count, uint flags);
 }
}
'@
    }
    $stream=[IO.File]::OpenRead((Join-Path $Path 'vmware-operation.dpapi'))
    try{
        $buffer=[Text.StringBuilder]::new(4096)
        $count=[ArcIAProtectedPath.Native]::GetFinalPathNameByHandleW($stream.SafeFileHandle.DangerousGetHandle(),$buffer,4096,0)
        if($count -eq 0 -or $count -ge 4096){throw 'PROTECTED_PATH_RESOLUTION_FAILED'}
        $resolved=$buffer.ToString()
        if($resolved.StartsWith('\\?\')){$resolved=$resolved.Substring(4)}
        return Split-Path -Parent $resolved
    }finally{$stream.Dispose()}
}

function Get-ArcIAPrivateRoot {
    $primary=Join-Path $env:LOCALAPPDATA 'ArcIA-Harness'
    $candidates=@(Get-ArcIAStateCandidates)
    $valid=@()
    foreach($candidate in ($candidates|Select-Object -Unique)){
        $pilotPath=Join-Path $candidate 'pilot-credentials.dpapi'
        $operationPath=Join-Path $candidate 'vmware-operation.dpapi'
        if(-not(Test-Path -LiteralPath $pilotPath) -or -not(Test-Path -LiteralPath $operationPath)){continue}
        if((Get-Item -LiteralPath $candidate).Attributes -band [IO.FileAttributes]::ReparsePoint){continue}
        try{
            $access=(Read-ProtectedBundle $pilotPath)|ConvertFrom-Json
            $identity=(Read-ProtectedBundle $operationPath)|ConvertFrom-Json
            if($access.operation_id -ne $identity.id -or -not $access.username -or -not $access.password){continue}
            if($candidate -eq $primary){return Get-PhysicalArcIARoot $primary}
            $valid+=,$candidate
        }catch{
            # Another Windows account's DPAPI data is never adopted.
        }finally{$access=$null;$identity=$null}
    }
    if($valid.Count -eq 1){return Get-PhysicalArcIARoot $valid[0]}
    if($valid.Count -gt 1){throw 'MULTIPLE_PROTECTED_ARCIA_STATES_REFUSED'}
    throw 'PROTECTED_DASHBOARD_CREDENTIALS_NOT_FOUND_FOR_CURRENT_WINDOWS_USER'
}

function Initialize-PrivateDirectory {
    param([Parameter(Mandatory=$true)][string]$Path)
    $fullPath = [IO.Path]::GetFullPath($Path)
    $workspace = [IO.Path]::GetFullPath((Split-Path $PSScriptRoot -Parent)).TrimEnd('\') + '\'
    if (($fullPath.TrimEnd('\') + '\').StartsWith($workspace, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'PRIVATE_PATH_INSIDE_WORKSPACE'
    }
    foreach ($syncPath in @($env:OneDrive, $env:OneDriveCommercial, $env:OneDriveConsumer)) {
        if ($syncPath -and ($fullPath.TrimEnd('\') + '\').StartsWith(([IO.Path]::GetFullPath($syncPath).TrimEnd('\') + '\'), [StringComparison]::OrdinalIgnoreCase)) {
            throw 'PRIVATE_PATH_INSIDE_SYNC'
        }
    }
    $null = New-Item -ItemType Directory -Force -Path $fullPath
    if ((Get-Item -LiteralPath $fullPath).Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw 'PRIVATE_DIRECTORY_REPARSE_POINT'
    }
    $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User
    # Read/write the access section only: re-opening an existing directory must
    # not request the SACL privilege (SeSecurityPrivilege).
    $directory = Get-Item -LiteralPath $fullPath
    if ($PSVersionTable.PSEdition -eq 'Core') {
        $acl = [IO.FileSystemAclExtensions]::GetAccessControl($directory, [Security.AccessControl.AccessControlSections]::Access)
    } else {
        $acl = $directory.GetAccessControl([Security.AccessControl.AccessControlSections]::Access)
    }
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($existingRule in @($acl.Access)) {
        if ($null -ne $existingRule) { $null = $acl.RemoveAccessRuleSpecific($existingRule) }
    }
    $rule = New-Object Security.AccessControl.FileSystemAccessRule($sid, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
    $acl.AddAccessRule($rule)
    if ($PSVersionTable.PSEdition -eq 'Core') {
        [IO.FileSystemAclExtensions]::SetAccessControl($directory, $acl)
    } else {
        $directory.SetAccessControl($acl)
    }
}

function Save-ProtectedBundle {
    param([string]$Path, [string]$Bundle)
    if (Test-Path -LiteralPath $Path) { throw 'EXISTING_CONFIGURATION' }
    $bytes = [Text.Encoding]::UTF8.GetBytes($Bundle)
    try {
        $encrypted = [Security.Cryptography.ProtectedData]::Protect($bytes, $null, [Security.Cryptography.DataProtectionScope]::CurrentUser)
        $stream = [IO.File]::Open($Path, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
        try { $stream.Write($encrypted, 0, $encrypted.Length) } finally { $stream.Dispose() }
    } finally {
        [Array]::Clear($bytes, 0, $bytes.Length)
    }
}

function Read-ProtectedBundle {
    param([string]$Path)
    $bytes = [Security.Cryptography.ProtectedData]::Unprotect([IO.File]::ReadAllBytes($Path), $null, [Security.Cryptography.DataProtectionScope]::CurrentUser)
    try { return [Text.Encoding]::UTF8.GetString($bytes) } finally {
        [Array]::Clear($bytes, 0, $bytes.Length)
    }
}
