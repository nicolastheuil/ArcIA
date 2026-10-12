[CmdletBinding()]
param([ValidateSet('request','collect','suspend','checkpoint')][string]$Action='request',[string]$Email,
    [string]$HermesHostname,[string]$TeamsHostname)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'ProtectedState.ps1')
$root=Join-Path $env:LOCALAPPDATA 'ArcIA-Harness'
Initialize-PrivateDirectory $root
$operation=(Read-ProtectedBundle (Join-Path $root 'vmware-operation.dpapi'))|ConvertFrom-Json
$payload=@{action=$Action;operation_id=$operation.id}
if($Action -eq 'request'){
    if(-not $Email -or -not $HermesHostname -or -not $TeamsHostname){throw 'ACME_CONTACT_AND_DOMAINS_REQUIRED'}
    $payload.email=$Email;$payload.domains=@($HermesHostname,$TeamsHostname)
    $payload.hook_source=[IO.File]::ReadAllText((Join-Path $PSScriptRoot 'certbot_dns_hook.py'))
}
$start=[Diagnostics.ProcessStartInfo]::new();$start.FileName='wsl.exe'
foreach($arg in @('-e','/bin/sh','-c','exec "$HOME/.local/share/arcia-validation/bin/python" -c "$1"',
    'arcia-acme',[IO.File]::ReadAllText((Join-Path $PSScriptRoot 'certbot_controller.py')))){$start.ArgumentList.Add($arg)}
$start.UseShellExecute=$false;$start.CreateNoWindow=$true
$start.RedirectStandardInput=$true;$start.RedirectStandardOutput=$true;$start.RedirectStandardError=$true
$start.StandardInputEncoding=[Text.UTF8Encoding]::new($false)
$process=[Diagnostics.Process]::new();$process.StartInfo=$start
$lockStream=$null
function Replace-AcmeBundle([string]$Name,$Value){
    $temp=Join-Path $root ('acme-'+[guid]::NewGuid().ToString('N')+'.dpapi')
    Save-ProtectedBundle $temp ($Value|ConvertTo-Json -Depth 30 -Compress)
    $dest=Join-Path $root $Name
    if(Test-Path -LiteralPath $dest){[IO.File]::Replace($temp,$dest,[NullString]::Value)}else{Move-Item -LiteralPath $temp -Destination $dest}
}
try{
    $null=$process.Start();$errors=$process.StandardError.ReadToEndAsync()
    $process.StandardInput.Write(($payload|ConvertTo-Json -Depth 10 -Compress));$process.StandardInput.Close()
    while($null -ne ($line=$process.StandardOutput.ReadLine())){
        $result=$line|ConvertFrom-Json
        if($Action -in @('request','suspend')){
            # Only fixed statuses and public DNS challenges are emitted.
            if($result.code -eq 'ACME_DNS_TXT_REQUIRED'){
                if($result.record.name -notin @(('_acme-challenge.'+$HermesHostname),('_acme-challenge.'+$TeamsHostname)) -or
                    $result.record.value -notmatch '^[A-Za-z0-9_-]{43}$'){throw 'ACME_PUBLIC_OUTPUT_SCOPE'}
                @{status='waiting_dns';code='ACME_DNS_TXT_REQUIRED';record=@{name=$result.record.name;type='TXT';value=$result.record.value}}|ConvertTo-Json -Compress
            }elseif($result.code -in @('ACME_CERTIFICATE_ISSUED','ACME_CERTIFICATE_FAILED','PROTECTED_ACME_OPERATION_FAILED','ACME_DNS_VALIDATION_DEFERRED')){
                @{status=$result.status;code=$result.code}|ConvertTo-Json -Compress
                [IO.File]::WriteAllText((Join-Path $root 'certificate-request-status.json'),($result|ConvertTo-Json -Compress))
            }else{throw 'ACME_UNEXPECTED_OUTPUT'}
        }elseif($Action -eq 'checkpoint'){
            if(-not $result.private -or $result.private.operation_id -ne $operation.id){throw 'ACME_CHECKPOINT_SCOPE'}
            Replace-AcmeBundle 'acme-state.dpapi' $result.private
            '{"status":"saved","code":"ACME_ACCOUNT_AND_CHALLENGES_CHECKPOINT_ENCRYPTED"}'
        }else{
            if(-not $result.private -or $result.private.operation_id -ne $operation.id){throw 'ACME_CERTIFICATE_COLLECTION_FAILED'}
            $cert=$result.private
            $lockStream=[IO.File]::Open((Join-Path $root 'cluster-operation.lock'),[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::Write,[IO.FileShare]::None)
            $pilot=(Read-ProtectedBundle (Join-Path $root 'pilot-credentials.dpapi'))|ConvertFrom-Json
            $instance=(Read-ProtectedBundle (Join-Path $root 'instance.dpapi'))|ConvertFrom-Json
            $decisions=(Read-ProtectedBundle (Join-Path $root 'installation-decisions.dpapi'))|ConvertFrom-Json
            if($pilot.operation_id -ne $operation.id -or $instance.operation_id -ne $operation.id -or
                $decisions.operation_id -ne $operation.id -or $cert.domains.Count -ne 2){throw 'ACME_INSTALL_SCOPE_CONFLICT'}
            $certificate=[Security.Cryptography.X509Certificates.X509Certificate2]::CreateFromPem($cert.certificate,$cert.private_key)
            try{
                $san=[Security.Cryptography.X509Certificates.X509SubjectAlternativeNameExtension]::new()
                $san.CopyFrom($certificate.Extensions['2.5.29.17'])
                $names=@($san.EnumerateDnsNames())
                if(-not $certificate.HasPrivateKey -or $certificate.NotAfter.ToUniversalTime() -lt [DateTime]::UtcNow.AddDays(1) -or
                    $certificate.NotBefore.ToUniversalTime() -gt [DateTime]::UtcNow -or
                    @($cert.domains|Where-Object{$_ -notin $names}).Count){throw 'ACME_CERTIFICATE_VALIDATION_FAILED'}
            }finally{$certificate.Dispose()}
            # Keep encrypted recovery material before the two protected replacements.
            Replace-AcmeBundle ('tls-before-'+[guid]::NewGuid().ToString('N')+'.dpapi') @{pilot=$pilot;instance=$instance;decisions=$decisions}
            $pilot.hostname=$cert.domains[0];$pilot.tls_certificate=$cert.certificate;$pilot.tls_private_key=$cert.private_key
            $instance.config.network.public_hostname=$cert.domains[0]
            $decisions.tls_mode='public_acme'
            $migration=@{operation_id=$operation.id;pilot=$pilot;instance=$instance;decisions=$decisions;domains=$cert.domains;tls_issuer='lets_encrypt'}
            Replace-AcmeBundle 'tls-migration.dpapi' $migration
            Replace-AcmeBundle 'pilot-credentials.dpapi' $pilot
            Replace-AcmeBundle 'instance.dpapi' $instance
            Replace-AcmeBundle 'installation-decisions.dpapi' $decisions
            Replace-AcmeBundle 'public-endpoints.dpapi' @{operation_id=$operation.id;hermes=$cert.domains[0];teams=$cert.domains[1];tls_issuer='lets_encrypt';public_access_enabled=$false}
            '{"status":"collected","code":"PUBLIC_TLS_PROTECTED_CONFIGURATION_UPDATED","deployed":false}'
        }
    }
    $process.WaitForExit();$null=$errors.GetAwaiter().GetResult()
    if($process.ExitCode -ne 0){exit 2}
}finally{
    if(-not $process.HasExited){$process.Kill($true)}
    $process.Dispose();if($lockStream){$lockStream.Dispose()}
    $payload=$null;$result=$null;$cert=$null;$pilot=$null;$instance=$null;$migration=$null
}
