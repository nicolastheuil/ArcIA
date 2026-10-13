# Credentials are displayed only in the local protected UI, never in tool output.
[CmdletBinding()]
param([switch]$OpenPortal)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'ProtectedState.ps1')
$root=Get-ArcIAStateRoot -Identity -SelectLocally
$identity=(Read-ProtectedBundle (Join-Path $root 'identity.dpapi'))|ConvertFrom-Json
$instance=(Read-ProtectedBundle (Join-Path $root 'instance.dpapi'))|ConvertFrom-Json
$operation=(Read-ProtectedBundle (Join-Path $root 'vmware-operation.dpapi'))|ConvertFrom-Json
if(-not $operation.id -or $identity.operation_id -ne $instance.operation_id -or
    $identity.operation_id -ne $operation.id){throw 'IDENTITY_ACCESS_SCOPE_CONFLICT'}
$operation=$null
$url='https://'+$instance.config.network.public_hostname+'/admin/users'
if($OpenPortal){
    $browser=@((Join-Path ${env:ProgramFiles(x86)} 'Microsoft\Edge\Application\msedge.exe'),
        (Join-Path $env:ProgramFiles 'Microsoft\Edge\Application\msedge.exe'))|
        Where-Object {Test-Path -LiteralPath $_}|Select-Object -First 1
    if(-not $browser){throw 'EXISTING_BROWSER_REQUIRED'}
    $hostValue=$instance.config.network.public_hostname
    $address=[Net.IPAddress]::Parse($instance.endpoint_design.https_ip)
    if($hostValue -notmatch '^[a-z0-9][a-z0-9.-]+[a-z0-9]$'){throw 'IDENTITY_HOST_INVALID'}
    $profile=Join-Path $root 'identity-admin-browser';Initialize-PrivateDirectory $profile
    Start-Process -FilePath $browser -WindowStyle Normal -ArgumentList @(
        ('--user-data-dir="'+$profile+'"'),('--host-resolver-rules="MAP '+$hostValue+' '+$address.ToString()+'"'),
        '--no-proxy-server','--no-first-run','--no-default-browser-check','--new-window',$url)|Out-Null
}
Add-Type -AssemblyName System.Windows.Forms
$form=[Windows.Forms.Form]::new();$form.Text='ArcIA — administration des identités';$form.Width=760;$form.Height=310
$form.StartPosition='CenterScreen'
$values=@($url,$identity.admin_username,$identity.admin_password)
$labels=@('Portail privé HTTPS','Administrateur initial','Mot de passe initial')
for($i=0;$i -lt 3;$i++){
    $label=[Windows.Forms.Label]::new();$label.Text=$labels[$i];$label.SetBounds(15,20+45*$i,165,25)
    $box=[Windows.Forms.TextBox]::new();$box.Text=$values[$i];$box.ReadOnly=$true;$box.SetBounds(185,18+45*$i,535,26)
    if($i -eq 2){$box.UseSystemPasswordChar=$true;$passwordBox=$box}
    $form.Controls.Add($label);$form.Controls.Add($box)
}
$show=[Windows.Forms.CheckBox]::new();$show.Text='Afficher le mot de passe initial localement';$show.SetBounds(185,155,500,25)
$show.Add_CheckedChanged({$passwordBox.UseSystemPasswordChar=-not $show.Checked});$form.Controls.Add($show)
$note=[Windows.Forms.Label]::new();$note.Text='Première connexion : changer le mot de passe et configurer le MFA. Ensuite utiliser votre mot de passe personnel. La réapplication ne réinitialise aucun compte.'
$note.SetBounds(15,195,705,60);$form.Controls.Add($note)
try{$null=$form.ShowDialog()}finally{$form.Dispose();$values=$null;$identity=$null;$instance=$null}
