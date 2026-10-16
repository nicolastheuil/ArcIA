<#
.SYNOPSIS
    Lanceur Graphique Universel du Setup Wizard ArcIA (Windows PowerShell).
.DESCRIPTION
    Démarre le serveur local autonome du Setup Wizard ArcIA et ouvre automatiquement
    votre navigateur Web pour configurer et déployer l'intégralité de la plateforme.
.EXAMPLE
    .\wizard.ps1
#>
[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$RemainingArgs
)

$ErrorActionPreference = 'Stop'
$ScriptDir = $PSScriptRoot
$WizardPy = Join-Path $ScriptDir "scripts\wizard.py"

# Détection de Python 3
$PythonCmd = $null
if (Get-Command python -ErrorAction SilentlyContinue) {
    $PythonCmd = "python"
} elseif (Get-Command python3 -ErrorAction SilentlyContinue) {
    $PythonCmd = "python3"
} else {
    Write-Error "Python 3 est requis pour lancer le Wizard ArcIA mais n'a pas été trouvé dans le PATH."
    exit 1
}

# Lancement du Wizard
$ArgsList = @($WizardPy) + $RemainingArgs
& $PythonCmd @ArgsList
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
