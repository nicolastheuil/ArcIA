# A rebuild reuses protected valid certificate material; DNS-01 issuance stays
# an explicit resumable operation because the external DNS admin publishes TXT.
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'ProtectedState.ps1')
. (Join-Path $PSScriptRoot 'PilotCredentials.ps1')
$root=Get-ArcIAStateRoot
try{
    $operation=(Read-ProtectedBundle (Join-Path $root 'vmware-operation.dpapi'))|ConvertFrom-Json
    $instance=(Read-ProtectedBundle (Join-Path $root 'instance.dpapi'))|ConvertFrom-Json
    $decisions=(Read-ProtectedBundle (Join-Path $root 'installation-decisions.dpapi'))|ConvertFrom-Json
    if($operation.id -ne $instance.operation_id -or $operation.id -ne $decisions.operation_id){throw 'TLS_SCOPE_CONFLICT'}
    $pilot=Get-PilotCredentials $root $operation.id $instance.config.network.public_hostname
    if($decisions.tls_mode -ne 'public_acme'){
        $importPath=Join-Path $root 'bootstrap-tls.dpapi'
        if(-not(Test-Path -LiteralPath $importPath)){throw 'PUBLIC_TLS_MATERIAL_REQUIRED'}
        $material=(Read-ProtectedBundle $importPath)|ConvertFrom-Json
        $pilot.tls_certificate=$material.certificate;$pilot.tls_private_key=$material.private_key
    }
    $certificate=[Security.Cryptography.X509Certificates.X509Certificate2]::CreateFromPem($pilot.tls_certificate,$pilot.tls_private_key)
    $chain=[Security.Cryptography.X509Certificates.X509Chain]::new()
    try{
        $chain.ChainPolicy.RevocationMode=[Security.Cryptography.X509Certificates.X509RevocationMode]::NoCheck
        $san=[Security.Cryptography.X509Certificates.X509SubjectAlternativeNameExtension]::new()
        $san.CopyFrom($certificate.Extensions['2.5.29.17'])
        if(-not $certificate.HasPrivateKey -or -not $chain.Build($certificate) -or
            $instance.config.network.public_hostname -notin @($san.EnumerateDnsNames()) -or
            $certificate.NotAfter.ToUniversalTime() -lt [DateTime]::UtcNow.AddDays(7)){throw 'VALID_PUBLIC_TLS_REQUIRED'}
        if($decisions.tls_mode -ne 'public_acme'){
            foreach($item in @(@('pilot-credentials.dpapi',$pilot),@('installation-decisions.dpapi',$decisions))){
                $decisions.tls_mode='public_acme'
                $temporary=Join-Path $root ('tls-'+[guid]::NewGuid().ToString('N')+'.dpapi')
                Save-ProtectedBundle $temporary ($item[1]|ConvertTo-Json -Depth 24 -Compress)
                [IO.File]::Replace($temporary,(Join-Path $root $item[0]),[NullString]::Value)
            }
        }
    }finally{$chain.Dispose();$certificate.Dispose()}
    [IO.File]::WriteAllText((Join-Path $root 'bootstrap-tls-status.json'),' {"status":"verified","code":"PROTECTED_PUBLIC_TLS_READY"}')
    Write-Output 'PROTECTED_PUBLIC_TLS_READY'
}catch{Write-Output 'PUBLIC_TLS_REQUIRED_USE_DNS_RUNBOOK_OR_PROTECTED_IMPORT';exit 2}
finally{$pilot=$null;$material=$null;$instance=$null;$operation=$null;$decisions=$null}
