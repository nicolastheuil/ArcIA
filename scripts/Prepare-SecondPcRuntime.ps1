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
Write-Output 'WINDOWS_PROJECT_PYTHON_3_14_7_READY'
if($IncludeWsl){
    $source=(Get-Content -Raw (Join-Path $PSScriptRoot 'prepare_wsl_runtime.sh')).Replace("`r`n","`n")
    # PowerShell appends a Windows newline when piping text to native stdin.
    $source | & wsl.exe -e sh -c 'tr -d "\r" | sh -s'
    if($LASTEXITCODE -ne 0){throw 'WSL_RUNTIME_PREPARATION_FAILED'}
}
