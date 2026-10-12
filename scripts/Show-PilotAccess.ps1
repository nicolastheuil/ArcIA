# Display private access details only in a local window; never emit them to stdout.
[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'ProtectedState.ps1')
$root=Join-Path $env:LOCALAPPDATA 'ArcIA-Harness'
$pilot=(Read-ProtectedBundle (Join-Path $root 'pilot-credentials.dpapi'))|ConvertFrom-Json
$operation=(Read-ProtectedBundle (Join-Path $root 'vmware-operation.dpapi'))|ConvertFrom-Json
if($pilot.operation_id -ne $operation.id){throw 'PILOT_CREDENTIAL_SCOPE_CONFLICT'}
Add-Type -AssemblyName System.Windows.Forms
$form=[Windows.Forms.Form]::new()
$form.Text='ArcIA — accès au pilote de qualification'
$form.Width=650;$form.Height=285;$form.StartPosition='CenterScreen'
$values=@(('https://'+$pilot.hostname),$pilot.username,$pilot.password)
$labels=@('Adresse HTTPS privée','Utilisateur','Mot de passe')
for($i=0;$i -lt 3;$i++){
    $label=[Windows.Forms.Label]::new();$label.Text=$labels[$i];$label.SetBounds(15,20+45*$i,155,25)
    $box=[Windows.Forms.TextBox]::new();$box.Text=$values[$i];$box.ReadOnly=$true;$box.SetBounds(175,18+45*$i,420,26)
    if($i -eq 2){$box.UseSystemPasswordChar=$true;$passwordBox=$box}
    $form.Controls.Add($label);$form.Controls.Add($box)
}
$show=[Windows.Forms.CheckBox]::new();$show.Text='Afficher le mot de passe localement';$show.SetBounds(175,153,360,25)
$show.Add_CheckedChanged({$passwordBox.UseSystemPasswordChar=-not $show.Checked})
$form.Controls.Add($show)
$note=[Windows.Forms.Label]::new();$note.Text='Réseau privé requis. TLS auto-signé du pilote. Appels IA externes désactivés.'
$note.SetBounds(15,190,600,45);$form.Controls.Add($note)
try{$null=$form.ShowDialog()}finally{$form.Dispose();$pilot=$null;$values=$null}
