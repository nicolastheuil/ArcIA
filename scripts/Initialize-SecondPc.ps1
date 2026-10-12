[CmdletBinding()]
param([switch]$IncludeWsl)
$ErrorActionPreference='Stop'
try{
    if($PSVersionTable.PSVersion -lt [version]'7.4'){throw 'POWERSHELL_7_REQUIRED'}
    foreach($command in @('git','ssh')){if(-not(Get-Command $command -ErrorAction SilentlyContinue)){throw 'SYSTEM_TOOL_MISSING'}}
    $pythonPath=Join-Path $env:LOCALAPPDATA 'ArcIA-Validation/python-3.14.7/python.exe'
    if(-not(Test-Path -LiteralPath $pythonPath)){
        $python=Get-Command python -ErrorAction SilentlyContinue
        if(-not $python){throw 'PYTHON_3_14_REQUIRED'}
        $pythonPath=$python.Source
    }
    $version=& $pythonPath -c 'import sys; print("%d.%d" % sys.version_info[:2])'
    if($LASTEXITCODE -ne 0 -or $version -ne '3.14'){throw 'PYTHON_3_14_REQUIRED'}
    $validation=Join-Path $env:LOCALAPPDATA 'ArcIA-Validation/venv'
    $executable=Join-Path $validation 'Scripts/python.exe'
    if(-not(Test-Path -LiteralPath $executable)){
        & $pythonPath -m venv $validation *> $null
        if($LASTEXITCODE -ne 0){throw 'VALIDATION_ENVIRONMENT_CREATION_FAILED'}
    }
    & $executable -m pip install --require-hashes -r (Join-Path $PSScriptRoot '../requirements-vmware.txt') *> $null
    if($LASTEXITCODE -ne 0){throw 'VMWARE_DEPENDENCIES_FAILED'}
    & $executable -m pip install 'PyYAML==6.0.3' 'jsonschema==4.26.0' *> $null
    if($LASTEXITCODE -ne 0){throw 'VALIDATION_DEPENDENCIES_FAILED'}
    if($IncludeWsl){
        if(-not(Get-Command wsl.exe -ErrorAction SilentlyContinue)){throw 'WSL_REQUIRED'}
        $code=@'
import pathlib,sys,subprocess,venv
if sys.version_info < (3,12): raise SystemExit(2)
root=pathlib.Path.home()/'.local/share/arcia-validation'
if not (root/'bin/python').is_file(): venv.EnvBuilder(with_pip=True).create(root)
requirements=root/'requirements-validation.txt'
requirements.write_text(sys.stdin.read())
result=subprocess.run([str(root/'bin/python'),'-m','pip','install','-r',str(requirements)],capture_output=True)
raise SystemExit(result.returncode)
'@
        $requirements=Get-Content (Join-Path $PSScriptRoot '../requirements-validation.txt') -Raw
        $requirements| & wsl.exe -e /bin/sh -c 'if [ -x "$HOME/.local/share/arcia-validation/bin/python" ]; then exec "$HOME/.local/share/arcia-validation/bin/python" -c "$1"; else exec python3 -c "$1"; fi' 'arcia-prepare' $code *> $null
        if($LASTEXITCODE -ne 0){throw 'WSL_VALIDATION_DEPENDENCIES_FAILED'}
    }
    Write-Output 'SECOND_PC_DEPENDENCIES_PREPARED; NO_DEPLOYMENT_STARTED'
}catch{
    $code=if($_.Exception.Message -in @('POWERSHELL_7_REQUIRED','SYSTEM_TOOL_MISSING','PYTHON_3_14_REQUIRED','VALIDATION_ENVIRONMENT_CREATION_FAILED','VMWARE_DEPENDENCIES_FAILED','VALIDATION_DEPENDENCIES_FAILED','WSL_REQUIRED','WSL_VALIDATION_DEPENDENCIES_FAILED')){$_.Exception.Message}else{'SECOND_PC_INITIALIZATION_FAILED'}
    Write-Output $code;exit 2
}
