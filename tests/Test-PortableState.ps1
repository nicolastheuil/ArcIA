$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot '../scripts/ProtectedState.ps1')
. (Join-Path $PSScriptRoot '../scripts/PortableState.ps1')
$sandbox=Join-Path $env:TEMP ('arcia-portable-test-'+[guid]::NewGuid().ToString('N'))
try{
    Initialize-PrivateDirectory $sandbox
    $source=Join-Path $sandbox 'source';Initialize-PrivateDirectory $source
    $external=Join-Path $sandbox 'synthetic.asc';[IO.File]::WriteAllText($external,'SYNTHETIC_REFERENCE_NOT_A_KEY')
    $bundle=@{synthetic=$true;token='synthetic-token';path=(Join-Path $source 'identity');external=$external}
    Save-ProtectedBundle (Join-Path $source 'instance.dpapi') ($bundle|ConvertTo-Json -Compress)
    [IO.File]::WriteAllText((Join-Path $source 'identity'),'SYNTHETIC_NOT_A_PRIVATE_KEY')
    $password=[Convert]::ToBase64String([Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
    $archive=Join-Path $sandbox 'test.arciap'
    $result=Export-PortableState $source (Split-Path $PSScriptRoot -Parent) $archive $password
    if($result.file_count -ne 3 -or $result.rebound_dpapi_count -ne 1){
        Write-Output ('SYNTHETIC_EXPORT_FILES='+$result.file_count+'; DPAPI='+$result.rebound_dpapi_count+'; REFERENCES='+$result.referenced_file_count)
        throw 'EXPORT_COUNT_FAILED'
    }
    $wrongRejected=$false;try{$null=Read-PortableArchive $archive 'incorrect-password-1234'}catch{$wrongRejected=$true}
    if(-not $wrongRejected){throw 'WRONG_PASSWORD_ACCEPTED'}
    $destination=Join-Path $sandbox 'restored'
    $null=Import-PortableState $archive $destination (Split-Path $PSScriptRoot -Parent) $password
    $restored=(Read-ProtectedBundle (Join-Path $destination 'instance.dpapi'))|ConvertFrom-Json
    if($restored.token -ne 'synthetic-token' -or $restored.path -ne (Join-Path $destination 'identity') -or
        -not (Test-Path -LiteralPath $restored.external) -or [IO.File]::ReadAllText($restored.external) -ne 'SYNTHETIC_REFERENCE_NOT_A_KEY'){throw 'RESTORE_OR_PATH_REBIND_FAILED'}
    $overwriteRejected=$false;try{$null=Import-PortableState $archive $destination (Split-Path $PSScriptRoot -Parent) $password}catch{$overwriteRejected=$true}
    if(-not $overwriteRejected){throw 'EXISTING_STATE_OVERWRITTEN'}
    $tampered=[IO.File]::ReadAllBytes($archive);$tampered[-1]=$tampered[-1] -bxor 1
    $bad=Join-Path $sandbox 'tampered.arciap';[IO.File]::WriteAllBytes($bad,$tampered)
    $tamperRejected=$false;try{$null=Read-PortableArchive $bad $password}catch{$tamperRejected=$true}
    if(-not $tamperRejected){throw 'TAMPER_ACCEPTED'}
    Write-Output 'PORTABLE_ENCRYPTION_WRONG_PASSWORD_TAMPER_DPAPI_REBIND_REFERENCES_AND_NO_OVERWRITE_OK'
}finally{
    $password=$null;$restored=$null;$bundle=$null
    # Exact generated test directory, verified before recursive cleanup.
    $resolved=[IO.Path]::GetFullPath($sandbox);$expected=[IO.Path]::GetFullPath($env:TEMP).TrimEnd('\')+'\arcia-portable-test-'
    if($resolved.StartsWith($expected,[StringComparison]::OrdinalIgnoreCase) -and (Test-Path -LiteralPath $resolved)){Remove-Item -LiteralPath $resolved -Recurse -Force}
}
