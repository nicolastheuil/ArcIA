# Explicit hostname migration; credentials and K3s/API identity are preserved.
[CmdletBinding()]
param([Parameter(Mandatory)][string]$HermesHostname,[Parameter(Mandatory)][string]$TeamsHostname)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'ProtectedState.ps1')
$root=Get-ArcIAStateRoot
foreach($hostValue in @($HermesHostname,$TeamsHostname)){
    if($hostValue -notmatch '^[a-z0-9][a-z0-9.-]{1,250}\.[a-z]{2,}$'){throw 'ENDPOINT_FQDN_REQUIRED'}
}
if($HermesHostname -eq $TeamsHostname){throw 'DISTINCT_ENDPOINTS_REQUIRED'}
$lockStream=[IO.File]::Open((Join-Path $root 'cluster-operation.lock'),[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::Write,[IO.FileShare]::None)
function Replace-EndpointBundle([string]$Name,$Value){
    $temp=Join-Path $root ('endpoints-'+[guid]::NewGuid().ToString('N')+'.dpapi')
    Save-ProtectedBundle $temp ($Value|ConvertTo-Json -Depth 30 -Compress)
    $dest=Join-Path $root $Name
    if(Test-Path -LiteralPath $dest){[IO.File]::Replace($temp,$dest,[NullString]::Value)}else{Move-Item -LiteralPath $temp -Destination $dest}
}
try{
    $operation=(Read-ProtectedBundle (Join-Path $root 'vmware-operation.dpapi'))|ConvertFrom-Json
    $pilot=(Read-ProtectedBundle (Join-Path $root 'pilot-credentials.dpapi'))|ConvertFrom-Json
    $instance=(Read-ProtectedBundle (Join-Path $root 'instance.dpapi'))|ConvertFrom-Json
    $decisions=(Read-ProtectedBundle (Join-Path $root 'installation-decisions.dpapi'))|ConvertFrom-Json
    if($pilot.operation_id -ne $operation.id -or $instance.operation_id -ne $operation.id -or
        $decisions.operation_id -ne $operation.id -or $decisions.public_access_enabled){throw 'ENDPOINT_OPERATION_SCOPE_CONFLICT'}
    if($pilot.hostname -ne $HermesHostname){
        if($decisions.tls_mode -ne 'self_signed_pilot'){throw 'PUBLIC_CERTIFICATE_HOSTNAME_MIGRATION_REQUIRED'}
        Replace-EndpointBundle ('endpoints-before-'+[guid]::NewGuid().ToString('N')+'.dpapi') @{pilot=$pilot;instance=$instance}
        $rsa=[Security.Cryptography.RSA]::Create()
        try{
            $rsa.ImportFromPem($pilot.tls_private_key)
            $request=[Security.Cryptography.X509Certificates.CertificateRequest]::new(
                'CN='+$HermesHostname,$rsa,[Security.Cryptography.HashAlgorithmName]::SHA256,[Security.Cryptography.RSASignaturePadding]::Pkcs1)
            $san=[Security.Cryptography.X509Certificates.SubjectAlternativeNameBuilder]::new()
            $san.AddDnsName($HermesHostname);$request.CertificateExtensions.Add($san.Build())
            $request.CertificateExtensions.Add([Security.Cryptography.X509Certificates.X509BasicConstraintsExtension]::new($false,$false,0,$true))
            $request.CertificateExtensions.Add([Security.Cryptography.X509Certificates.X509KeyUsageExtension]::new(
                [Security.Cryptography.X509Certificates.X509KeyUsageFlags]::DigitalSignature -bor [Security.Cryptography.X509Certificates.X509KeyUsageFlags]::KeyEncipherment,$true))
            $certificate=$request.CreateSelfSigned([DateTimeOffset]::UtcNow.AddMinutes(-5),[DateTimeOffset]::UtcNow.AddDays(90))
            $pilot.tls_certificate=$certificate.ExportCertificatePem()
        }finally{$rsa.Dispose();if($certificate){$certificate.Dispose()}}
        $pilot.hostname=$HermesHostname;$instance.config.network.public_hostname=$HermesHostname
        Replace-EndpointBundle 'endpoint-migration.dpapi' @{operation_id=$operation.id;pilot=$pilot;instance=$instance}
        Replace-EndpointBundle 'pilot-credentials.dpapi' $pilot
        Replace-EndpointBundle 'instance.dpapi' $instance
    }
    $issuer=if($decisions.tls_mode -eq 'public_acme'){'lets_encrypt'}else{'self_signed_pilot'}
    Replace-EndpointBundle 'public-endpoints.dpapi' @{operation_id=$operation.id;hermes=$HermesHostname;teams=$TeamsHostname;
        tls_issuer=$issuer;public_access_enabled=$false;teams_service_enabled=$false;dns_validation='deferred_by_user'}
    '{"status":"configured","code":"PILOT_ENDPOINTS_UPDATED_CREDENTIALS_PRESERVED","public_access_enabled":false}'
}finally{$lockStream.Dispose();$pilot=$null;$instance=$null;$operation=$null}
