# Run on the designated Windows DNS server with an authorized personal AD identity.
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$PlanPath,[switch]$Create)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'DnsRecordPlan.ps1')
$created=0;$stage='VALIDATE_LOCAL_TARGET'
try {
    $plan=Get-Content -LiteralPath $PlanPath -Raw|ConvertFrom-Json
    $localAddresses=@(Get-NetIPAddress -AddressFamily IPv4|ForEach-Object {$_.IPAddress})
    if(-not @($plan.server_addresses|Where-Object {$_ -in $localAddresses}).Count){throw 'DESIGNATED_DNS_SERVER_REQUIRED'}
    if(@($plan.records).Count -lt 1 -or @($plan.records).Count -gt 2){throw 'DNS_PLAN_INVALID'}
    foreach($record in $plan.records){
        if($record.name -notmatch '^[A-Za-z0-9][A-Za-z0-9.-]{0,252}$' -or $record.name -notmatch '\.' -or
            [Net.IPAddress]::Parse($record.address).AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork){throw 'DNS_PLAN_INVALID'}
    }
    Import-Module DnsServer -ErrorAction Stop
    $stage='PREFLIGHT_ALL_RECORDS'
    $zones=@(Get-DnsServerZone|ForEach-Object {[pscustomobject]@{Name=$_.ZoneName}})
    $actions=@()
    foreach($record in $plan.records){
        $zone=Get-AuthoritativeZone $record.name $zones
        $relative=if($record.name -ieq $zone){'@'}else{$record.name.Substring(0,$record.name.Length-$zone.Length-1)}
        # Read the zone first so a provider/access failure cannot be mistaken for absence.
        $existing=@(Get-DnsServerResourceRecord -ZoneName $zone|Where-Object {$_.HostName -ieq $relative})
        if($existing.Count -and -not (Test-ExactLocalDnsRecord $existing $record.address)){throw 'EXISTING_DNS_RECORD_CONFLICT'}
        $actions+=@{zone=$zone;name=$relative;address=$record.address;exists=[bool]$existing.Count}
    }
    if($Create){
        $stage='CREATE_MISSING_RECORDS'
        foreach($item in $actions|Where-Object {-not $_.exists}){
            $null=Add-DnsServerResourceRecordA -ZoneName $item.zone -Name $item.name -IPv4Address $item.address -TimeToLive ([TimeSpan]::FromSeconds(60))
            $created++
        }
    }
    $stage='VERIFY_RECORDS';$verified=0
    foreach($item in $actions){
        $readback=@(Get-DnsServerResourceRecord -ZoneName $item.zone|Where-Object {$_.HostName -ieq $item.name})
        if(Test-ExactLocalDnsRecord $readback $item.address){$verified++}
    }
    @{status=if($verified -eq $actions.Count){'verified'}else{'prepared'};code=if($verified -eq $actions.Count){'DNS_RECORDS_VERIFIED'}else{'DNS_PLAN_READY'};created_count=$created;verified_count=$verified}|ConvertTo-Json
}catch{
    $allowed=@('DESIGNATED_DNS_SERVER_REQUIRED','DNS_PLAN_INVALID','AUTHORITATIVE_ZONE_MISSING','EXISTING_DNS_RECORD_CONFLICT')
    @{status='blocked';code=if($_.Exception.Message -in $allowed){$_.Exception.Message}else{'DNS_LOCAL_ACCESS_OR_PROVIDER_FAILED'};stage=$stage;created_count=$created;reconcile_before_retry=($stage -eq 'CREATE_MISSING_RECORDS')}|ConvertTo-Json
    exit 2
}
