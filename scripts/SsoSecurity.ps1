function New-ServicePassword([int]$Length){
    if($Length -lt 16 -or $Length -gt 64){throw 'PASSWORD_POLICY_REQUIRES_REVIEW'}
    $alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!@'
    $bytes=New-Object byte[] $Length;$rng=[Security.Cryptography.RandomNumberGenerator]::Create()
    try{
        do{
            $rng.GetBytes($bytes)
            $candidate=-join @($bytes|ForEach-Object {$alphabet[($_ -band 63)]})
        }while($candidate -cnotmatch '[A-Z]' -or $candidate -cnotmatch '[a-z]' -or $candidate -notmatch '[0-9]' -or $candidate -notmatch '[!@]' -or $candidate -match '(.)\1\1')
        return $candidate
    }finally{$rng.Dispose();[Array]::Clear($bytes,0,$bytes.Length)}
}
function Initialize-SsoCertificateValidator {
    Add-Type -AssemblyName System.IdentityModel
    Add-Type -AssemblyName System.ServiceModel
    Add-Type -TypeDefinition @'
using System;
using System.IdentityModel.Selectors;
using System.IdentityModel.Tokens;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
public sealed class ArcIAPinnedCertificateValidator : X509CertificateValidator {
    private readonly string expected;
    public ArcIAPinnedCertificateValidator(string pin) {
        if (pin == null || !System.Text.RegularExpressions.Regex.IsMatch(pin, "^[a-f0-9]{64}$"))
            throw new ArgumentException("TLS_PIN_REQUIRED");
        expected = pin;
    }
    public override void Validate(X509Certificate2 certificate) {
        if (certificate == null) throw new SecurityTokenValidationException("TLS_PIN_REQUIRED");
        using (var sha = SHA256.Create()) {
            var actual = BitConverter.ToString(sha.ComputeHash(certificate.RawData)).Replace("-", "").ToLowerInvariant();
            if (!String.Equals(expected, actual, StringComparison.Ordinal))
                throw new SecurityTokenValidationException("TLS_FINGERPRINT_CHANGED");
        }
    }
}
'@ -ReferencedAssemblies 'System.IdentityModel.dll'
}
