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
    $browser=Join-Path $source 'identity-admin-browser';$null=[IO.Directory]::CreateDirectory($browser)
    [IO.File]::WriteAllText((Join-Path $browser 'Cookies'),'SYNTHETIC_BROWSER_SESSION_MUST_NOT_TRANSFER')
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
    # Windows short/long aliases may differ textually while naming the same file.
    if($restored.token -ne 'synthetic-token' -or
        [ArcIAPortablePaths]::Resolve($restored.path) -ne [ArcIAPortablePaths]::Resolve((Join-Path $destination 'identity')) -or
        -not (Test-Path -LiteralPath $restored.external) -or [IO.File]::ReadAllText($restored.external) -ne 'SYNTHETIC_REFERENCE_NOT_A_KEY'){throw 'RESTORE_OR_PATH_REBIND_FAILED'}
    $overwriteRejected=$false;try{$null=Import-PortableState $archive $destination (Split-Path $PSScriptRoot -Parent) $password}catch{$overwriteRejected=$true}
    if(-not $overwriteRejected){throw 'EXISTING_STATE_OVERWRITTEN'}
    if(Test-Path -LiteralPath (Join-Path $destination 'identity-admin-browser')){throw 'BROWSER_SESSION_EXPORTED'}
    $stale=Join-Path $destination 'stale.secret';[IO.File]::WriteAllText($stale,'SYNTHETIC_STALE_SECRET')
    $oldDigest=(Get-FileHash -LiteralPath (Join-Path $destination 'instance.dpapi') -Algorithm SHA256).Hash
    $wrongReplacementRejected=$false
    try{$null=Import-PortableState $archive $destination (Split-Path $PSScriptRoot -Parent) 'incorrect-password-1234' -ReplaceExisting}catch{$wrongReplacementRejected=$true}
    if(-not $wrongReplacementRejected -or -not(Test-Path -LiteralPath $stale) -or
       (Get-FileHash -LiteralPath (Join-Path $destination 'instance.dpapi') -Algorithm SHA256).Hash -ne $oldDigest){throw 'BAD_PASSWORD_MODIFIED_EXISTING_STATE'}
    # Fault injection after promotion must restore the old root, not lose it.
    $originalReader=(Get-Item Function:\Read-ProtectedBundle).ScriptBlock
    $publicationRejected=$false
    try{
        Set-Item Function:\Read-ProtectedBundle -Value {
            param($Path)
            if($Path -eq (Join-Path $destination 'instance.dpapi')){throw 'SYNTHETIC_FINAL_READBACK_FAILURE'}
            & $originalReader $Path
        }
        try{$null=Import-PortableState $archive $destination (Split-Path $PSScriptRoot -Parent) $password -ReplaceExisting}catch{$publicationRejected=$true}
    }finally{Set-Item Function:\Read-ProtectedBundle -Value $originalReader}
    if(-not $publicationRejected -or -not(Test-Path -LiteralPath $stale) -or
       (Get-FileHash -LiteralPath (Join-Path $destination 'instance.dpapi') -Algorithm SHA256).Hash -ne $oldDigest){throw 'PUBLICATION_FAILURE_ROLLBACK_FAILED'}
    $replacement=Import-PortableState $archive $destination (Split-Path $PSScriptRoot -Parent) $password -ReplaceExisting
    if(-not $replacement.replaced_existing_state -or $replacement.merge_performed -or
       (Test-Path -LiteralPath $stale) -or @(Get-ChildItem -LiteralPath $sandbox -Directory -Filter 'restored.previous-*').Count -or
       @(Get-ChildItem -LiteralPath $sandbox -Directory -Filter 'restored.restore-*').Count){throw 'REPLACEMENT_LEFT_STALE_SECRETS_OR_TEMPORARIES'}
    $rootRejected=$false;try{$null=Import-PortableState $archive $env:USERPROFILE (Split-Path $PSScriptRoot -Parent) $password -ReplaceExisting}catch{$rootRejected=$true}
    if(-not $rootRejected){throw 'BROAD_ROOT_ACCEPTED_FOR_CLEANUP'}
    $workspaceRejected=$false;try{$null=Import-PortableState $archive (Join-Path (Split-Path $PSScriptRoot -Parent) 'must-not-create') (Split-Path $PSScriptRoot -Parent) $password -ReplaceExisting}catch{$workspaceRejected=$true}
    if(-not $workspaceRejected){throw 'WORKSPACE_ACCEPTED_FOR_CLEANUP'}
    $archiveInside=Join-Path $destination 'nested.arciap';[IO.File]::Copy($archive,$archiveInside)
    $insideRejected=$false;try{$null=Import-PortableState $archiveInside $destination (Split-Path $PSScriptRoot -Parent) $password -ReplaceExisting}catch{$insideRejected=$true}
    if(-not $insideRejected -or -not(Test-Path -LiteralPath $archiveInside)){throw 'ARCHIVE_INSIDE_TARGET_ACCEPTED'}
    $linked=Join-Path $sandbox 'linked';$null=New-Item -ItemType Junction -Path $linked -Target $destination
    $linkRejected=$false;try{$null=Import-PortableState $archive $linked (Split-Path $PSScriptRoot -Parent) $password -ReplaceExisting}catch{$linkRejected=$true}
    if(-not $linkRejected -or -not(Test-Path -LiteralPath (Join-Path $destination 'instance.dpapi'))){throw 'LINKED_RESTORE_ROOT_ACCEPTED'}
    # An added secret during export must invalidate the snapshot too.
    $originalManifestReader=(Get-Item Function:\Get-PortableManifest).ScriptBlock
    $archiveDigest=(Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash
    $added=Join-Path $source 'added-during-export.dpapi';$additionRejected=$false
    try{
        Set-Item Function:\Get-PortableManifest -Value {
            param([byte[]]$Bytes)
            $result=& $originalManifestReader $Bytes
            Save-ProtectedBundle $added ('{"synthetic":true}')
            return $result
        }
        try{$null=Export-PortableState $source (Split-Path $PSScriptRoot -Parent) $archive $password}catch{$additionRejected=$true}
    }finally{Set-Item Function:\Get-PortableManifest -Value $originalManifestReader}
    if(-not $additionRejected -or (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne $archiveDigest){throw 'SOURCE_ADDITION_DURING_EXPORT_NOT_REJECTED'}
    # An ArcIA secret placed in a browser profile may not be silently dropped.
    Save-ProtectedBundle (Join-Path $browser 'misplaced.dpapi') ('{"synthetic":true}')
    $misplacedRejected=$false;try{$null=Export-PortableState $source (Split-Path $PSScriptRoot -Parent) $archive $password}catch{$misplacedRejected=$true}
    if(-not $misplacedRejected){throw 'MISPLACED_SECRET_SILENTLY_OMITTED'}
    $tampered=[IO.File]::ReadAllBytes($archive);$tampered[-1]=$tampered[-1] -bxor 1
    $bad=Join-Path $sandbox 'tampered.arciap';[IO.File]::WriteAllBytes($bad,$tampered)
    $tamperRejected=$false;try{$null=Read-PortableArchive $bad $password}catch{$tamperRejected=$true}
    if(-not $tamperRejected){throw 'TAMPER_ACCEPTED'}
    [IO.File]::WriteAllText($stale,'SYNTHETIC_STALE_SECRET')
    $tamperedReplacementRejected=$false;try{$null=Import-PortableState $bad $destination (Split-Path $PSScriptRoot -Parent) $password -ReplaceExisting}catch{$tamperedReplacementRejected=$true}
    if(-not $tamperedReplacementRejected -or -not(Test-Path -LiteralPath $stale)){throw 'TAMPERED_ARCHIVE_MODIFIED_EXISTING_STATE'}
    Write-Output 'PORTABLE_ENCRYPTION_WRONG_PASSWORD_TAMPER_DPAPI_REBIND_REFERENCES_AND_NO_OVERWRITE_OK'
    Write-Output 'PORTABLE_REPLACE_NO_MERGE_ROLLBACK_SCOPE_AND_BROWSER_EXCLUSION_OK'
}finally{
    $password=$null;$restored=$null;$bundle=$null
    # Exact generated test directory, verified before recursive cleanup.
    $resolved=[IO.Path]::GetFullPath($sandbox);$expected=[IO.Path]::GetFullPath($env:TEMP).TrimEnd('\')+'\arcia-portable-test-'
    if($resolved.StartsWith($expected,[StringComparison]::OrdinalIgnoreCase) -and (Test-Path -LiteralPath $resolved)){Remove-Item -LiteralPath $resolved -Recurse -Force}
}
