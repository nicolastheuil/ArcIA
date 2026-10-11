# Public artifacts only. No credentials or remote infrastructure access.
[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'ProtectedState.ps1')
try {
    $lock=Get-Content -LiteralPath (Join-Path $PSScriptRoot '../versions.lock.yaml') -Raw|ConvertFrom-Json
    if($lock.sso_admin_client.revision -notmatch '^[a-f0-9]{40}$'){throw 'CLIENT_REVISION_INVALID'}
    $cache=Join-Path $env:LOCALAPPDATA ('ArcIA-Harness/tools/sso-'+$lock.sso_admin_client.revision)
    Initialize-PrivateDirectory $cache
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    foreach($file in $lock.sso_admin_client.files){
        if($file.name -notmatch '^VMware\.[A-Za-z.]+\.dll$' -or $file.sha256 -notmatch '^[a-f0-9]{64}$' -or
           -not $file.url.StartsWith('https://raw.githubusercontent.com/vmware/PowerCLI-Example-Scripts/'+$lock.sso_admin_client.revision+'/')){throw 'CLIENT_SOURCE_INVALID'}
        $destination=Join-Path $cache $file.name
        if(Test-Path -LiteralPath $destination){
            if((Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLower() -ne $file.sha256){throw 'CLIENT_CACHE_INTEGRITY_FAILED'}
            continue
        }
        $download=Join-Path $cache ('download-'+[guid]::NewGuid().ToString('N'))
        $candidate=Join-Path $cache ('candidate-'+[guid]::NewGuid().ToString('N'))
        try{
            Invoke-WebRequest -Uri $file.url -OutFile $download -UseBasicParsing
            $expected=if($file.archive_member){$file.download_sha256}else{$file.sha256}
            if((Get-FileHash -LiteralPath $download -Algorithm SHA256).Hash.ToLower() -ne $expected){throw 'CLIENT_DOWNLOAD_INTEGRITY_FAILED'}
            if($file.archive_member){
                if($file.archive_member -ne ('lib/net45/'+$file.name)){throw 'CLIENT_ARCHIVE_MEMBER_INVALID'}
                $archive=[IO.Compression.ZipFile]::OpenRead($download)
                try{
                    $entries=@($archive.Entries|Where-Object {$_.FullName -ceq $file.archive_member})
                    if($entries.Count -ne 1){throw 'CLIENT_ARCHIVE_MEMBER_MISSING'}
                    [IO.Compression.ZipFileExtensions]::ExtractToFile($entries[0],$candidate,$false)
                }finally{$archive.Dispose()}
            }else{Copy-Item -LiteralPath $download -Destination $candidate}
            if((Get-FileHash -LiteralPath $candidate -Algorithm SHA256).Hash.ToLower() -ne $file.sha256){throw 'CLIENT_BINARY_INTEGRITY_FAILED'}
            Move-Item -LiteralPath $candidate -Destination $destination
        }finally{
            foreach($temporary in @($download,$candidate)){if(Test-Path -LiteralPath $temporary){Remove-Item -LiteralPath $temporary -Force}}
        }
    }
    @{status='verified';code='PINNED_SSO_CLIENT_CACHE_VERIFIED';file_count=@($lock.sso_admin_client.files).Count}|ConvertTo-Json
}catch{
    @{status='blocked';code='SSO_CLIENT_CACHE_INITIALIZATION_FAILED'}|ConvertTo-Json
    exit 2
}
