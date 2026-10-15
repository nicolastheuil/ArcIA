<#
.SYNOPSIS
    Script de déploiement universel et automatisé d'ArcIA sur Kubernetes.
.DESCRIPTION
    Ce script vérifie l'environnement local, lit le fichier de configuration unique
    'arcia.config.yaml' (ou 'arcia.env') et déploie l'intégralité du socle ArcIA.
.PARAMETER ConfigFile
    Chemin vers le fichier de configuration (défaut : arcia.config.yaml)
.PARAMETER DryRun
    Valide la configuration sans appliquer les changements sur le cluster
.EXAMPLE
    .\scripts\Deploy-ArcIA.ps1
.EXAMPLE
    .\scripts\Deploy-ArcIA.ps1 -ConfigFile .\mon-instance.config.yaml -DryRun
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory=$false)]
    [string]$ConfigFile = "arcia.config.yaml",

    [Parameter(Mandatory=$false)]
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$ScriptDir = $PSScriptRoot
$RootDir = Split-Path $ScriptDir -Parent
$DeployPy = Join-Path $ScriptDir "deploy.py"

# Vérification de Python 3
$PythonCmd = $null
if (Get-Command python -ErrorAction SilentlyContinue) {
    $PythonCmd = "python"
} elseif (Get-Command python3 -ErrorAction SilentlyContinue) {
    $PythonCmd = "python3"
} else {
    Write-Error "Python 3 est requis pour exécuter le déploiement mais n'a pas été trouvé dans le PATH."
    exit 1
}

# Construction des arguments
$ArgsList = @($DeployPy, "--config", $ConfigFile)
if ($DryRun) {
    $ArgsList += "--dry-run"
}

# Exécution du moteur universel de déploiement
& $PythonCmd @ArgsList
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
