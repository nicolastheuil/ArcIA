[CmdletBinding()]
param(
    [Parameter(Position=0, Mandatory=$false)]
    [string]$Command = "get nodes",
    
    [Parameter(Mandatory=$false, ValueFromPipeline=$true)]
    [string]$InputObject,

    [Parameter(Mandatory=$false)]
    [switch]$RawShell,

    [Parameter(Mandatory=$false)]
    [string]$Node = $(if ($env:ARCIA_K3S_NODE) { $env:ARCIA_K3S_NODE } else { "127.0.0.1" }),

    [Parameter(Mandatory=$false)]
    [string]$User = $(if ($env:ARCIA_K3S_USER) { $env:ARCIA_K3S_USER } elseif ($env:USER) { $env:USER } elseif ($env:USERNAME) { $env:USERNAME.ToLower() } else { "debian" })
)

$ErrorActionPreference = 'Stop'

# Locate private SSH identity and known_hosts
$harnessDirs = @(
    $(if ($env:ARCIA_STATE_ROOT) { $env:ARCIA_STATE_ROOT }),
    (Join-Path $env:LOCALAPPDATA 'ArcIA-Harness'),
    (Join-Path $env:USERPROFILE '.ssh')
) | Where-Object { $_ }

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

if ($Node -eq "127.0.0.1" -and (Test-Path $known)) {
    $match = (Get-Content $known | Select-String -Pattern '^\s*([0-9\.]+)' | Select-Object -First 1)
    if ($match -and $match.Matches.Count -gt 0) {
        $Node = $match.Matches[0].Groups[1].Value
    }
}

$remoteCmd = if ($RawShell) {
    "sudo /bin/sh -c '$Command'"
} else {
    "sudo /usr/local/bin/k3s kubectl $Command"
}

$argsList = @(
    '-F', 'NUL',
    '-o', 'BatchMode=yes',
    '-o', 'StrictHostKeyChecking=yes',
    '-o', 'IdentitiesOnly=yes',
    '-o', 'HostKeyAlgorithms=ssh-ed25519',
    ("-oUserKnownHostsFile=$known"),
    '-i', $identity,
    "$User@$Node",
    $remoteCmd
)

$pinfo = New-Object Diagnostics.ProcessStartInfo
$pinfo.FileName = 'ssh'

if ($pinfo.PSObject.Properties['ArgumentList'] -and $pinfo.ArgumentList -ne $null) {
    foreach ($a in $argsList) {
        $pinfo.ArgumentList.Add($a)
    }
} else {
    $escaped = $argsList | ForEach-Object {
        if ($_ -match '[\s"]') {
            '"' + ($_ -replace '"', '\"') + '"'
        } else {
            $_
        }
    }
    $pinfo.Arguments = $escaped -join ' '
}

if ($InputObject) {
    $pinfo.RedirectStandardInput = $true
} else {
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
    Write-Error "SSH Error (exit code $($proc.ExitCode)): $stderr"
} elseif ($stderr) {
    Write-Verbose $stderr
}
