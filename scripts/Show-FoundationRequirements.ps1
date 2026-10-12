# Display private records locally. Never render the textbox content to agent tools.
[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'ProtectedState.ps1')
$privateRoot=Get-ArcIAStateRoot
try {
    $bundle=(Read-ProtectedBundle (Join-Path $privateRoot 'instance.dpapi'))|ConvertFrom-Json
    $target=(Read-ProtectedBundle (Join-Path $privateRoot 'vmware-target.dpapi'))|ConvertFrom-Json
    $inventory=((Read-ProtectedBundle (Join-Path $privateRoot 'vmware-inventory.dpapi'))|ConvertFrom-Json).inventory
    $plan=Get-Content -LiteralPath (Join-Path $PSScriptRoot '../infra/vmware/csi-permissions.plan.json') -Raw|ConvertFrom-Json
    $dns=@(
        ($bundle.config.network.api_endpoint+'  A  '+$bundle.endpoint_design.api_ip),
        ($bundle.config.network.public_hostname+'  A  '+$bundle.endpoint_design.https_ip))|Sort-Object -Unique
    $lines=New-Object Collections.Generic.List[string]
    $lines.Add('DNS INTERNE : enregistrements A a creer (TTL de qualification propose : 60 s)')
    foreach($record in $dns){$lines.Add($record)}
    $lines.Add('')
    $lines.Add('Compte technique CPI/CSI arcia-cpi-csi cree dans le SSO local vCenter ; droits non qualifies.')
    $lines.Add('Ne pas reutiliser le compte personnel de deploiement.')
    $lines.Add('Mot de passe / coffre : uniquement programme protege local, jamais le chat.')
    $lines.Add('')
    $lines.Add('Plan de droits a revoir puis qualifier : aucun droit applique par cet ecran.')
    foreach($role in $plan.roles){
        $lines.Add($role.name+' ; portee '+$role.scope+' ; propagation : '+$role.propagate)
        $lines.Add('  '+($role.privileges -join ', '))
    }
    $lines.Add('')
    foreach($mapping in @(@('clusters','cluster_id'),@('datastores','datastore_id'),@('folders','folder_id'))){
        $selection=@($inventory.($mapping[0])|Where-Object id -eq $target.($mapping[1]))
        foreach($item in $selection){$lines.Add('Cible '+$mapping[0]+' : '+$item.path)}
    }
    $lines.Add('VM : '+(($bundle.config.nodes|ForEach-Object name)-join ', '))
    $lines.Add('')
    $lines.Add('CIDR futurs inconnus : controles limites aux routes actuellement visibles. VPN clients desactives.')
    $lines.Add('K3s / VIP / CPI / CSI non installes. Etapes suivantes : DNS, reconciliation des droits, test VIP.')
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    $form=New-Object Windows.Forms.Form
    $form.Text='ArcIA - DNS et droits techniques a qualifier'
    $form.ClientSize=New-Object Drawing.Size(1000,760);$form.StartPosition='CenterScreen';$form.TopMost=$true
    $box=New-Object Windows.Forms.TextBox
    $box.Multiline=$true;$box.ReadOnly=$true;$box.ScrollBars='Both';$box.WordWrap=$false
    $box.Location=New-Object Drawing.Point(15,15);$box.Size=New-Object Drawing.Size(970,675)
    $box.Text=$lines -join "`r`n";$form.Controls.Add($box)
    $copy=New-Object Windows.Forms.Button;$copy.Text='Copier uniquement les 2 enregistrements DNS'
    $copy.Location=New-Object Drawing.Point(15,710);$copy.Size=New-Object Drawing.Size(475,35)
    $copy.Add_Click({[Windows.Forms.Clipboard]::SetText(($dns-join "`r`n"))});$form.Controls.Add($copy)
    $close=New-Object Windows.Forms.Button;$close.Text='Fermer';$close.Location=New-Object Drawing.Point(810,710)
    $close.Size=New-Object Drawing.Size(175,35);$close.Add_Click({$form.Close()});$form.Controls.Add($close)
    [IO.File]::WriteAllText((Join-Path $privateRoot 'foundation-requirements-status.json'),'{"status":"awaiting_prerequisites","code":"DNS_AND_SERVICE_PERMISSIONS_REQUIRED","k3s_installed":false}')
    $null=$form.ShowDialog()
}catch{Write-Output 'LOCAL_REQUIREMENTS_VIEW_FAILED';exit 2}
finally{$bundle=$null;$target=$null;$inventory=$null;$dns=$null;$lines=$null}
