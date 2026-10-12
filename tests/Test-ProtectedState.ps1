$ErrorActionPreference = 'Stop'
. (Join-Path (Split-Path $PSScriptRoot -Parent) 'scripts/ProtectedState.ps1')
$testDirectory = Join-Path $env:LOCALAPPDATA ('ArcIA-Validation\dpapi-' + [guid]::NewGuid().ToString('N'))
Initialize-PrivateDirectory -Path $testDirectory
$path = Join-Path $testDirectory 'synthetic.dpapi'
try {
    $canary = '{"canary":"SYNTHETIC_DPAPI_TEST"}'
    Save-ProtectedBundle -Path $path -Bundle $canary
    Initialize-PrivateDirectory -Path $testDirectory
    if ((Read-ProtectedBundle -Path $path) -cne $canary) { throw 'DPAPI_ROUNDTRIP_FAILED' }
    $replacement = Join-Path $testDirectory 'replacement.dpapi'
    Save-ProtectedBundle -Path $replacement -Bundle $canary
    [IO.File]::Replace($replacement, $path, [NullString]::Value)
    if ((Read-ProtectedBundle -Path $path) -cne $canary) { throw 'DPAPI_REPLACEMENT_FAILED' }
    if ([Text.Encoding]::UTF8.GetString([IO.File]::ReadAllBytes($path)).Contains('SYNTHETIC_DPAPI_TEST')) { throw 'PLAINTEXT_LEAK' }
    $blocked = $false
    try { Save-ProtectedBundle -Path $path -Bundle $canary } catch { $blocked = $true }
    if (-not $blocked) { throw 'OVERWRITE_NOT_BLOCKED' }
    $workspaceBlocked = $false
    try { Initialize-PrivateDirectory -Path (Join-Path (Split-Path $PSScriptRoot -Parent) 'private-test') } catch { $workspaceBlocked = $true }
    if (-not $workspaceBlocked) { throw 'WORKSPACE_NOT_BLOCKED' }
    $rules = (Get-Acl -LiteralPath $testDirectory).Access
    if (@($rules).Count -ne 1 -or $rules[0].IsInherited) { throw 'ACL_NOT_RESTRICTED' }
    $operationPath=Join-Path $testDirectory 'vmware-operation.dpapi'
    Save-ProtectedBundle -Path $operationPath -Bundle '{"id":"synthetic-operation"}'
    $physicalRoot=Get-PhysicalArcIARoot $testDirectory
    if(-not(Test-Path -LiteralPath (Join-Path $physicalRoot 'vmware-operation.dpapi'))){throw 'PHYSICAL_PATH_NOT_RESOLVED'}
    Remove-Item -LiteralPath $operationPath
    Write-Host 'DPAPI_ROUNDTRIP_OK; ATOMIC_REPLACEMENT_OK; PLAINTEXT_ABSENT; OVERWRITE_BLOCKED; WORKSPACE_BLOCKED; ACL_RESTRICTED'
} finally {
    # Exact synthetic files only, no recursive directory removal.
    if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path }
    if ($operationPath -and (Test-Path -LiteralPath $operationPath)) {Remove-Item -LiteralPath $operationPath}
    if (Test-Path -LiteralPath $testDirectory) { Remove-Item -LiteralPath $testDirectory }
}
