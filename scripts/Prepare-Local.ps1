[CmdletBinding()]
param([ValidateSet('plan','render','preflight')][string]$Action = 'plan')
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'ProtectedState.ps1')
$privateRoot = Get-ArcIAStateRoot
$bundlePath = Join-Path $privateRoot 'instance.dpapi'
try {
    Initialize-PrivateDirectory -Path $privateRoot
    $bundle = Read-ProtectedBundle -Path $bundlePath
    $arguments = @((Join-Path $PSScriptRoot 'harness.py'), $Action, '--stdin')
    if ($Action -eq 'render') {
        $transit = Join-Path $privateRoot ('transit-' + [guid]::NewGuid().ToString('N'))
        Initialize-PrivateDirectory -Path $transit
        # Inherits only the current-user ACL set by Configure-Local.ps1.
        $arguments += @('--output-dir', $transit)
    }
    $bundle | & python @arguments
    if ($LASTEXITCODE -ne 0) { throw 'PREPARATION_FAILED' }
    if ($Action -eq 'render') { Write-Host 'PRIVATE_INVENTORY_RENDERED_IN_LOCALAPPDATA; NEVER_COPY_TO_CHAT_OR_GIT' }
} catch {
    Write-Host 'PREPARATION_BLOCKED (configuration absente, DPAPI ou validation).'
    exit 2
} finally {
    $bundle = $null
}
