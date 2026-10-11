[CmdletBinding()]
param([switch]$Create)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'ProtectedState.ps1')
. (Join-Path $PSScriptRoot 'DnsRecordPlan.ps1')
$privateRoot=Join-Path $env:LOCALAPPDATA 'ArcIA-Harness'
$statusPath=Join-Path $privateRoot 'dns-status.json'
$session=$null;$stage='READ_PROTECTED_PLAN';$created=0;$lockStream=$null
try {
    $lockStream=[IO.File]::Open((Join-Path $privateRoot 'dns-operation.lock'),[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::Write,[IO.FileShare]::None)
    $access=(Read-ProtectedBundle (Join-Path $privateRoot 'dns-access.dpapi'))|ConvertFrom-Json
    $bundle=(Read-ProtectedBundle (Join-Path $privateRoot 'instance.dpapi'))|ConvertFrom-Json
    if($access.server -notmatch '^[A-Za-z0-9][A-Za-z0-9.-]{0,252}$' -or -not $access.authorized_server){throw 'DESIGNATED_DNS_REQUIRED'}
    $records=@(
        [pscustomobject]@{name=$bundle.config.network.api_endpoint;address=$bundle.endpoint_design.api_ip},
        [pscustomobject]@{name=$bundle.config.network.public_hostname;address=$bundle.endpoint_design.https_ip})
    foreach($record in $records){
        if($record.name -notmatch '^[A-Za-z0-9][A-Za-z0-9.-]{0,252}$' -or $record.name -notmatch '\.' -or
           [Net.IPAddress]::Parse($record.address).AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork){throw 'DNS_PLAN_INVALID'}
    }
    if($records[0].name -eq $records[1].name -and $records[0].address -ne $records[1].address){throw 'DNS_PLAN_CONFLICT'}
    $records=@($records|Sort-Object name -Unique)
    $secure=ConvertTo-SecureString $access.password -AsPlainText -Force
    $credential=New-Object Management.Automation.PSCredential($access.username,$secure)
    $stage='CONNECT_ENCRYPTED_DCOM'
    # These parameters select the DCOM parameter set; adding -Protocol conflicts with it.
    $option=New-CimSessionOption -PacketPrivacy -PacketIntegrity -Impersonation Impersonate
    $session=New-CimSession -ComputerName $access.server -Credential $credential -SessionOption $option -OperationTimeoutSec 20
    $stage='READ_DNS_ZONES_AND_RECORDS'
    $zones=@(Get-CimInstance -CimSession $session -Namespace root/MicrosoftDNS -ClassName MicrosoftDNS_Zone -OperationTimeoutSec 20)
    $plan=@()
    # Preflight both records before writing either. Do not create zones, delete or overwrite records.
    foreach($record in $records){
        $zone=Get-AuthoritativeZone $record.name $zones
        $existing=@(Get-CimInstance -CimSession $session -Namespace root/MicrosoftDNS -ClassName MicrosoftDNS_ResourceRecord -Filter ("OwnerName='"+$record.name+"'") -OperationTimeoutSec 20)
        if($existing.Count -and -not (Test-ExactDnsRecord $existing $record.address)){throw 'EXISTING_DNS_RECORD_CONFLICT'}
        $plan+=@{name=$record.name;address=$record.address;zone=$zone;exists=[bool]$existing.Count}
    }
    if($Create){
        $stage='SAVE_DNS_INTENT'
        $intent=@{operation_id=$bundle.operation_id;server=$access.server;records=$plan;status='dispatch_started'}
        $temporary=Join-Path $privateRoot ('dns-'+[guid]::NewGuid().ToString('N')+'.dpapi')
        Save-ProtectedBundle $temporary ($intent|ConvertTo-Json -Depth 8 -Compress)
        $destination=Join-Path $privateRoot 'dns-operation.dpapi'
        if(Test-Path -LiteralPath $destination){[IO.File]::Replace($temporary,$destination,[NullString]::Value)}else{Move-Item -LiteralPath $temporary -Destination $destination}
        $stage='CREATE_MISSING_DNS_RECORDS'
        foreach($item in $plan|Where-Object {-not $_.exists}){
            $arguments=@{DnsServerName=$access.server;ContainerName=$item.zone;OwnerName=$item.name;RecordClass=[uint32]1;TTL=[uint32]60;IPAddress=$item.address}
            $null=Invoke-CimMethod -CimSession $session -Namespace root/MicrosoftDNS -ClassName MicrosoftDNS_AType -MethodName CreateInstanceFromPropertyData -Arguments $arguments -OperationTimeoutSec 20
            $created++
        }
    }
    $stage='VERIFY_DNS_RECORDS'
    $verified=0
    foreach($item in $plan){
        $readback=@(Get-CimInstance -CimSession $session -Namespace root/MicrosoftDNS -ClassName MicrosoftDNS_ResourceRecord -Filter ("OwnerName='"+$item.name+"'") -OperationTimeoutSec 20)
        if(Test-ExactDnsRecord $readback $item.address){$verified++}
    }
    $safe=@{status=if($verified -eq $records.Count){'verified'}else{'prepared'};code=if($verified -eq $records.Count){'DNS_RECORDS_VERIFIED'}else{'DNS_RECORDS_NOT_YET_CREATED'};created_count=$created;verified_count=$verified;k3s_installed=$false}
    [IO.File]::WriteAllText($statusPath,($safe|ConvertTo-Json),[Text.Encoding]::UTF8)
}catch{
    $failure=$_
    $failureLine=$_.InvocationInfo.ScriptLineNumber
    $diagnostic=@{stage=$stage;line=$failureLine;error=($_|Out-String)}
    try{Save-ProtectedBundle (Join-Path $privateRoot ('dns-fault-'+[guid]::NewGuid().ToString('N')+'.dpapi')) ($diagnostic|ConvertTo-Json -Depth 5 -Compress)}catch{}
    $code=if($failure.Exception.Message -in @('AUTHORITATIVE_ZONE_MISSING','EXISTING_DNS_RECORD_CONFLICT','DNS_PLAN_CONFLICT','DNS_PLAN_INVALID','DESIGNATED_DNS_REQUIRED')){$failure.Exception.Message}else{'DNS_ACCESS_OR_PROVIDER_FAILED'}
    if($stage -eq 'CONNECT_ENCRYPTED_DCOM' -and $failure.Exception.ToString() -match '0x80070005|Access is denied|Accès refusé'){$code='DNS_DCOM_ACCESS_DENIED'}
    $safe=@{status='blocked';code=$code;stage=$stage;failure_line=$failureLine;created_count=$created;reconcile_before_retry=($stage -eq 'CREATE_MISSING_DNS_RECORDS');k3s_installed=$false}
    [IO.File]::WriteAllText($statusPath,($safe|ConvertTo-Json),[Text.Encoding]::UTF8)
    exit 2
}finally{
    if($session){Remove-CimSession $session -ErrorAction SilentlyContinue}
    if($secure){$secure.Dispose()};if($lockStream){$lockStream.Dispose()}
    $access=$null;$bundle=$null;$credential=$null;$records=$null;$plan=$null
}
