$ProgressPreference = 'SilentlyContinue'
$release = Invoke-WebRequest -Uri 'https://api.github.com/repos/k3s-io/k3s/releases/tags/v1.37.1%2Bk3s1' -UseBasicParsing
$json = $release.Content | ConvertFrom-Json
Write-Host "Commitish: $($json.target_commitish)"

# Get the actual commit SHA from the tag
$tag = Invoke-WebRequest -Uri 'https://api.github.com/repos/k3s-io/k3s/git/refs/tags/v1.37.1%2Bk3s1' -UseBasicParsing
$tagJson = $tag.Content | ConvertFrom-Json
Write-Host "Tag SHA: $($tagJson.object.sha)"

# If it's a tag object, get the commit it points to
if ($tagJson.object.type -eq 'tag') {
    $tagObj = Invoke-WebRequest -Uri $tagJson.object.url -UseBasicParsing
    $tagObjJson = $tagObj.Content | ConvertFrom-Json
    Write-Host "Commit SHA: $($tagObjJson.object.sha)"
}