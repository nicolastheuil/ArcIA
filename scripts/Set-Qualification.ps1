[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('vmware_compatibility','api_failover','network_review','cpi_design')]
    [string]$Gate,
    [Parameter(Mandatory=$true)][ValidateSet('pending','verified')][string]$Status,
    [Parameter(Mandatory=$true)][ValidateNotNullOrEmpty()][string]$EvidenceRef
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'ProtectedState.ps1')
$privateRoot = Join-Path $env:LOCALAPPDATA 'ArcIA-Harness'
$bundlePath = Join-Path $privateRoot 'instance.dpapi'
$temporaryPath = Join-Path $privateRoot ('update-' + [guid]::NewGuid().ToString('N') + '.dpapi')
try {
    Initialize-PrivateDirectory -Path $privateRoot
    $state = Read-ProtectedBundle -Path $bundlePath | ConvertFrom-Json
    $state.config.gates.$Gate = $Status
    if ($Gate -eq 'network_review') { $state.config.network.existing_cidrs_reviewed = ($Status -eq 'verified') }
    if (-not $state.PSObject.Properties['qualification_evidence']) {
        $state | Add-Member -MemberType NoteProperty -Name qualification_evidence -Value ([pscustomobject]@{})
    }
    $record = @{ status = $Status; evidence_ref = $EvidenceRef; recorded_at = [DateTime]::UtcNow.ToString('o') }
    $state.qualification_evidence | Add-Member -Force -MemberType NoteProperty -Name $Gate -Value $record
    $bundle = $state | ConvertTo-Json -Depth 30
    $validation = $bundle | & python (Join-Path $PSScriptRoot 'harness.py') validate --stdin
    if ($LASTEXITCODE -ne 0) { throw 'QUALIFICATION_VALIDATION_FAILED' }
    Save-ProtectedBundle -Path $temporaryPath -Bundle $bundle
    [IO.File]::Replace($temporaryPath, $bundlePath, $null)
    Write-Host 'QUALIFICATION_RECORDED_LOCALLY; NO_DEPLOYMENT'
} catch {
    Write-Host 'QUALIFICATION_BLOCKED'
    exit 2
} finally {
    if (Test-Path -LiteralPath $temporaryPath) { Remove-Item -LiteralPath $temporaryPath }
    $bundle = $null; $state = $null
}
