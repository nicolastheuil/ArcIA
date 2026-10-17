[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$scriptDir = $PSScriptRoot
$rootDir = Split-Path $scriptDir -Parent
$envFile = Join-Path $rootDir 'secrets\arcia.env'

if (-not (Test-Path -LiteralPath $envFile)) {
    throw "Secrets file not found: $envFile"
}

# Parse .env file
$envVars = @{}
Get-Content -LiteralPath $envFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith('#') -and $line.Contains('=')) {
        $idx = $line.IndexOf('=')
        $key = $line.Substring(0, $idx).Trim()
        $val = $line.Substring($idx + 1).Trim().Trim('"').Trim("'")
        $envVars[$key] = $val
    }
}

Write-Host "[*] Application des Secrets Kubernetes dans le namespace arcia..."

function Invoke-K3sShell {
    param([string]$ShellCmd)
    pwsh -NoProfile -File (Join-Path $scriptDir 'Invoke-K3s.ps1') -RawShell $ShellCmd
}

# 1. enterprise-llm-secret & litellm-secret
$openRouterKey = $envVars['OPENROUTER_API_KEY']
$litellmMaster = if ($envVars['LITELLM_MASTER_KEY']) { $envVars['LITELLM_MASTER_KEY'] } else { "sk-arcia-master-$(Get-Random)" }
$litellmDbPass = if ($envVars['LITELLM_POSTGRES_PASSWORD']) { $envVars['LITELLM_POSTGRES_PASSWORD'] } else { "ArcIA_DB_$(Get-Random)" }
$litellmDbUrl = "postgresql://litellm:$litellmDbPass@litellm-db.arcia.svc:5432/litellm"
Invoke-K3sShell "/usr/local/bin/k3s kubectl create secret generic enterprise-llm-secret --namespace arcia --from-literal=openrouter-key='$openRouterKey' --dry-run=client -o yaml | /usr/local/bin/k3s kubectl apply -f -"
Invoke-K3sShell "/usr/local/bin/k3s kubectl create secret generic litellm-secret --namespace arcia --from-literal=master-key='$litellmMaster' --from-literal=openrouter-key='$openRouterKey' --from-literal=db-password='$litellmDbPass' --from-literal=database-url='$litellmDbUrl' --dry-run=client -o yaml | /usr/local/bin/k3s kubectl apply -f -"

# 2. entraid-secret
$clientId = $envVars['ENTRA_CLIENT_ID']
$clientSecret = $envVars['ENTRA_CLIENT_SECRET']
$tenantId = $envVars['ENTRA_TENANT_ID']
$cookieSecret = $envVars['OAUTH2_PROXY_COOKIE_SECRET']
Invoke-K3sShell "/usr/local/bin/k3s kubectl create secret generic entraid-secret --namespace arcia --from-literal=client-id='$clientId' --from-literal=client-secret='$clientSecret' --from-literal=tenant-id='$tenantId' --from-literal=cookie-secret='$cookieSecret' --dry-run=client -o yaml | /usr/local/bin/k3s kubectl apply -f -"

# 3. hermes-gateway-secret
$hermesKey = $envVars['HERMES_API_SERVER_KEY']
$hermesPass = if ($envVars['HERMES_ADMIN_PASSWORD']) { $envVars['HERMES_ADMIN_PASSWORD'] } else { 'admin' }
Invoke-K3sShell "/usr/local/bin/k3s kubectl create secret generic hermes-gateway-secret --namespace arcia --from-literal=api-server-key='$hermesKey' --from-literal=admin-password='$hermesPass' --dry-run=client -o yaml | /usr/local/bin/k3s kubectl apply -f -"

# 4. teams-bot-secret
$teamsId = $envVars['TEAMS_BOT_APP_ID']
$teamsPwd = $envVars['TEAMS_BOT_APP_PASSWORD']
Invoke-K3sShell "/usr/local/bin/k3s kubectl create secret generic teams-bot-secret --namespace arcia --from-literal=app-id='$teamsId' --from-literal=app-password='$teamsPwd' --dry-run=client -o yaml | /usr/local/bin/k3s kubectl apply -f -"

# 5. presidio-secret
$presidioKey = $envVars['PRESIDIO_MASTER_KEY']
Invoke-K3sShell "/usr/local/bin/k3s kubectl create secret generic presidio-secret --namespace arcia --from-literal=master-key='$presidioKey' --dry-run=client -o yaml | /usr/local/bin/k3s kubectl apply -f -"

Write-Host "[+] Tous les secrets Kubernetes ont été appliqués avec succès."

