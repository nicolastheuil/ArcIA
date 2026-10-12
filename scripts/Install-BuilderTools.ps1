[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
$repoRoot=Split-Path $PSScriptRoot -Parent
$toolRoot=Join-Path $env:LOCALAPPDATA 'ArcIA-Builder'
$node=(Get-Command node.exe -ErrorAction Stop).Source
$npm=Join-Path (Split-Path $node) 'node_modules/npm/bin/npm-cli.js'
if(-not(Test-Path -LiteralPath $npm)){throw 'BUILDER_NPM_RUNTIME_REQUIRED'}
$lock=Get-Content -LiteralPath (Join-Path $repoRoot 'builder/tools.lock.json') -Raw|ConvertFrom-Json
$null=New-Item -ItemType Directory -Path (Join-Path $toolRoot 'npm') -Force
Copy-Item -LiteralPath (Join-Path $repoRoot 'builder/npm/package.json') -Destination (Join-Path $toolRoot 'npm/package.json')
Copy-Item -LiteralPath (Join-Path $repoRoot 'builder/npm/package-lock.json') -Destination (Join-Path $toolRoot 'npm/package-lock.json')
$previousTelemetry=$env:DISABLE_TELEMETRY
try{
    $env:DISABLE_TELEMETRY='1'
    & $node $npm ci --prefix (Join-Path $toolRoot 'npm') --ignore-scripts --no-audit --no-fund
    if($LASTEXITCODE -ne 0){throw 'BUILDER_NPM_INSTALL_FAILED'}
    foreach($entry in @(@('skills',$lock.tools.skills_cli.version),@('@upstash/context7-mcp',$lock.tools.context7.version))){
        $package=Get-Content -LiteralPath (Join-Path $toolRoot ('npm/node_modules/'+$entry[0]+'/package.json')) -Raw|ConvertFrom-Json
        if($package.version -ne $entry[1]){throw 'BUILDER_PACKAGE_VERSION_MISMATCH'}
    }
    $source=(Get-Content -LiteralPath (Join-Path $PSScriptRoot 'prepare_builder_python.sh') -Raw).Replace("`r`n","`n")
    $drive=$repoRoot.Substring(0,1).ToLowerInvariant()
    $linuxRepo='/mnt/'+$drive+'/'+$repoRoot.Substring(3).Replace('\','/')
    $source | & wsl.exe -e sh -c 'tr -d "\r" | sh -s -- "$1"' arcia-builder $linuxRepo
    if($LASTEXITCODE -ne 0){throw 'BUILDER_PYTHON_INSTALL_FAILED'}
    'BUILDER_PINNED_CLI_TOOLS_INSTALLED'
}finally{$env:DISABLE_TELEMETRY=$previousTelemetry}
