[CmdletBinding()]
param(
    [Parameter(Position=0, Mandatory=$false, HelpMessage="Email du collaborateur (ou action: list)")]
    [string]$Email,

    [Parameter(Mandatory=$false)]
    [ValidateSet("spawn", "list", "stop", "start", "destroy")]
    [string]$Action = "spawn",

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
    [switch]$KeepPvc,

    [Parameter(Mandatory=$false)]
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonScript = Join-Path $ScriptDir "arcia_poweruser.py"

if ($Email -in @("list", "stop", "start", "destroy") -and $PSBoundParameters.ContainsKey("Action") -eq $false) {
    $Action = $Email
    $Email = $null
}

if ($Action -eq "list") {
    python $PythonScript list
    exit $LASTEXITCODE
}

if (-not $Email) {
    throw "Veuillez spécifier l'adresse email du Power User (ex: .\scripts\Spawn-PowerUser.ps1 prenom.nom@example.org)."
}

if ($Action -in @("stop", "start")) {
    python $PythonScript $Action $Email
    exit $LASTEXITCODE
}

if ($Action -eq "destroy") {
    $DestroyArgs = @($PythonScript, "destroy", $Email)
    if ($KeepPvc) { $DestroyArgs += "--keep-pvc" }
    python @DestroyArgs
    exit $LASTEXITCODE
}

$ArgsList = @($PythonScript, "spawn", $Email, "--team", $Team, "--job-title", $JobTitle, "--manager", $Manager, "--storage", $Storage)

if ($SoulFile) {
    $ArgsList += @("--soul-file", $SoulFile)
}

if ($DryRun) {
    $ArgsList += "--dry-run"
}

python @ArgsList
