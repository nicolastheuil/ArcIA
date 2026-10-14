[CmdletBinding()]
param([ValidateSet('Export','Import')][string]$Action='Export',[switch]$ReplaceExisting)
$ErrorActionPreference='Stop'
if($PSVersionTable.PSVersion -lt [version]'7.4'){Write-Output 'POWERSHELL_7_4_OR_NEWER_REQUIRED';exit 2}
. (Join-Path $PSScriptRoot 'ProtectedState.ps1')
. (Join-Path $PSScriptRoot 'PortableState.ps1')
$workspace=[IO.Path]::GetFullPath((Split-Path $PSScriptRoot -Parent))
$directory=Join-Path $workspace 'secrets/local';$archive=Join-Path $directory 'arcia-private.arciap'
$localRoot=$null
try{
    $localRoot=Get-ArcIAStateRoot
    $null=New-Item -ItemType Directory -Path $directory -Force
    # OneDrive Cloud Files placeholders are expected here; actual filesystem
    # redirections are refused. Plaintext state is still outside OneDrive.
    if((Get-Item -LiteralPath $directory -Force).LinkType -in @('SymbolicLink','Junction')){throw 'PORTABLE_FOLDER_LINK_REFUSED'}
    & git -C $workspace check-ignore --quiet -- 'secrets/local/arcia-private.arciap'
    if($LASTEXITCODE -ne 0){throw 'PORTABLE_FOLDER_NOT_GIT_IGNORED'}
    Add-Type -AssemblyName System.Windows.Forms;Add-Type -AssemblyName System.Drawing
    $form=[Windows.Forms.Form]::new();$form.Text='ArcIA - Archive portable protegee';$form.ClientSize=[Drawing.Size]::new(830,400);$form.StartPosition='CenterScreen';$form.TopMost=$true
    $label=[Windows.Forms.Label]::new();$label.Location=[Drawing.Point]::new(15,15);$label.Size=[Drawing.Size]::new(800,100)
    $label.Text=if($Action -eq 'Export'){'Archive complete dans secrets\local\arcia-private.arciap, exclue de Git. Tous les bundles DPAPI, cles SSH et fichiers references ; profils navigateur/caches exclus. Saisissez la cle de votre gestionnaire de mots de passe (au moins 16 caracteres), jamais dans le chat.'}elseif($ReplaceExisting){'Remplacement de l''ancien etat local ArcIA-Harness hors OneDrive. L''archive et le staging seront verifies avant de vider la cible ; aucune fusion avec les anciens secrets. Le dossier OneDrive est conserve. Aucun deploiement automatique.'}else{'Restauration sur ce PC dans le dossier local protege ArcIA-Harness. Les bundles seront rechiffres pour votre compte Windows et les chemins adaptes. Aucun deploiement automatique. Refus si un etat local existe deja.'}
    $form.Controls.Add($label)
    $boxes=@()
    for($i=0;$i -lt $(if($Action -eq 'Export'){2}else{1});$i++){
        $caption=[Windows.Forms.Label]::new();$caption.Text=if($i -eq 0){'Mot de passe de l''archive'}else{'Confirmation'};$caption.Location=[Drawing.Point]::new(15,(125+50*$i));$caption.Size=[Drawing.Size]::new(240,30);$form.Controls.Add($caption)
        $box=[Windows.Forms.TextBox]::new();$box.UseSystemPasswordChar=$true;$box.Location=[Drawing.Point]::new(260,(125+50*$i));$box.Size=[Drawing.Size]::new(550,30);$form.Controls.Add($box);$boxes+=,$box
    }
    $message=[Windows.Forms.Label]::new();$message.Location=[Drawing.Point]::new(15,240);$message.Size=[Drawing.Size]::new(800,85);$message.Text='Aucune valeur secrete ne sera affichee. La verification relit et controle chaque fichier de l''archive.';$form.Controls.Add($message)
    $button=[Windows.Forms.Button]::new();$button.Text=if($Action -eq 'Export'){'Creer et verifier l''archive portable'}else{'Restaurer et proteger pour ce PC'};$button.Location=[Drawing.Point]::new(350,345);$button.Size=[Drawing.Size]::new(460,35);$form.Controls.Add($button)
    $button.Add_Click({
        try{
            if($boxes[0].Text.Length -lt 16){$message.Text='Mot de passe d''au moins 16 caracteres requis.';return}
            if($Action -eq 'Export' -and $boxes[0].Text -cne $boxes[1].Text){$message.Text='Les deux saisies different.';return}
            $button.Enabled=$false;$message.Text='Archive et verification en cours. Patientez sans fermer cette fenetre...';$form.Refresh()
            $result=if($Action -eq 'Export'){Export-PortableState $localRoot $workspace $archive $boxes[0].Text}else{Import-PortableState $archive $localRoot $workspace $boxes[0].Text -ReplaceExisting:$ReplaceExisting}
            if($Action -eq 'Export'){
                [IO.File]::WriteAllText(($archive+'.sha256'),($result.archive_sha256+'  '+[IO.Path]::GetFileName($archive)+[Environment]::NewLine),[Text.UTF8Encoding]::new($false))
            }
            [IO.File]::WriteAllText((Join-Path $directory 'portable-status.json'),($result|ConvertTo-Json),[Text.Encoding]::UTF8)
            foreach($box in $boxes){$box.Clear()}
            $message.Text=if($Action -eq 'Export'){'Archive creee et relue integralement. Attendez sa synchronisation OneDrive. Sur le second PC : -Action Import -ReplaceExisting pour remplacer les anciens secrets locaux. Gardez la cle separement.'}else{'Etat restaure et protege pour ce compte Windows, chemins adaptes. Aucun deploiement lance.'};$form.Refresh()
        }catch{
            [IO.File]::WriteAllText((Join-Path $directory 'portable-status.json'),'{"status":"failed","code":"PORTABLE_OPERATION_FAILED"}')
            $message.Text='Operation interrompue : mot de passe, etat existant, fichier ou verification. Les originaux sont conserves.';$button.Enabled=$true
            # Diagnostics stay DPAPI-protected on this PC; never rendered by the model.
            if(Test-Path -LiteralPath $localRoot){Save-ProtectedBundle (Join-Path $localRoot ('portable-fault-'+[guid]::NewGuid().ToString('N')+'.dpapi')) ([string]$_|ConvertTo-Json -Compress)}
        }
    })
    $form.Add_Shown({[IO.File]::WriteAllText((Join-Path $directory 'portable-form-status.json'),'{"status":"visible","code":"PORTABLE_PASSWORD_FORM_SHOWN"}')})
    $null=$form.ShowDialog()
}catch{Write-Output 'PORTABLE_PROGRAM_INITIALIZATION_FAILED';exit 2}
