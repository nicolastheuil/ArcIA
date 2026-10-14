[CmdletBinding()]
param([switch]$IncludeWsl)
$ErrorActionPreference='Stop'
# User-scoped toolchain only; no registry, PATH, system Python or private state changes.
$directory=Join-Path $env:LOCALAPPDATA 'ArcIA-Validation'
$download=Join-Path $directory 'downloads'
$runtime=Join-Path $directory 'python-3.14.7'
$archive=Join-Path $download 'python-3.14.7-amd64.zip'
$expected='ac1a727a71738e11de80b76e975f9b8a258aea6412bfc31696b929d59c6aafd0'
# python.org/ftp/python/3.14.7/windows-3.14.7.json, pythoncore-3.14-64.
if(-not [Environment]::Is64BitProcess){throw 'AMD64_POWERSHELL_REQUIRED'}
$null=New-Item -ItemType Directory -Path $download -Force
if(-not(Test-Path -LiteralPath $archive)){
    Invoke-WebRequest 'https://www.python.org/ftp/python/3.14.7/python-3.14.7-amd64.zip' -OutFile $archive
}
if((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne $expected){throw 'PYTHON_ARCHIVE_HASH_MISMATCH'}
if(-not(Test-Path -LiteralPath $runtime)){Expand-Archive -LiteralPath $archive -DestinationPath $runtime}
$version=& (Join-Path $runtime 'python.exe') -c 'import sys; print(".".join(map(str,sys.version_info[:3])))'
if($LASTEXITCODE -ne 0 -or $version -ne '3.14.7'){throw 'LOCAL_RUNTIME_VERSION_MISMATCH'}
$venv=Join-Path $directory 'venv'
if(-not(Test-Path -LiteralPath (Join-Path $venv 'Scripts\python.exe'))){
    & (Join-Path $runtime 'python.exe') -m venv $venv
    if($LASTEXITCODE -ne 0){throw 'WINDOWS_CONTROLLER_VENV_CREATION_FAILED'}
}
$python=Join-Path $venv 'Scripts\python.exe'
& $python -m pip install --disable-pip-version-check -r (Join-Path $PSScriptRoot '../requirements-controller-windows.lock.txt') --require-hashes --only-binary=:all:
if($LASTEXITCODE -ne 0){throw 'WINDOWS_CONTROLLER_DEPENDENCIES_FAILED'}
Write-Output 'WINDOWS_PROJECT_PYTHON_3_14_7_READY'
if($IncludeWsl){
    $source=(Get-Content -Raw (Join-Path $PSScriptRoot 'prepare_wsl_runtime.sh')).Replace("`r`n","`n")
    # PowerShell appends a Windows newline when piping text to native stdin.
    $source | & wsl.exe -e sh -c 'tr -d "\r" | sh -s'
    if($LASTEXITCODE -ne 0){throw 'WSL_RUNTIME_PREPARATION_FAILED'}
    $repo=Split-Path $PSScriptRoot -Parent
    $linuxRepo=(& wsl.exe -e wslpath -a $repo).Trim()
    & wsl.exe -e sh -c 'exec "$HOME/.local/share/arcia-toolchain/uv-0.13.0/uv" --no-config pip install --python "$HOME/.local/share/arcia-validation/bin/python" --require-hashes --only-binary=:all: -r "$1/requirements-controller-linux.lock.txt"' arcia-controller $linuxRepo
    if($LASTEXITCODE -ne 0){throw 'WSL_CONTROLLER_DEPENDENCIES_FAILED'}
}
