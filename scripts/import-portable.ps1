# Import portable state without GUI
. (Join-Path $PSScriptRoot 'ProtectedState.ps1')
. (Join-Path $PSScriptRoot 'PortableState.ps1')

$archive = 'C:\Users\NicolasTHEUIL\OneDrive - Arcitek\Projets\arcia\secrets\local\arcia-private.arciap'
$dest = 'C:\Users\NicolasTHEUIL\AppData\Local\ArcIA-Harness'
$ws = 'C:\Users\NicolasTHEUIL\OneDrive - Arcitek\Projets\arcia'

$pwd = Read-Host -AsSecureString 'Password (ArcIA Platform Encryption Key from 1Password)'
$pwdText = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($pwd))

try {
    $result = Import-PortableState $archive $dest $ws $pwdText
    Write-Host "Import successful: $($result.code)"
    Write-Host "Files restored: $($result.file_count)"
} catch {
    Write-Error "Import failed: $_"
    exit 1
} finally {
    [Array]::Clear([Text.Encoding]::UTF8.GetBytes($pwdText))
    $pwd.Dispose()
}