# Protected enrollment for the native Hermes Entra test; never prints field values.
[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'ProtectedState.ps1')
$entraStateRoot=Get-ArcIAStateRoot
$instance=(Read-ProtectedBundle (Join-Path $entraStateRoot 'instance.dpapi'))|ConvertFrom-Json
$operation=(Read-ProtectedBundle (Join-Path $entraStateRoot 'vmware-operation.dpapi'))|ConvertFrom-Json
if($instance.operation_id -ne $operation.id){throw 'ENTRA_TEST_OPERATION_SCOPE'}
$destination=Join-Path $entraStateRoot 'entra-test.dpapi'
$saved=$null
if(Test-Path -LiteralPath $destination){
    $saved=(Read-ProtectedBundle $destination)|ConvertFrom-Json
    if($saved.operation_id -ne $operation.id){throw 'ENTRA_TEST_ENROLLMENT_SCOPE'}
}
Add-Type -AssemblyName System.Windows.Forms
$form=[Windows.Forms.Form]::new();$form.Text='ArcIA - test Entra ID natif Hermes';$form.Width=950;$form.Height=590
$form.StartPosition='CenterScreen'
$fields=@{}
$definitions=@(
    @{key='tenant_id';label='ID du tenant Microsoft Entra';secret=$false},
    @{key='client_id';label='ID application (client), mono-tenant, plateforme Web';secret=$false},
    @{key='client_secret';label='Secret application (valeur), uniquement dans ce formulaire';secret=$true},
    @{key='owner_object_id';label='Object ID Entra du compte qui effectuera le test';secret=$false}
)
$row=0
foreach($definition in $definitions){
    $label=[Windows.Forms.Label]::new();$label.Text=$definition.label;$label.SetBounds(15,20+65*$row,405,42)
    $box=[Windows.Forms.TextBox]::new();$box.SetBounds(430,20+65*$row,480,28);$box.UseSystemPasswordChar=$definition.secret
    if($saved){$box.Text=[string]$saved.($definition.key)}
    $form.Controls.Add($label);$form.Controls.Add($box);$fields[$definition.key]=$box;$row++
}
$callback='https://'+$instance.config.network.public_hostname+'/entra-test/auth/callback'
$label=[Windows.Forms.Label]::new();$label.Text='URI de redirection a ajouter dans Entra : plateforme Web';$label.SetBounds(15,285,890,24)
$box=[Windows.Forms.TextBox]::new();$box.Text=$callback;$box.ReadOnly=$true;$box.SetBounds(15,315,740,28)
$copy=[Windows.Forms.Button]::new();$copy.Text='Copier URI';$copy.SetBounds(770,313,140,32)
$copy.Add_Click({[Windows.Forms.Clipboard]::SetText($callback)})
$form.Controls.Add($label);$form.Controls.Add($box);$form.Controls.Add($copy)
$note=[Windows.Forms.Label]::new();$note.Text='Ne pas saisir votre mot de passe Microsoft. Le test est limite au tenant et a l''Object ID ci-dessus. Keycloak reste actif. Les donnees sont chiffrees hors Git/OneDrive. Le callback doit etre autorise avant le test interactif.'
$note.SetBounds(15,365,890,75);$form.Controls.Add($note)
$message=[Windows.Forms.Label]::new();$message.SetBounds(15,445,890,40);$form.Controls.Add($message)
$save=[Windows.Forms.Button]::new();$save.Text='Enregistrer les parametres proteges';$save.SetBounds(420,495,490,35);$form.Controls.Add($save)
$save.Add_Click({
    try{
        $values=@{schema_version=1;operation_id=$operation.id}
        foreach($definition in $definitions){
            $value=$fields[$definition.key].Text.Trim()
            if(-not $value){$message.Text='Champ requis : '+$definition.label;return}
            if(-not $definition.secret){
                $parsed=[guid]::Empty
                if(-not [guid]::TryParse($value,[ref]$parsed) -or $parsed -eq [guid]::Empty){$message.Text='GUID valide requis : '+$definition.label;return}
                $value=$parsed.ToString()
            }
            $values[$definition.key]=$value
        }
        $temporary=Join-Path $entraStateRoot ('entra-test-'+[guid]::NewGuid().ToString('N')+'.dpapi')
        Save-ProtectedBundle $temporary ($values|ConvertTo-Json -Compress)
        if(Test-Path -LiteralPath $destination){[IO.File]::Replace($temporary,$destination,[NullString]::Value)}
        else{Move-Item -LiteralPath $temporary -Destination $destination}
        [IO.File]::WriteAllText((Join-Path $entraStateRoot 'entra-test-enrollment-status.json'),'{"status":"saved","code":"ENTRA_TEST_ENROLLED_PROTECTED","fields_present":true}',[Text.UTF8Encoding]::new($false))
        $values=$null;$form.Close()
    }catch{$message.Text='Enregistrement impossible. Ne recopiez aucune valeur dans le chat.'}
})
$form.Add_Shown({[IO.File]::WriteAllText((Join-Path $entraStateRoot 'entra-test-form-status.json'),'{"status":"visible","code":"ENTRA_TEST_PROTECTED_FORM_SHOWN"}',[Text.UTF8Encoding]::new($false))})
try{$null=$form.ShowDialog()}finally{$form.Dispose();$instance=$null;$operation=$null;$saved=$null;$fields=$null}
