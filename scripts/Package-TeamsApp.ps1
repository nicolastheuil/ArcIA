<#
.SYNOPSIS
    Génère l'archive de package Microsoft Teams (.zip) pour ArcIA prête à être importée dans dev.teams.microsoft.com.

.DESCRIPTION
    Ce script vérifie la conformité du manifeste Teams et des icônes (color.png 192x192, outline.png 32x32),
    et assemble l'archive .zip requise par le Portail Développeur Teams.

.PARAMETER BotId
    Optionnel. L'ID d'application Microsoft (GUID) du bot Azure / Entra ID.

.PARAMETER AppId
    Optionnel. Le GUID unique de l'application Teams (généré automatiquement si omis).

.PARAMETER Name
    Optionnel. Nom court personnalisé (défaut : ArcIA).

.PARAMETER Domain
    Optionnel. FQDN ou domaine d'instance supplémentaire à autoriser.

.PARAMETER Output
    Chemin de l'archive de sortie (défaut : assets/teams/arcia-teams-app.zip).

.PARAMETER CheckOnly
    Valide les fichiers sans générer l'archive .zip.

.EXAMPLE
    .\scripts\Package-TeamsApp.ps1

.EXAMPLE
    .\scripts\Package-TeamsApp.ps1 -BotId "12345678-1234-1234-1234-123456789abc"
#>

[CmdletBinding()]
param(
    [string]$BotId,
    [string]$AppId,
    [string]$Name,
    [string]$Domain,
    [string]$Output = "assets/teams/arcia-teams-app.zip",
    [switch]$NoBot,
    [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$projectRoot = Split-Path -Parent $scriptDir
$pythonScript = Join-Path $scriptDir "package_teams_app.py"

$pythonCmd = "python"
if (-not (Get-Command $pythonCmd -ErrorAction SilentlyContinue)) {
    if (Get-Command "py" -ErrorAction SilentlyContinue) {
        $pythonCmd = "py"
    } else {
        Write-Error "Python 3 est requis mais introuvable dans le PATH."
        exit 1
    }
}

$argsList = @($pythonScript, "--output", $Output)

if ($BotId) {
    $argsList += @("--bot-id", $BotId)
}
if ($AppId) {
    $argsList += @("--app-id", $AppId)
}
if ($Name) {
    $argsList += @("--name", $Name)
}
if ($Domain) {
    $argsList += @("--domain", $Domain)
}
if ($NoBot) {
    $argsList += @("--no-bot")
}
if ($CheckOnly) {
    $argsList += @("--check-only")
}

& $pythonCmd $argsList
exit $LASTEXITCODE
