$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot '../scripts/SsoSecurity.ps1')
foreach($length in @(16,20,32,64)){
    $samples=@(1..30|ForEach-Object {New-ServicePassword $length})
    if(@($samples|Select-Object -Unique).Count -ne 30){throw 'PASSWORD_GENERATION_DUPLICATE'}
    foreach($value in $samples){
        if($value.Length -ne $length -or $value -cnotmatch '[A-Z]' -or $value -cnotmatch '[a-z]' -or
            $value -notmatch '[0-9]' -or $value -notmatch '[!@]' -or $value -match '(.)\1\1'){throw 'PASSWORD_POLICY_FAILED'}
    }
}
foreach($length in @(0,8,65)){
    $blocked=$false
    try{$null=New-ServicePassword $length}catch{$blocked=$true}
    if(-not $blocked){throw 'UNREVIEWED_PASSWORD_LENGTH_NOT_BLOCKED'}
}
Initialize-SsoCertificateValidator
# Windows synthetic certificate, no private key and no infrastructure access.
$certificate=Get-ChildItem Cert:\LocalMachine\Root|Select-Object -First 1
if(-not $certificate){throw 'SYNTHETIC_CERTIFICATE_FIXTURE_MISSING'}
$sha=[Security.Cryptography.SHA256]::Create()
try{$pin=([BitConverter]::ToString($sha.ComputeHash($certificate.RawData))).Replace('-','').ToLowerInvariant()}finally{$sha.Dispose()}
$validator=New-Object ArcIAPinnedCertificateValidator($pin)
$validator.Validate($certificate)
$wrong=New-Object ArcIAPinnedCertificateValidator(('0'*64))
$blocked=$false
try{$wrong.Validate($certificate)}catch{$blocked=$true}
if(-not $blocked){throw 'CHANGED_TLS_CERTIFICATE_NOT_BLOCKED'}
$blocked=$false
try{$validator.Validate($null)}catch{$blocked=$true}
if(-not $blocked){throw 'MISSING_TLS_CERTIFICATE_NOT_BLOCKED'}
$samples=$null;$value=$null
Write-Output 'SSO_PASSWORD_AND_TLS_SECURITY_TESTS_PASSED; NO_REMOTE_ACCESS'
