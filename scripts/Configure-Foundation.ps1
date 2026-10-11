[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'ProtectedState.ps1')
$privateRoot=Join-Path $env:LOCALAPPDATA 'ArcIA-Harness'
$bundlePath=Join-Path $privateRoot 'instance.dpapi'
$statusPath=Join-Path $privateRoot 'configuration-status.json'
$draftPath=Join-Path $privateRoot 'configuration-draft.dpapi'
function Set-ConfigurationStatus([string]$Status,[string]$Code){
    [IO.File]::WriteAllText($statusPath,(@{status=$Status;code=$Code;k3s_installed=$false}|ConvertTo-Json),[Text.Encoding]::UTF8)
}
function Save-ConfigurationDraft($Values){
    $temporary=Join-Path $privateRoot ('configuration-'+[guid]::NewGuid().ToString('N')+'.dpapi')
    Save-ProtectedBundle $temporary ($Values|ConvertTo-Json -Depth 8 -Compress)
    if(Test-Path -LiteralPath $draftPath){[IO.File]::Replace($temporary,$draftPath,[NullString]::Value)}
    else{Move-Item -LiteralPath $temporary -Destination $draftPath}
}
try {
    Initialize-PrivateDirectory $privateRoot
    if(Test-Path -LiteralPath $bundlePath){Set-ConfigurationStatus configured EXISTING_CONFIGURATION_PRESERVED;exit 0}
    $target=(Read-ProtectedBundle (Join-Path $privateRoot 'vmware-target.dpapi'))|ConvertFrom-Json
    $trust=(Read-ProtectedBundle (Join-Path $privateRoot 'ssh-trust.dpapi'))|ConvertFrom-Json
    $operation=(Read-ProtectedBundle (Join-Path $privateRoot 'vmware-operation.dpapi'))|ConvertFrom-Json
    $foundation=(Read-ProtectedBundle (Join-Path $privateRoot 'foundation-inventory.dpapi'))|ConvertFrom-Json
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    [Windows.Forms.Application]::EnableVisualStyles()
    $form=New-Object Windows.Forms.Form
    $form.Text='ArcIA - Endpoints et stockage K3s'
    $form.ClientSize=New-Object Drawing.Size(910,720)
    $form.StartPosition='CenterScreen';$form.TopMost=$true
    $form.FormBorderStyle='FixedDialog';$form.MaximizeBox=$false
    $fields=@{}
    $definitions=@(
        @('method','Bascule API / HTTPS','combo'),
        @('api_endpoint','FQDN API privee (DNS a configurer)','text'),
        @('api_ip','IPv4 reservee API (VIP ou repartiteur)','text'),
        @('public_hostname','FQDN HTTPS metier (aucune publication ici)','text'),
        @('https_ip','IPv4 privee HTTPS (meme VIP autorisee)','text'),
        @('pod_cidr','CIDR Pods propose, a verifier / modifier','text'),
        @('service_cidr','CIDR Services propose, a verifier / modifier','text'),
        @('existing_cidrs','CIDR entreprise / VPN / clients connus, virgules','text'),
        @('policy_id','Politique compatible sur le datastore choisi','combo'))
    $row=0
    foreach($definition in $definitions){
        $label=New-Object Windows.Forms.Label;$label.Text=$definition[1]
        $label.Location=New-Object Drawing.Point(15,(20+46*$row));$label.Size=New-Object Drawing.Size(425,35)
        $form.Controls.Add($label)
        if($definition[2] -eq 'combo'){$control=New-Object Windows.Forms.ComboBox;$control.DropDownStyle='DropDownList';$control.DisplayMember='name'}
        else{$control=New-Object Windows.Forms.TextBox}
        $control.Location=New-Object Drawing.Point(450,(18+46*$row));$control.Size=New-Object Drawing.Size(440,27)
        $fields[$definition[0]]=$control;$form.Controls.Add($control);$row++
    }
    $null=$fields.method.Items.Add([pscustomobject]@{id='node_vip';name='IP virtuelle sur les VM (reseau L2 commun requis)'})
    $null=$fields.method.Items.Add([pscustomobject]@{id='existing_load_balancer';name='Repartiteur existant avec bascule'})
    $fields.method.SelectedIndex=0
    foreach($policy in @($foundation.policies|Where-Object compatible)){$null=$fields.policy_id.Items.Add($policy)}
    $fields.pod_cidr.Text='10.42.0.0/16';$fields.service_cidr.Text='10.43.0.0/16'
    $reserved=New-Object Windows.Forms.CheckBox
    $reserved.Text='Les adresses sont reservees, libres et exclues du DHCP (ou celles du repartiteur existant).'
    $reserved.Location=New-Object Drawing.Point(15,445);$reserved.Size=New-Object Drawing.Size(875,30);$form.Controls.Add($reserved)
    $reviewed=New-Object Windows.Forms.CheckBox
    $reviewed.Text='Les CIDR renseignes sont ceux connus aujourd''hui (facultatif ; les futurs reseaux restent inconnus).'
    $reviewed.Location=New-Object Drawing.Point(15,480);$reviewed.Size=New-Object Drawing.Size(875,35);$form.Controls.Add($reviewed)
    $message=New-Object Windows.Forms.Label
    $message.Text='Compte GitHub, VM et SSH deja repris. Aucun mot de passe demande. VIP dans le sous-reseau des VM. CIDR inconnus : laisser le champ vide ; les routes visibles seront controlees. Tout futur VPN exigera un controle de conflit. Saisie chiffree hors OneDrive ; gates en attente de tests.'
    $message.Location=New-Object Drawing.Point(15,530);$message.Size=New-Object Drawing.Size(875,105);$form.Controls.Add($message)
    if(Test-Path -LiteralPath $draftPath){
        $draft=(Read-ProtectedBundle $draftPath)|ConvertFrom-Json
        foreach($key in $fields.Keys){
            if($key -in @('method','policy_id')){
                for($i=0;$i -lt $fields[$key].Items.Count;$i++){if($fields[$key].Items[$i].id -eq $draft.$key){$fields[$key].SelectedIndex=$i}}
            }elseif($null -ne $draft.$key){$fields[$key].Text=$draft.$key}
        }
        $reserved.Checked=[bool]$draft.addresses_reserved;$reviewed.Checked=[bool]$draft.cidrs_reviewed;$draft=$null
    }
    $button=New-Object Windows.Forms.Button;$button.Text='Valider et enregistrer les parametres chiffres'
    $button.Location=New-Object Drawing.Point(430,665);$button.Size=New-Object Drawing.Size(460,35);$form.Controls.Add($button)
    $button.Add_Click({
        $process=$null
        try {
            $message.Text='Validation locale en cours...';$form.Refresh()
            $values=@{}
            foreach($key in $fields.Keys){
                if($key -in @('method','policy_id')){$values[$key]=$fields[$key].SelectedItem.id}
                else{$values[$key]=$fields[$key].Text.Trim()}
            }
            $values.addresses_reserved=[bool]$reserved.Checked;$values.cidrs_reviewed=[bool]$reviewed.Checked
            Save-ConfigurationDraft $values
            $start=New-Object Diagnostics.ProcessStartInfo
            $start.FileName=Join-Path $env:LOCALAPPDATA 'ArcIA-Validation\venv\Scripts\python.exe'
            $start.Arguments='"'+(Join-Path $PSScriptRoot 'bootstrap_config.py')+'"'
            $start.UseShellExecute=$false;$start.CreateNoWindow=$true
            $start.RedirectStandardInput=$true;$start.RedirectStandardOutput=$true;$start.RedirectStandardError=$true
            if($PSVersionTable.PSEdition -eq 'Core'){$start.StandardInputEncoding=New-Object Text.UTF8Encoding($false)}
            $start.StandardOutputEncoding=[Text.Encoding]::UTF8
            $process=New-Object Diagnostics.Process;$process.StartInfo=$start;$null=$process.Start()
            $payload=@{target=$target;trust=$trust;operation_id=$operation.id;foundation=$foundation;private_root=$privateRoot;values=$values}
            $process.StandardInput.Write(($payload|ConvertTo-Json -Depth 18 -Compress));$process.StandardInput.Close()
            $output=$process.StandardOutput.ReadToEndAsync();$errors=$process.StandardError.ReadToEndAsync()
            if(-not $process.WaitForExit(20000)){$process.Kill();throw 'LOCAL_VALIDATION_TIMEOUT'}
            $response=$output.GetAwaiter().GetResult()|ConvertFrom-Json;$null=$errors.GetAwaiter().GetResult()
            if($process.ExitCode -ne 0 -or -not $response.bundle){
                Set-ConfigurationStatus blocked $response.safe.code
                $message.Text='Saisie a corriger : '+$response.safe.code+'. Verifier FQDN, IP reservees, CIDR connus sans chevauchement, politique et reservation des IP.'
                return
            }
            Save-ProtectedBundle $bundlePath ($response.bundle|ConvertTo-Json -Depth 20 -Compress)
            Set-ConfigurationStatus configured CONFIGURATION_ENCRYPTED_GATES_PENDING
            $button.Enabled=$false
            $null=[Windows.Forms.MessageBox]::Show($form,'Configuration chiffree enregistree. Les tests reseau et la qualification CPI/CSI peuvent continuer.','ArcIA - Enregistrement confirme')
            $form.Close()
        }catch{
            Set-ConfigurationStatus blocked LOCAL_CONFIGURATION_SAVE_FAILED
            $message.Text='Enregistrement impossible. Le brouillon chiffre est conserve ; aucun deploiement effectue.'
        }finally{if($process){$process.Dispose()};$payload=$null;$values=$null;$response=$null}
    })
    Set-ConfigurationStatus awaiting_local_input ENDPOINT_STORAGE_FORM_OPEN
    $null=$form.ShowDialog()
}catch{
    Set-ConfigurationStatus blocked CONFIGURATION_FORM_FAILED
    exit 2
}finally{$target=$null;$trust=$null;$foundation=$null}
