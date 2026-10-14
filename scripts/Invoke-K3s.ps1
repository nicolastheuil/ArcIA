[CmdletBinding()]
param(
    [Parameter(Position=0, Mandatory=$false)]
    [string]$Command = "get nodes",
    
    [Parameter(Mandatory=$false)]
    [string]$InputObject,

    [Parameter(Mandatory=$false)]
    [string]$Node = "172.31.210.61"
)

$ErrorActionPreference = 'Stop'

# Locate private SSH identity and known_hosts
$harnessDirs = @(
    (Join-Path $env:LOCALAPPDATA 'ArcIA-Harness'),
    (Join-Path $env:USERPROFILE 'AppData\Local\Packages\OpenAI.Codex_2p2nqsd0c76g0\LocalCache\Local\ArcIA-Harness')
)

$privateRoot = $null
foreach ($dir in $harnessDirs) {
    if (Test-Path -LiteralPath (Join-Path $dir 'ssh\arcia-vm_ed25519')) {
        $privateRoot = $dir
        break
    }
}

if (-not $privateRoot) {
    throw "SSH identity file (arcia-vm_ed25519) not found in expected LocalAppData paths."
}

$identity = Join-Path $privateRoot 'ssh\arcia-vm_ed25519'
$known = Join-Path $privateRoot 'known_hosts.arcia'

$pinfo = New-Object Diagnostics.ProcessStartInfo
$pinfo.FileName = 'ssh'
$pinfo.ArgumentList.Add('-F')
$pinfo.ArgumentList.Add('NUL')
$pinfo.ArgumentList.Add('-o')
$pinfo.ArgumentList.Add('BatchMode=yes')
$pinfo.ArgumentList.Add('-o')
$pinfo.ArgumentList.Add('StrictHostKeyChecking=yes')
$pinfo.ArgumentList.Add('-o')
$pinfo.ArgumentList.Add('IdentitiesOnly=yes')
$pinfo.ArgumentList.Add('-o')
$pinfo.ArgumentList.Add('HostKeyAlgorithms=ssh-ed25519')
$pinfo.ArgumentList.Add(('-oUserKnownHostsFile=' + $known))
$pinfo.ArgumentList.Add('-i')
$pinfo.ArgumentList.Add($identity)
$pinfo.ArgumentList.Add("nicolas@$Node")

if ($InputObject) {
    $pinfo.ArgumentList.Add("sudo /usr/local/bin/k3s kubectl $Command")
    $pinfo.RedirectStandardInput = $true
} else {
    $pinfo.ArgumentList.Add("sudo /usr/local/bin/k3s kubectl $Command")
    $pinfo.RedirectStandardInput = $false
}

$pinfo.RedirectStandardOutput = $true
$pinfo.RedirectStandardError = $true
$pinfo.UseShellExecute = $false

$proc = [Diagnostics.Process]::Start($pinfo)
if ($InputObject) {
    $proc.StandardInput.Write($InputObject)
    $proc.StandardInput.Close()
}

$stdout = $proc.StandardOutput.ReadToEnd()
$stderr = $proc.StandardError.ReadToEnd()
$proc.WaitForExit()

if ($stdout) { Write-Output $stdout }
if ($stderr -and $proc.ExitCode -ne 0) { 
    Write-Error "SSH/Kubectl Error (exit code $($proc.ExitCode)): $stderr"
} elseif ($stderr) {
    Write-Verbose $stderr
}
