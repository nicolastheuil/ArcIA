[CmdletBinding()]
param([Parameter(Mandatory)][ValidateSet('skills','context7','lintlang')][string]$Tool,
    [Parameter(ValueFromRemainingArguments)][string[]]$ToolArguments)
$ErrorActionPreference='Stop'
$previousTelemetry=$env:DISABLE_TELEMETRY
try{
    $env:DISABLE_TELEMETRY='1'
    if($Tool -eq 'lintlang'){
        # WSL inherits cwd as /mnt/...; no private operational paths are scanned.
        & wsl.exe -e sh -c 'exec "$HOME/.local/share/arcia-builder/python/bin/lintlang" "$@"' arcia-lint @ToolArguments
    }else{
        $node=(Get-Command node.exe -ErrorAction Stop).Source
        $relative=if($Tool -eq 'skills'){'skills/bin/cli.mjs'}else{'@upstash/context7-mcp/dist/index.js'}
        $entry=Join-Path $env:LOCALAPPDATA ('ArcIA-Builder/npm/node_modules/'+$relative)
        & $node $entry @ToolArguments
    }
    exit $LASTEXITCODE
}finally{$env:DISABLE_TELEMETRY=$previousTelemetry}
