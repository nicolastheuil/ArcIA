[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'ProtectedState.ps1')
$repoRoot = Split-Path $PSScriptRoot -Parent
$privateRoot = Join-Path $env:LOCALAPPDATA 'ArcIA-Harness'
$bundlePath = Join-Path $privateRoot 'instance.dpapi'
try {
    if (Test-Path -LiteralPath $bundlePath) { throw 'EXISTING_CONFIGURATION' }
    Initialize-PrivateDirectory -Path $privateRoot
    Write-Host 'Saisie locale : les valeurs ne doivent pas etre copiees dans le chat.'
    $config = Get-Content -LiteralPath (Join-Path $repoRoot 'examples/synthetic/instance.json') -Raw | ConvertFrom-Json
    $config.synthetic = $false
    $config.github.account = Read-Host 'Compte/organisation GitHub (nicolastheuil pour ArcIA)'
    $config.github.repository = Read-Host 'Depot GitHub (arcia-harness pour ArcIA)'
    foreach ($node in $config.nodes) {
        $node.address = Read-Host ("IPv4 privee de " + $node.name)
        $node.ssh_user = Read-Host 'Utilisateur SSH personnel'
        $node.ssh_port = [int](Read-Host 'Port SSH')
        $node.identity_file = Read-Host 'Chemin Windows de votre cle SSH (rendu WSL automatique)'
        $node.known_hosts_file = Read-Host 'Chemin Windows known_hosts (empreintes verifiees hors bande)'
    }
    $config.network.api_endpoint = Read-Host 'FQDN API privee avec bascule'
    $config.network.public_hostname = Read-Host 'FQDN HTTPS metier'
    $config.network.pod_cidr = Read-Host 'CIDR IPv4 Pods'
    $config.network.service_cidr = Read-Host 'CIDR IPv4 Services'
    $cidrs = Read-Host 'CIDR entreprise/VPN/clients connus, separes par virgule'
    $config.network.existing_cidrs = @($cidrs.Split(',') | ForEach-Object { $_.Trim() } | Where-Object { $_ })
    $config.storage.storage_class = Read-Host 'Nom de StorageClass CSI prevu'
    $config.storage.policy_ref = Read-Host 'Reference de storage policy VMware'
    # Gates remain pending: entering a value never qualifies compatibility/failover.
    $random = New-Object byte[] 32
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($random)
    $rng.Dispose()
    $token = [BitConverter]::ToString($random).Replace('-', '').ToLowerInvariant()
    $bundle = @{ config = $config; k3s_token = $token } | ConvertTo-Json -Depth 20
    $validation = $bundle | & python (Join-Path $PSScriptRoot 'harness.py') validate --stdin
    if ($LASTEXITCODE -ne 0) { throw 'CONFIG_VALIDATION_FAILED' }
    Save-ProtectedBundle -Path $bundlePath -Bundle $bundle
    Write-Host 'CONFIGURATION_ENCRYPTED; GATES_PENDING'
} catch {
    Write-Host 'CONFIGURATION_BLOCKED (configuration existante, saisie invalide ou protection locale indisponible).'
    exit 2
} finally {
    if ($random) { [Array]::Clear($random, 0, $random.Length) }
    $bundle = $null; $token = $null
}
