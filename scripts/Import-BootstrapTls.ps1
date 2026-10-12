# Trusted local file references only; certificate/key bytes never leave this program.
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$CertificatePath,[Parameter(Mandatory=$true)][string]$PrivateKeyPath)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'ProtectedState.ps1')
$root=Get-ArcIAStateRoot;Initialize-PrivateDirectory $root
try{
    $material=@{certificate=[IO.File]::ReadAllText($CertificatePath);private_key=[IO.File]::ReadAllText($PrivateKeyPath)}
    $certificate=[Security.Cryptography.X509Certificates.X509Certificate2]::CreateFromPem($material.certificate,$material.private_key)
    try{if(-not $certificate.HasPrivateKey){throw 'TLS_KEY_REQUIRED'}}finally{$certificate.Dispose()}
    $temporary=Join-Path $root ('tls-import-'+[guid]::NewGuid().ToString('N')+'.dpapi')
    Save-ProtectedBundle $temporary ($material|ConvertTo-Json -Compress)
    $destination=Join-Path $root 'bootstrap-tls.dpapi'
    if(Test-Path -LiteralPath $destination){[IO.File]::Replace($temporary,$destination,[NullString]::Value)}else{Move-Item -LiteralPath $temporary -Destination $destination}
    Write-Output 'BOOTSTRAP_TLS_IMPORTED_ENCRYPTED'
}finally{$material=$null}
