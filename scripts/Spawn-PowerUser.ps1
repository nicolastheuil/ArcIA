[CmdletBinding()]
param(
    [Parameter(Position=0, Mandatory=$true, HelpMessage="Email du collaborateur")]
    [string]$Email,

    [Parameter(Mandatory=$false)]
    [string]$Team = "engineering",

    [Parameter(Mandatory=$false)]
    [string]$JobTitle = "Expert / Ingénieur",

    [Parameter(Mandatory=$false)]
    [string]$Manager = "Direction Technique",

    [Parameter(Mandatory=$false)]
    [string]$SoulFile,

    [Parameter(Mandatory=$false)]
    [string]$Storage = "10Gi",

    [Parameter(Mandatory=$false)]
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonScript = Join-Path $ScriptDir "arcia_poweruser.py"

$ArgsList = @($PythonScript, "spawn", $Email, "--team", $Team, "--job-title", $JobTitle, "--manager", $Manager, "--storage", $Storage)

if ($SoulFile) {
    $ArgsList += @("--soul-file", $SoulFile)
}

if ($DryRun) {
    $ArgsList += "--dry-run"
}

python @ArgsList
