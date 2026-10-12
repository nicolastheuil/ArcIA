# Local generation and storage only. Never write credential values to stdout.
function Get-PilotCredentials {
    param([string]$Root,[string]$Operation,[string]$Hostname)
    $path=Join-Path $Root 'pilot-credentials.dpapi'
    if(Test-Path -LiteralPath $path){
        $pilot=(Read-ProtectedBundle $path)|ConvertFrom-Json
        if($pilot.operation_id -ne $Operation -or $pilot.hostname -ne $Hostname){throw 'PILOT_CREDENTIAL_SCOPE_CONFLICT'}
        return $pilot
    }
    function New-PilotRandom([int]$Length){
        $bytes=[byte[]]::new($Length)
        [Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
        return [Convert]::ToBase64String($bytes)
    }
    $rsa=[Security.Cryptography.RSA]::Create(3072)
    try{
        $request=[Security.Cryptography.X509Certificates.CertificateRequest]::new(
            'CN='+$Hostname,$rsa,[Security.Cryptography.HashAlgorithmName]::SHA256,[Security.Cryptography.RSASignaturePadding]::Pkcs1)
        $san=[Security.Cryptography.X509Certificates.SubjectAlternativeNameBuilder]::new()
        $san.AddDnsName($Hostname);$request.CertificateExtensions.Add($san.Build())
        $request.CertificateExtensions.Add([Security.Cryptography.X509Certificates.X509BasicConstraintsExtension]::new($false,$false,0,$true))
        $request.CertificateExtensions.Add([Security.Cryptography.X509Certificates.X509KeyUsageExtension]::new(
            [Security.Cryptography.X509Certificates.X509KeyUsageFlags]::DigitalSignature -bor [Security.Cryptography.X509Certificates.X509KeyUsageFlags]::KeyEncipherment,$true))
        $certificate=$request.CreateSelfSigned([DateTimeOffset]::UtcNow.AddMinutes(-5),[DateTimeOffset]::UtcNow.AddDays(90))
        $pilot=@{schema_version=1;operation_id=$Operation;hostname=$Hostname;username='qualification';
            password=(New-PilotRandom 24);password_salt=(New-PilotRandom 16);session_secret=(New-PilotRandom 32);
            tls_certificate=$certificate.ExportCertificatePem();tls_private_key=$rsa.ExportPkcs8PrivateKeyPem();
            created_at=[DateTime]::UtcNow.ToString('o')}
        Save-ProtectedBundle $path ($pilot|ConvertTo-Json -Compress)
        return [pscustomobject]$pilot
    }finally{$rsa.Dispose();if($certificate){$certificate.Dispose()}}
}
