function Get-AuthoritativeZone {
    param([string]$Name,[object[]]$Zones)
    $matches=@($Zones|Where-Object {($Name -ieq $_.Name -or $Name.EndsWith('.'+$_.Name,[StringComparison]::OrdinalIgnoreCase)) -and $_.Name -ne '.'}|Sort-Object {$_.Name.Length} -Descending)
    if(-not $matches.Count){throw 'AUTHORITATIVE_ZONE_MISSING'}
    return $matches[0].Name
}
function Test-ExactDnsRecord {
    param([object[]]$Records,[string]$Address)
    return ($Records.Count -eq 1 -and $Records[0].CimClass.CimClassName -eq 'MicrosoftDNS_AType' -and $Records[0].IPAddress -eq $Address)
}
function Test-ExactLocalDnsRecord {
    param([object[]]$Records,[string]$Address)
    return ($Records.Count -eq 1 -and $Records[0].RecordType -eq 'A' -and
        $Records[0].RecordData.IPv4Address.IPAddressToString -eq $Address)
}
