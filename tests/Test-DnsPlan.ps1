$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot '../scripts/DnsRecordPlan.ps1')
$zones=@([pscustomobject]@{Name='synthetic.test'},[pscustomobject]@{Name='platform.synthetic.test'})
if((Get-AuthoritativeZone 'api.platform.synthetic.test' $zones) -ne 'platform.synthetic.test'){throw 'LONGEST_ZONE_FAILED'}
$blocked=$false
try{Get-AuthoritativeZone 'api.other.test' $zones|Out-Null}catch{$blocked=$true}
if(-not $blocked){throw 'MISSING_ZONE_NOT_BLOCKED'}
$record=[pscustomobject]@{CimClass=[pscustomobject]@{CimClassName='MicrosoftDNS_AType'};IPAddress='192.0.2.20'}
if(-not (Test-ExactDnsRecord @($record) '192.0.2.20')){throw 'MATCHING_RECORD_FAILED'}
if(Test-ExactDnsRecord @($record) '192.0.2.21'){throw 'DIFFERENT_RECORD_NOT_BLOCKED'}
if(Test-ExactDnsRecord @($record,$record) '192.0.2.20'){throw 'MULTIPLE_RECORDS_NOT_BLOCKED'}
$record.CimClass.CimClassName='MicrosoftDNS_CNAMEType'
if(Test-ExactDnsRecord @($record) '192.0.2.20'){throw 'CNAME_NOT_BLOCKED'}
$localRecord=[pscustomobject]@{RecordType='A';RecordData=[pscustomobject]@{IPv4Address=[Net.IPAddress]::Parse('192.0.2.20')}}
if(-not (Test-ExactLocalDnsRecord @($localRecord) '192.0.2.20')){throw 'LOCAL_MATCHING_RECORD_FAILED'}
if(Test-ExactLocalDnsRecord @($localRecord) '192.0.2.21'){throw 'LOCAL_DIFFERENT_RECORD_NOT_BLOCKED'}
if(Test-ExactLocalDnsRecord @($localRecord,$localRecord) '192.0.2.20'){throw 'LOCAL_MULTIPLE_RECORDS_NOT_BLOCKED'}
$localRecord.RecordType='CNAME'
if(Test-ExactLocalDnsRecord @($localRecord) '192.0.2.20'){throw 'LOCAL_CNAME_NOT_BLOCKED'}
# Regression: -Protocol cannot be combined with the DCOM-specific parameter set.
$options=New-CimSessionOption -PacketPrivacy -PacketIntegrity -Impersonation Impersonate
if(-not $options.PacketPrivacy -or -not $options.PacketIntegrity){throw 'DCOM_ENCRYPTION_OPTIONS_REQUIRED'}
Write-Output 'SYNTHETIC_DNS_PLAN_TESTS_PASSED; NO_REMOTE_ACCESS'
