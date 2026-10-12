[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'ProtectedState.ps1')
$root=Get-ArcIAStateRoot
try{
    $access=(Read-ProtectedBundle (Join-Path $root 'dns-access.dpapi'))|ConvertFrom-Json
    $bundle=(Read-ProtectedBundle (Join-Path $root 'instance.dpapi'))|ConvertFrom-Json
    if(-not $access.authorized_server){throw 'DESIGNATED_DNS_REQUIRED'}
    $addresses=@([Net.Dns]::GetHostAddresses($access.server)|Where-Object {$_.AddressFamily -eq [Net.Sockets.AddressFamily]::InterNetwork}|ForEach-Object {$_.IPAddressToString})
    if(-not $addresses.Count){throw 'DESIGNATED_DNS_IPV4_REQUIRED'}
    $directory=Join-Path $root ('dns-local-'+[guid]::NewGuid().ToString('N'))
    Initialize-PrivateDirectory $directory
    $records=@([pscustomobject]@{name=$bundle.config.network.api_endpoint;address=$bundle.endpoint_design.api_ip},[pscustomobject]@{name=$bundle.config.network.public_hostname;address=$bundle.endpoint_design.https_ip})|Sort-Object name -Unique
    $plan=@{operation_id=$bundle.operation_id;server_addresses=$addresses;records=@($records)}
    [IO.File]::WriteAllText((Join-Path $directory 'plan.private.json'),($plan|ConvertTo-Json -Depth 7),[Text.Encoding]::UTF8)
    foreach($name in @('Invoke-LocalDnsPlan.ps1','DnsRecordPlan.ps1')){Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination (Join-Path $directory $name)}
    $instructions=@'
ArcIA - DNS local
Ce dossier contient uniquement le plan prive DNS et les scripts, aucun identifiant ni mot de passe.
Le conserver hors Git, cloud et OneDrive. Le copier sur le serveur DNS designe par un canal interne autorise.
Sur ce serveur, ouvrir Windows PowerShell avec votre identite AD autorisee, puis dans ce dossier :
powershell.exe -NoProfile -File .\Invoke-LocalDnsPlan.ps1 -PlanPath .\plan.private.json
Si le resultat est DNS_PLAN_READY :
powershell.exe -NoProfile -File .\Invoke-LocalDnsPlan.ps1 -PlanPath .\plan.private.json -Create
Le programme refuse une autre cible, une zone absente et tout record existant different.
Il verifie tous les records avant toute creation et ne supprime/modifie aucun record existant.
Un echec apres creation exige reconciliation avant reprise ; le script reconnait les records exacts.
Communiquer uniquement DNS_RECORDS_VERIFIED ou le code generique obtenu. Supprimer le dossier apres verification depuis les VM.
'@
    [IO.File]::WriteAllText((Join-Path $directory 'LIRE-MOI.txt'),$instructions,[Text.Encoding]::UTF8)
    Save-ProtectedBundle (Join-Path $root ('dns-local-reference-'+[guid]::NewGuid().ToString('N')+'.dpapi')) (@{directory=$directory;operation_id=$bundle.operation_id}|ConvertTo-Json -Compress)
    @{status='prepared';code='LOCAL_DNS_PACKAGE_CREATED';contains_credentials=$false;created_records=0}|ConvertTo-Json
}catch{
    @{status='blocked';code='LOCAL_DNS_PACKAGE_FAILED'}|ConvertTo-Json
    exit 2
}finally{$access=$null;$bundle=$null;$plan=$null;$records=$null}
