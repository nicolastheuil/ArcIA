# This file never returns a secret to stdout. Call only from a local trusted program.
Add-Type -AssemblyName System.Security

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
