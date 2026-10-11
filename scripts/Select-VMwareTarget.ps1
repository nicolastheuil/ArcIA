[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'ProtectedState.ps1')
$privateRoot = Join-Path $env:LOCALAPPDATA 'ArcIA-Harness'
$targetPath = Join-Path $privateRoot 'vmware-target.dpapi'
$draftPath = Join-Path $privateRoot 'vmware-target-draft.dpapi'
$statusPath = Join-Path $privateRoot 'vmware-target-status.json'
function Set-TargetStatus([string]$Status, [string]$Code) {
    [IO.File]::WriteAllText($statusPath, (@{status=$Status;code=$Code;deployed=$false}|ConvertTo-Json), [Text.Encoding]::UTF8)
}
try {
    Initialize-PrivateDirectory -Path $privateRoot
    $inventory = ((Read-ProtectedBundle -Path (Join-Path $privateRoot 'vmware-inventory.dpapi'))|ConvertFrom-Json).inventory
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    [Windows.Forms.Application]::EnableVisualStyles()
    $form = New-Object Windows.Forms.Form
    $form.Text = 'ArcIA - Placement et reseau des 3 VM'
    $form.ClientSize = New-Object Drawing.Size(840,710)
    $form.StartPosition = 'CenterScreen'; $form.TopMost=$true
    $form.FormBorderStyle='FixedDialog'; $form.MaximizeBox=$false
    $fields=@{}
    $definitions=@(
        @('cluster','Cluster ESXi','combo'), @('datastore','Datastore partage','combo'),
        @('network','Reseau / portgroup','combo'), @('folder','Dossier VM de destination','combo'),
        @('ip1','arcia-k3s-01 : IPv4 / prefixe (ex. 192.0.2.11/24)','text'),
        @('ip2','arcia-k3s-02 : IPv4 / prefixe','text'), @('ip3','arcia-k3s-03 : IPv4 / prefixe','text'),
        @('gateway','Passerelle IPv4','text'), @('dns','Serveurs DNS IPv4, separes par virgules','text'),
        @('ntp','Serveurs NTP (IP ou noms), separes par virgules','text'),
        @('ssh_user','Votre compte Linux personnel','text'), @('ssh_public_key','Fichier cle SSH publique (.pub)','text')
    )
    $row=0
    foreach ($definition in $definitions) {
        $label=New-Object Windows.Forms.Label
        $label.Text=$definition[1]; $label.Location=New-Object Drawing.Point(15,(15+45*$row))
        $label.Size=New-Object Drawing.Size(415,30); $form.Controls.Add($label)
        if ($definition[2] -eq 'combo') {
            $control=New-Object Windows.Forms.ComboBox; $control.DropDownStyle='DropDownList'
            $control.DisplayMember='path'
        } else { $control=New-Object Windows.Forms.TextBox }
        $control.Location=New-Object Drawing.Point(440,(12+45*$row)); $control.Size=New-Object Drawing.Size(380,25)
        $fields[$definition[0]]=$control; $form.Controls.Add($control); $row++
    }
    foreach ($item in @($inventory.clusters)) { $null=$fields.cluster.Items.Add($item) }
    foreach ($item in @($inventory.datastores|Where-Object accessible)) { $null=$fields.datastore.Items.Add($item) }
    foreach ($item in @($inventory.networks)) { $null=$fields.network.Items.Add($item) }
    foreach ($item in @($inventory.folders)) { $null=$fields.folder.Items.Add($item) }
    $fields.ssh_user.Text = $env:USERNAME.ToLower()
    $defaultPublic = Join-Path $env:USERPROFILE '.ssh\id_ed25519.pub'
    if (Test-Path -LiteralPath $defaultPublic) { $fields.ssh_public_key.Text = $defaultPublic }
    foreach ($key in @('cluster','datastore','network','folder')) {
        if ($fields[$key].Items.Count -eq 1) { $fields[$key].SelectedIndex=0 }
    }
    function Save-TargetDraft {
        $draft=@{}
        foreach ($key in $fields.Keys) {
            if ($key -in @('cluster','datastore','network','folder')) { $draft[$key]=$fields[$key].SelectedItem.id }
            else {$draft[$key]=$fields[$key].Text}
        }
        $temporary=Join-Path $privateRoot ('draft-'+[guid]::NewGuid().ToString('N')+'.dpapi')
        Save-ProtectedBundle -Path $temporary -Bundle ($draft|ConvertTo-Json)
        if (Test-Path -LiteralPath $draftPath) { [IO.File]::Replace($temporary,$draftPath,[NullString]::Value) }
        else { Move-Item -LiteralPath $temporary -Destination $draftPath }
    }
    if (Test-Path -LiteralPath $draftPath) {
        try {
            $draft=(Read-ProtectedBundle -Path $draftPath)|ConvertFrom-Json
            foreach ($key in $fields.Keys) {
                if ($key -in @('cluster','datastore','network','folder')) {
                    for ($i=0;$i -lt $fields[$key].Items.Count;$i++) {
                        if ($fields[$key].Items[$i].id -eq $draft.$key) { $fields[$key].SelectedIndex=$i }
                    }
                } elseif ($null -ne $draft.$key) {$fields[$key].Text=$draft.$key}
            }
        } catch {} finally {$draft=$null}
    }
    $draftTimer=New-Object Windows.Forms.Timer
    $draftTimer.Interval=600
    $draftTimer.Add_Tick({$draftTimer.Stop(); try {Save-TargetDraft} catch {}})
    foreach ($control in $fields.Values) {
        $control.Add_TextChanged({$draftTimer.Stop();$draftTimer.Start()})
    }
    $message=New-Object Windows.Forms.Label
    $message.Text='3 VM : 8 vCPU / 32 Gio RAM / 150 Gio disque chacune. IP stables libres requises. Sortie Debian HTTPS necessaire. Aucun secret dans ce formulaire ; utilisez une cle PUBLIQUE.'
    $message.Location=New-Object Drawing.Point(15,560); $message.Size=New-Object Drawing.Size(805,75)
    $form.Controls.Add($message)
    $button=New-Object Windows.Forms.Button
    $button.Text='Enregistrer les parametres de deploiement'; $button.Location=New-Object Drawing.Point(420,655)
    $button.Size=New-Object Drawing.Size(400,35); $form.Controls.Add($button)
    $button.Add_Click({
        try {
            Set-TargetStatus validating TARGET_SAVE_CLICKED
            Save-TargetDraft
            $message.Text='Validation et enregistrement en cours...'
            foreach ($key in @('cluster','datastore','network','folder')) {
                if (-not $fields[$key].SelectedItem) { $fields[$key].BackColor=[Drawing.Color]::MistyRose; throw 'MISSING_PLACEMENT' }
            }
            foreach ($key in @('ip1','ip2','ip3','gateway','dns','ntp','ssh_user','ssh_public_key')) {
                if (-not $fields[$key].Text.Trim()) { $fields[$key].BackColor=[Drawing.Color]::MistyRose; throw 'MISSING_NETWORK_OR_SSH' }
            }
            $fields.ssh_public_key.Text=$fields.ssh_public_key.Text.Trim().Trim('"')
            if ($fields.ssh_public_key.Text -notmatch '\.pub$' -or -not (Test-Path -LiteralPath $fields.ssh_public_key.Text)) { throw 'PUBLIC_KEY_FILE_REQUIRED' }
            $target=@{schema_version=1;cluster_id=$fields.cluster.SelectedItem.id;datastore_id=$fields.datastore.SelectedItem.id;
                network_id=$fields.network.SelectedItem.id;folder_id=$fields.folder.SelectedItem.id;
                addresses=@($fields.ip1.Text.Trim(),$fields.ip2.Text.Trim(),$fields.ip3.Text.Trim());gateway=$fields.gateway.Text.Trim();
                dns=@($fields.dns.Text.Split(',')|ForEach-Object {$_.Trim()});ntp=@($fields.ntp.Text.Split(',')|ForEach-Object {$_.Trim()});
                ssh_user=$fields.ssh_user.Text.Trim();ssh_public_key_path=$fields.ssh_public_key.Text.Trim()}
            $temporary=Join-Path $privateRoot ('target-'+[guid]::NewGuid().ToString('N')+'.dpapi')
            Save-ProtectedBundle -Path $temporary -Bundle ($target|ConvertTo-Json -Depth 8)
            if (Test-Path -LiteralPath $targetPath) { [IO.File]::Replace($temporary,$targetPath,[NullString]::Value) }
            else { Move-Item -LiteralPath $temporary -Destination $targetPath }
            Set-TargetStatus configured TARGET_PARAMETERS_SAVED
            $message.Text='Parametres enregistres chiffres. Validation des IP, du placement et des ressources avant creation. Aucune VM creee par ce formulaire.'
            $button.Enabled=$false
            $null=[Windows.Forms.MessageBox]::Show($form,'Parametres chiffres enregistres. La preparation des VM peut continuer.','ArcIA - Enregistrement confirme')
            $form.Close()
        } catch {
            $code=$_.Exception.Message
            if ($code -notin @('MISSING_PLACEMENT','MISSING_NETWORK_OR_SSH','PUBLIC_KEY_FILE_REQUIRED')) {$code='TARGET_SAVE_FAILED'}
            Set-TargetStatus blocked $code
            $message.Text='Selectionner cluster, datastore, reseau et dossier ; remplir les IP/prefixes, passerelle, DNS/NTP, compte et fichier de cle publique .pub.'
            $detail='Completer le champ signale en rose.'
            if ($code -eq 'PUBLIC_KEY_FILE_REQUIRED') {$detail='Le fichier de cle publique doit exister et se terminer par .pub. Coller son chemin complet, sans guillemets.'}
            if ($code -eq 'TARGET_SAVE_FAILED') {$detail='Erreur du programme local. Le brouillon chiffre conserve la saisie pour reprise.'}
            $null=[Windows.Forms.MessageBox]::Show($form,$detail,'ArcIA - Parametres non enregistres')
        } finally {$target=$null}
    })
    Set-TargetStatus awaiting_local_input TARGET_FORM_OPEN
    $null=$form.ShowDialog()
} catch {
    if (Test-Path -LiteralPath $privateRoot) { Set-TargetStatus blocked TARGET_FORM_FAILED }
    Write-Host 'VMWARE_TARGET_SELECTION_BLOCKED'
    exit 2
} finally {$inventory=$null}
