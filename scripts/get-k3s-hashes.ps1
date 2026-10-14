$ProgressPreference = 'SilentlyContinue'
$installer = Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/k3s-io/k3s/v1.37.1%2Bk3s1/install.sh' -UseBasicParsing
$installerBytes = [System.Text.Encoding]::UTF8.GetBytes($installer.Content)
$sha256 = [System.Security.Cryptography.SHA256]::Create().ComputeHash($installerBytes)
$installerHash = ($sha256 | ForEach-Object { $_.ToString('x2') }) -join ''
Write-Host "Installer SHA256: $installerHash"

$binaryUrl = 'https://github.com/k3s-io/k3s/releases/download/v1.37.1%2Bk3s1/k3s'
$binary = Invoke-WebRequest -Uri $binaryUrl -UseBasicParsing
$sha256 = [System.Security.Cryptography.SHA256]::Create().ComputeHash($binary.Content)
$binaryHash = ($sha256 | ForEach-Object { $_.ToString('x2') }) -join ''
Write-Host "Binary SHA256: $binaryHash"

$imagesUrl = 'https://github.com/k3s-io/k3s/releases/download/v1.37.1%2Bk3s1/k3s-airgap-images-amd64.tar.zst'
$images = Invoke-WebRequest -Uri $imagesUrl -UseBasicParsing
$sha256 = [System.Security.Cryptography.SHA256]::Create().ComputeHash($images.Content)
$imagesHash = ($sha256 | ForEach-Object { $_.ToString('x2') }) -join ''
Write-Host "Images SHA256: $imagesHash"