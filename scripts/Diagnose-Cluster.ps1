$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'ProtectedState.ps1')
$root=Join-Path $env:LOCALAPPDATA 'ArcIA-Harness'
try{
    $data=(Read-ProtectedBundle (Join-Path $root 'cluster-install_k3s.dpapi'))|ConvertFrom-Json
    $source=Get-Content (Join-Path $PSScriptRoot '../infra/ansible/roles/k3s/tasks/main.yml') -Raw
    $source+="`n"+(Get-Content (Join-Path $PSScriptRoot '../infra/ansible/preflight.yml') -Raw)
    $source+="`n"+(Get-Content (Join-Path $PSScriptRoot '../infra/ansible/site.yml') -Raw)
    $allowed=@([regex]::Matches($source,'(?m)^\s*- name: (.+)$')|ForEach-Object {$_.Groups[1].Value})
    $tasks=@([regex]::Matches($data.ansible.stdout,'TASK \[(?:k3s : )?([^\]]+)\]')|ForEach-Object {$_.Groups[1].Value})
    $last=if($tasks.Count -and $tasks[-1] -in $allowed){$tasks[-1]}else{'UNCLASSIFIED_TASK'}
    $codes=@()
    foreach($pair in @(@('unsupported version','REMOTE_PYTHON_UNSUPPORTED'),@('Permission denied','SSH_PERMISSION_DENIED'),
        @('Connection refused','CONNECTION_REFUSED'),@('timed out','OPERATION_TIMEOUT'),@('checksum','CHECKSUM_RELATED'),
        @('sudo','SUDO_RELATED'),@('Failed to download','ARTIFACT_DOWNLOAD_FAILED'),@('assertion','ASSERTION_FAILED'))){
        if(($data.ansible.stdout+$data.ansible.stderr) -match [regex]::Escape($pair[0])){$codes+=$pair[1]}
    }
    @{status='diagnosed';last_task=$last;known_error_codes=$codes;host_count=@($data.ansible.stats).Count;
      failed_host_count=@($data.ansible.stats|Where-Object {$_.failures -gt 0}).Count;
      unreachable_host_count=@($data.ansible.stats|Where-Object {$_.unreachable -gt 0}).Count}|ConvertTo-Json
}catch{Write-Output 'CLUSTER_DIAGNOSTIC_UNAVAILABLE';exit 2}
finally{$data=$null;$source=$null}
