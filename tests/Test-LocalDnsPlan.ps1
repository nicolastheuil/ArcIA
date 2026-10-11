$ErrorActionPreference='Stop'
$scriptPath=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../scripts/Invoke-LocalDnsPlan.ps1'))
$planPath=Join-Path ([IO.Path]::GetTempPath()) ('arcia-dns-synthetic-'+[guid]::NewGuid().ToString('N')+'.json')
@{server_addresses=@('192.0.2.53');records=@(@{name='api.synthetic.test';address='192.0.2.20'},@{name='app.synthetic.test';address='192.0.2.21'})}|ConvertTo-Json -Depth 5|Set-Content -LiteralPath $planPath
try{
    foreach($scenario in @('create','existing','conflict','wrong_target','provider_failure')){
        $pipeline=[PowerShell]::Create()
        try{
            $null=$pipeline.AddScript({
                param($scriptPath,$planPath,$scenario)
                $global:scenario=$scenario;$global:store=@()
                function New-Record($Name,$Address){[pscustomobject]@{HostName=$Name;RecordType='A';RecordData=[pscustomobject]@{IPv4Address=[Net.IPAddress]::Parse($Address)}}}
                if($scenario -eq 'existing'){$global:store=@((New-Record 'api' '192.0.2.20'),(New-Record 'app' '192.0.2.21'))}
                if($scenario -eq 'conflict'){$global:store=@((New-Record 'app' '192.0.2.99'))}
                function Get-NetIPAddress {param($AddressFamily);[pscustomobject]@{IPAddress=if($global:scenario -eq 'wrong_target'){'192.0.2.54'}else{'192.0.2.53'}}}
                function Import-Module {param($Name)}
                function Get-DnsServerZone {[pscustomobject]@{ZoneName='synthetic.test'}}
                function Get-DnsServerResourceRecord {param($ZoneName);if($global:scenario -eq 'provider_failure'){throw 'SYNTHETIC_PROVIDER_FAILURE'};$global:store}
                function Add-DnsServerResourceRecordA {param($ZoneName,$Name,$IPv4Address,$TimeToLive);$global:store+=New-Record $Name $IPv4Address}
                & $scriptPath -PlanPath $planPath -Create
            }).AddArgument($scriptPath).AddArgument($planPath).AddArgument($scenario)
            $output=$pipeline.Invoke()
            if($pipeline.Streams.Error.Count){throw 'SYNTHETIC_DNS_EXECUTION_ERROR'}
            $result=($output -join "`n")|ConvertFrom-Json
            switch($scenario){
                create {if($result.code -ne 'DNS_RECORDS_VERIFIED' -or $result.created_count -ne 2 -or $result.verified_count -ne 2){throw 'DNS_CREATE_OR_READBACK_FAILED'}}
                existing {if($result.code -ne 'DNS_RECORDS_VERIFIED' -or $result.created_count -ne 0){throw 'DNS_REPLAY_NOT_IDEMPOTENT'}}
                conflict {if($result.code -ne 'EXISTING_DNS_RECORD_CONFLICT' -or $result.created_count -ne 0){throw 'ALL_RECORDS_NOT_PREFLIGHTED_BEFORE_WRITE'}}
                wrong_target {if($result.code -ne 'DESIGNATED_DNS_SERVER_REQUIRED' -or $result.created_count -ne 0){throw 'FOREIGN_TARGET_NOT_BLOCKED'}}
                provider_failure {if($result.code -ne 'DNS_LOCAL_ACCESS_OR_PROVIDER_FAILED' -or $result.created_count -ne 0){throw 'PROVIDER_FAILURE_TREATED_AS_ABSENCE'}}
            }
        }finally{$pipeline.Dispose()}
    }
}finally{Remove-Item -LiteralPath $planPath -Force}
Write-Output 'LOCAL_DNS_SYNTHETIC_CREATE_REPLAY_CONFLICT_TARGET_PROVIDER_TESTS_PASSED; NO_REMOTE_ACCESS'
