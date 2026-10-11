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
    $acl = New-Object Security.AccessControl.DirectorySecurity
    $acl.SetAccessRuleProtection($true, $false)
    $rule = New-Object Security.AccessControl.FileSystemAccessRule($sid, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
    $acl.AddAccessRule($rule)
    Set-Acl -LiteralPath $fullPath -AclObject $acl
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
