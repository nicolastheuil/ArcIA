[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'ProtectedState.ps1')
$privateRoot=Join-Path $env:LOCALAPPDATA 'ArcIA-Harness'
try {
    Initialize-PrivateDirectory $privateRoot
    $bundle=(Read-ProtectedBundle (Join-Path $privateRoot 'instance.dpapi'))|ConvertFrom-Json
    $target=(Read-ProtectedBundle (Join-Path $privateRoot 'vmware-target.dpapi'))|ConvertFrom-Json
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    $form=New-Object Windows.Forms.Form
    $form.Text='ArcIA - Creation DNS interne protegee'
    $form.ClientSize=New-Object Drawing.Size(940,510);$form.StartPosition='CenterScreen';$form.TopMost=$true
    $records=New-Object Windows.Forms.TextBox;$records.Multiline=$true;$records.ReadOnly=$true
    $records.Location=New-Object Drawing.Point(15,15);$records.Size=New-Object Drawing.Size(910,85)
    $records.Text='Enregistrements A a creer (aucun ecrasement autorise) :'+"`r`n"+$bundle.config.network.api_endpoint+' -> '+$bundle.endpoint_design.api_ip+"`r`n"+$bundle.config.network.public_hostname+' -> '+$bundle.endpoint_design.https_ip
    $form.Controls.Add($records)
    $fields=@{}
    $row=0
    foreach($definition in @(@('server','Serveur Windows DNS designe'),@('username','Votre compte AD autorise (DOMAINE\compte ou UPN)'),@('password','Mot de passe (saisie locale uniquement)'))){
        $label=New-Object Windows.Forms.Label;$label.Text=$definition[1]
        $label.Location=New-Object Drawing.Point(15,(120+50*$row));$label.Size=New-Object Drawing.Size(430,35);$form.Controls.Add($label)
        $field=New-Object Windows.Forms.TextBox;$field.Location=New-Object Drawing.Point(455,(118+50*$row));$field.Size=New-Object Drawing.Size(470,28)
        if($definition[0] -eq 'password'){$field.UseSystemPasswordChar=$true}
        $fields[$definition[0]]=$field;$form.Controls.Add($field);$row++
    }
    $fields.server.Text=$target.dns[0]
    $scope=New-Object Windows.Forms.CheckBox
    $scope.Text='Ce serveur DNS est la cible autorisee pour ces deux enregistrements.'
    $scope.Location=New-Object Drawing.Point(15,280);$scope.Size=New-Object Drawing.Size(910,35);$form.Controls.Add($scope)
    $message=New-Object Windows.Forms.Label
    $message.Text='Connexion RPC/DCOM chiffree (PacketPrivacy), sans modification de TrustedHosts. Les zones doivent exister. Le programme verifie les deux noms avant toute creation et refuse un record different. Acces chiffres DPAPI, hors OneDrive.'
    $message.Location=New-Object Drawing.Point(15,330);$message.Size=New-Object Drawing.Size(910,90);$form.Controls.Add($message)
    $button=New-Object Windows.Forms.Button;$button.Text='Connecter et creer uniquement les records manquants'
    $button.Location=New-Object Drawing.Point(410,455);$button.Size=New-Object Drawing.Size(515,35);$form.Controls.Add($button)
    $button.Add_Click({
        try{
            if(-not $scope.Checked -or -not $fields.server.Text.Trim() -or -not $fields.username.Text.Trim() -or -not $fields.password.Text){$message.Text='Renseigner serveur, compte, mot de passe et confirmer la cible DNS.';return}
            $access=@{server=$fields.server.Text.Trim();username=$fields.username.Text.Trim();password=$fields.password.Text;authorized_server=$true}
            $temporary=Join-Path $privateRoot ('dns-access-'+[guid]::NewGuid().ToString('N')+'.dpapi')
            Save-ProtectedBundle $temporary ($access|ConvertTo-Json -Compress)
            $destination=Join-Path $privateRoot 'dns-access.dpapi'
            if(Test-Path -LiteralPath $destination){[IO.File]::Replace($temporary,$destination,[NullString]::Value)}else{Move-Item -LiteralPath $temporary -Destination $destination}
            $fields.password.Clear();$button.Enabled=$false
            $message.Text='Connexion et controle des zones/records en cours. Ne pas relancer le bouton.';$form.Refresh()
            $start=New-Object Diagnostics.ProcessStartInfo
            $start.FileName='powershell.exe';$start.Arguments='-NoProfile -File "'+(Join-Path $PSScriptRoot 'Manage-InternalDns.ps1')+'" -Create'
            $start.UseShellExecute=$false;$start.CreateNoWindow=$true;$start.RedirectStandardOutput=$true;$start.RedirectStandardError=$true
            $process=New-Object Diagnostics.Process;$process.StartInfo=$start;$null=$process.Start()
            $output=$process.StandardOutput.ReadToEndAsync();$errors=$process.StandardError.ReadToEndAsync()
            if(-not $process.WaitForExit(240000)){$process.Kill();throw 'DNS_OPERATION_RECONCILIATION_REQUIRED'}
            $null=$output.GetAwaiter().GetResult();$null=$errors.GetAwaiter().GetResult();$process.Dispose()
            $status=Get-Content (Join-Path $privateRoot 'dns-status.json') -Raw|ConvertFrom-Json
            if($status.status -eq 'verified'){
                $null=[Windows.Forms.MessageBox]::Show($form,'Enregistrements DNS verifies. La resolution depuis les VM sera recontrolee.','ArcIA - DNS verifies');$form.Close()
            }else{$message.Text='Operation arretee : '+$status.code+'. Aucun record different n''est ecrase. Les acces restent chiffres pour diagnostic local.';$button.Enabled=$true}
        }catch{$message.Text='Operation locale interrompue. Reconciliation des records avant reprise ; ne pas recopier les acces dans le chat.'}
        finally{$access=$null}
    })
    [IO.File]::WriteAllText((Join-Path $privateRoot 'dns-form-status.json'),'{"status":"awaiting_local_input","code":"DNS_PROTECTED_FORM_OPEN"}')
    $null=$form.ShowDialog()
}catch{
    [IO.File]::WriteAllText((Join-Path $privateRoot 'dns-form-status.json'),'{"status":"blocked","code":"DNS_PROTECTED_FORM_FAILED"}')
    exit 2
}finally{$bundle=$null;$target=$null}
