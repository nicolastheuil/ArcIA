# Private-key material is held only in DPAPI and protected worker stdin.
[CmdletBinding()]
param([switch]$TrustCurrentUser)
$ErrorActionPreference='Stop'
if($PSVersionTable.PSEdition -ne 'Core'){throw 'POWERSHELL_CORE_REQUIRED'}
. (Join-Path $PSScriptRoot 'ProtectedState.ps1')
$root=Get-ArcIAStateRoot -Identity -SelectLocally
Initialize-PrivateDirectory $root
$instance=(Read-ProtectedBundle (Join-Path $root 'instance.dpapi'))|ConvertFrom-Json
$operation=(Read-ProtectedBundle (Join-Path $root 'vmware-operation.dpapi'))|ConvertFrom-Json
if($operation.id -ne $instance.operation_id){throw 'ROUTING_IP_TLS_SCOPE_CONFLICT'}
$vip=[Net.IPAddress]::Parse($instance.endpoint_design.https_ip)
$bytes=$vip.GetAddressBytes()
if($bytes.Length -ne 4 -or -not($bytes[0] -eq 10 -or ($bytes[0] -eq 172 -and $bytes[1] -ge 16 -and $bytes[1] -le 31) -or ($bytes[0] -eq 192 -and $bytes[1] -eq 168))){throw 'PRIVATE_ROUTING_VIP_REQUIRED'}
$destination=Join-Path $root 'routing-ip-tls.dpapi'
$rsa=$null;$certificate=$null
try{
    if(Test-Path -LiteralPath $destination){
        $bundle=(Read-ProtectedBundle $destination)|ConvertFrom-Json
        if($bundle.operation_id -ne $operation.id -or $bundle.vip -ne $vip.ToString()){throw 'ROUTING_IP_TLS_REENROLLMENT_REQUIRED'}
        $certificate=[Security.Cryptography.X509Certificates.X509Certificate2]::CreateFromPem($bundle.certificate_pem)
        if($certificate.NotAfter.ToUniversalTime() -le [DateTime]::UtcNow.AddDays(14)){throw 'CONTROLLED_ROUTING_IP_TLS_ROTATION_REQUIRED'}
    }else{
        $rsa=[Security.Cryptography.RSA]::Create(3072)
        $request=[Security.Cryptography.X509Certificates.CertificateRequest]::new(
            'CN=ArcIA OmniRoute private VIP',$rsa,[Security.Cryptography.HashAlgorithmName]::SHA256,
            [Security.Cryptography.RSASignaturePadding]::Pkcs1)
        $request.CertificateExtensions.Add([Security.Cryptography.X509Certificates.X509BasicConstraintsExtension]::new($false,$false,0,$true))
        $usage=[Security.Cryptography.X509Certificates.X509KeyUsageFlags]::DigitalSignature -bor [Security.Cryptography.X509Certificates.X509KeyUsageFlags]::KeyEncipherment
        $request.CertificateExtensions.Add([Security.Cryptography.X509Certificates.X509KeyUsageExtension]::new($usage,$true))
        $oids=[Security.Cryptography.OidCollection]::new();$null=$oids.Add([Security.Cryptography.Oid]::new('1.3.6.1.5.5.7.3.1'))
        $request.CertificateExtensions.Add([Security.Cryptography.X509Certificates.X509EnhancedKeyUsageExtension]::new($oids,$false))
        $san=[Security.Cryptography.X509Certificates.SubjectAlternativeNameBuilder]::new();$san.AddIpAddress($vip)
        $request.CertificateExtensions.Add($san.Build())
        $certificate=$request.CreateSelfSigned([DateTimeOffset]::UtcNow.AddMinutes(-5),[DateTimeOffset]::UtcNow.AddDays(365))
        $bundle=@{operation_id=$operation.id;vip=$vip.ToString();certificate_pem=$certificate.ExportCertificatePem();private_key_pem=$rsa.ExportPkcs8PrivateKeyPem()}
        Save-ProtectedBundle $destination ($bundle|ConvertTo-Json -Compress)
    }
    # Public certificate only; this file contains no private key.
    $publicPath=Join-Path $root 'routing-ip-tls.cer'
    [IO.File]::WriteAllBytes($publicPath,$certificate.Export([Security.Cryptography.X509Certificates.X509ContentType]::Cert))
    if($TrustCurrentUser){
        # Explicit operator choice, never part of Fresh/Reconcile or deployment.
        $store=[Security.Cryptography.X509Certificates.X509Store]::new('Root','CurrentUser')
        try{$store.Open([Security.Cryptography.X509Certificates.OpenFlags]::ReadWrite);$store.Add([Security.Cryptography.X509Certificates.X509Certificate2]::new($publicPath))}finally{$store.Close()}
    }
    $previousRoot=$env:ARCIA_STATE_ROOT
    try{
        $env:ARCIA_STATE_ROOT=$root
        & (Join-Path $PSScriptRoot 'Invoke-ClusterFoundation.ps1') -Action install_omniroute
        if($LASTEXITCODE -ne 0){throw 'ROUTING_IP_TLS_DEPLOYMENT_FAILED'}
    }finally{$env:ARCIA_STATE_ROOT=$previousRoot}
    Write-Output 'ROUTING_PRIVATE_IP_CERTIFICATE_ENROLLED'
    if($TrustCurrentUser){Write-Output 'ROUTING_IP_CERTIFICATE_TRUSTED_FOR_CURRENT_USER'}else{Write-Output 'ROUTING_IP_CERTIFICATE_CLIENT_TRUST_PENDING'}
}finally{
    if($certificate){$certificate.Dispose()};if($rsa){$rsa.Dispose()}
    $bundle=$null;$instance=$null;$operation=$null
}
