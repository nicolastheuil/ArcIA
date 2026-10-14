# Show credentials only in a local Windows form; never return them to stdout.
[CmdletBinding()]
param([switch]$OpenPortal,[switch]$UseIp)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'ProtectedState.ps1')
$root=Get-ArcIAStateRoot -Identity -SelectLocally
$previousRoot=$env:ARCIA_STATE_ROOT
try{
    $env:ARCIA_STATE_ROOT=$root
    & (Join-Path $PSScriptRoot 'Invoke-ClusterFoundation.ps1') -Action read_omniroute_access
    if($LASTEXITCODE -ne 0){throw 'ROUTING_ACCESS_UNAVAILABLE'}
    $access=(Read-ProtectedBundle (Join-Path $root 'cluster-read_omniroute_access.dpapi'))|ConvertFrom-Json
    $operation=(Read-ProtectedBundle (Join-Path $root 'vmware-operation.dpapi'))|ConvertFrom-Json
    if($access.operation_id -ne $operation.id){throw 'ROUTING_ACCESS_SCOPE_CONFLICT'}
    if($access.hostname -notmatch '^[a-z0-9][a-z0-9.-]+[a-z0-9]$' -or $access.port -ne 20129){throw 'ROUTING_ACCESS_ENDPOINT_INVALID'}
    $address=[Net.IPAddress]::Parse($access.endpoint_address)
    $url='https://'+$access.hostname+':20129/dashboard'
    if($UseIp){$url='https://'+$address.ToString()+':20129/dashboard'}
    if($OpenPortal){
        $browser=@((Join-Path ${env:ProgramFiles(x86)} 'Microsoft/Edge/Application/msedge.exe'),
            (Join-Path $env:ProgramFiles 'Microsoft/Edge/Application/msedge.exe'))|Where-Object {Test-Path -LiteralPath $_}|Select-Object -First 1
        if(-not $browser){throw 'EXISTING_BROWSER_REQUIRED'}
        $profile=Join-Path $root 'routing-admin-browser';Initialize-PrivateDirectory $profile
        Start-Process -FilePath $browser -WindowStyle Normal -ArgumentList @(
            ('--user-data-dir="'+$profile+'"'),('--host-resolver-rules="MAP '+$access.hostname+' '+$address.ToString()+'"'),
            '--no-proxy-server','--no-first-run','--no-default-browser-check','--new-window',$url)|Out-Null
    }
    Add-Type -AssemblyName System.Windows.Forms
    $form=[Windows.Forms.Form]::new();$form.Text='ArcIA — OmniRoute, administration LAN';$form.Width=770;$form.Height=260
    $form.StartPosition='CenterScreen'
    $values=@($url,$access.initial_password);$labels=@('Portail LAN HTTPS','Mot de passe initial')
    for($i=0;$i -lt 2;$i++){
        $label=[Windows.Forms.Label]::new();$label.Text=$labels[$i];$label.SetBounds(15,20+45*$i,170,25)
        $box=[Windows.Forms.TextBox]::new();$box.Text=$values[$i];$box.ReadOnly=$true;$box.SetBounds(190,18+45*$i,545,26)
        if($i -eq 1){$box.UseSystemPasswordChar=$true;$passwordBox=$box}
        $form.Controls.Add($label);$form.Controls.Add($box)
    }
    $show=[Windows.Forms.CheckBox]::new();$show.Text='Afficher le mot de passe initial localement';$show.SetBounds(190,112,500,25)
    $show.Add_CheckedChanged({$passwordBox.UseSystemPasswordChar=-not $show.Checked});$form.Controls.Add($show)
    $note=[Windows.Forms.Label]::new();$note.Text='Changer le mot de passe à la première connexion. Ce formulaire ne lit pas le mot de passe changé. Réapplication : aucun compte ni volume réinitialisé. Aucun port à publier sur Internet.'
    $note.SetBounds(15,150,720,65);$form.Controls.Add($note)
    $null=$form.ShowDialog()
}finally{
    if($form){$form.Dispose()};$access=$null;$values=$null;$operation=$null
    $env:ARCIA_STATE_ROOT=$previousRoot
}
