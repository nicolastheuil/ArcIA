. 'C:\Users\NicolasTHEUIL\OneDrive - Arcitek\Projets\arcia\scripts\ProtectedState.ps1'
$root = Get-ArcIAStateRoot
$target = (Read-ProtectedBundle (Join-Path $root 'vmware-target.dpapi')) | ConvertFrom-Json
$trust = (Read-ProtectedBundle (Join-Path $root 'ssh-trust.dpapi')) | ConvertFrom-Json
$instance = (Read-ProtectedBundle (Join-Path $root 'instance.dpapi')) | ConvertFrom-Json
$operation = (Read-ProtectedBundle (Join-Path $root 'vmware-operation.dpapi')) | ConvertFrom-Json
$nodes = $trust.nodes
$script = [IO.File]::ReadAllBytes("C:\Users\NicolasTHEUIL\OneDrive - Arcitek\Projets\arcia\scripts\node_foundation.py")

function Check-Node($node) {
    $values = @{
        action = 'run_command'
        operation_id = $operation.id
        address = $node.address
        command = 'cat /etc/systemd/system/k3s.service; echo "---"; ls -la /usr/local/bin/; echo "---"; /usr/local/bin/k3s --version'
    }
    try {
        $result = guest $target $node $instance.base $script $values root=$true
        return $result.stdout
    } catch {
        return "ERROR: $($_.Exception.Message)"
    }
}

Check-Node $nodes[0]
Check-Node $nodes[1]
Check-Node $nodes[2]