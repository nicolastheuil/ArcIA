# Interactive enrollment only. Never expose these fields through model tools.
[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'ProtectedState.ps1')
$root=Join-Path $env:LOCALAPPDATA 'ArcIA-Harness'
try{
    Initialize-PrivateDirectory $root
    $instance=(Read-ProtectedBundle (Join-Path $root 'instance.dpapi'))|ConvertFrom-Json
    $definitions=@(
        @{tab='Entra';key='tenant_id';label='Tenant Entra ID';kind='guid'},
        @{tab='Entra';key='oidc_client_id';label='Application Entra Web / OIDC (client ID)';kind='guid'},
        @{tab='Entra';key='oidc_client_secret';label='Secret application OIDC (valeur, saisie locale)';secret=$true},
        @{tab='Entra';key='admin_object_id';label='Votre object ID utilisateur Entra (administration)';kind='guid'},
        @{tab='Entra';key='second_test_object_id';label='Object ID du second consultant de qualification';kind='guid'},
        @{tab='Teams';key='teams_app_id';label='Application/bot Teams existant (client ID)';kind='guid'},
        @{tab='Teams';key='teams_client_secret';label='Secret application/bot Teams';secret=$true},
        @{tab='Passbolt';key='passbolt_url';label='URL HTTPS du Passbolt Pro existant';kind='https'},
        @{tab='Passbolt';key='passbolt_service_email';label='Identite technique Passbolt plateforme existante'},
        @{tab='Passbolt';key='passbolt_private_key_path';label='Chemin local de sa cle GPG privee (.asc)';kind='file'},
        @{tab='Passbolt';key='passbolt_passphrase';label='Passphrase GPG (saisie locale)';secret=$true},
        @{tab='Passbolt';key='passbolt_server_key_sha256';label='Empreinte SHA256 cle serveur Passbolt, si connue'},
        @{tab='Recuperation';key='recovery_recipients';label='Destinataires age publics des ingenieurs (separes par espaces)'},
        @{tab='Recuperation';key='recovery_resource_id';label='UUID entree Passbolt de recuperation, si creee';kind='guid'},
        @{tab='IA';key='openrouter_api_key';label='Cle OpenRouter (gratuits autorises / repli prepayee)';secret=$true},
        @{tab='IA';key='context7_api_key';label='Cle Context7, si requise pour votre compte';secret=$true},
        @{tab='TLS';key='tls_certificate_path';label='Certificat HTTPS et chaine (.pem) ou certificat (.pfx)';kind='file'},
        @{tab='TLS';key='tls_private_key_path';label='Cle privee TLS (.pem), inutile si PFX complet';kind='file'},
        @{tab='TLS';key='tls_pfx_password';label='Mot de passe du PFX, si applicable';secret=$true}
    )
    $saved=$null;$destination=Join-Path $root 'integrations.dpapi'
    if(Test-Path -LiteralPath $destination){$saved=(Read-ProtectedBundle $destination)|ConvertFrom-Json;if($saved.operation_id -ne $instance.operation_id){throw 'INTEGRATIONS_OWNER_MISMATCH'}}
    Add-Type -AssemblyName System.Windows.Forms;Add-Type -AssemblyName System.Drawing
    $form=New-Object Windows.Forms.Form;$form.Text='ArcIA - Integrations protegees (saisie unique)'
    $form.ClientSize=New-Object Drawing.Size(1050,720);$form.StartPosition='CenterScreen';$form.TopMost=$true
    $tabs=New-Object Windows.Forms.TabControl;$tabs.Location=New-Object Drawing.Point(15,15);$tabs.Size=New-Object Drawing.Size(1020,550);$form.Controls.Add($tabs)
    $fields=@{}
    foreach($name in @('Entra','Teams','Passbolt','Recuperation','IA','TLS')){
        $page=New-Object Windows.Forms.TabPage;$page.Text=$name;$page.AutoScroll=$true;$null=$tabs.TabPages.Add($page)
        $row=0
        foreach($definition in $definitions|Where-Object tab -eq $name){
            $label=New-Object Windows.Forms.Label;$label.Text=$definition.label;$label.Location=New-Object Drawing.Point(12,(18+65*$row));$label.Size=New-Object Drawing.Size(460,45);$page.Controls.Add($label)
            $box=New-Object Windows.Forms.TextBox;$box.Location=New-Object Drawing.Point(480,(18+65*$row));$box.Size=New-Object Drawing.Size(510,30)
            $box.UseSystemPasswordChar=[bool]$definition.secret
            if($saved){$box.Text=[string]$saved.values.($definition.key)}
            $page.Controls.Add($box);$fields[$definition.key]=$box;$row++
        }
        $note=New-Object Windows.Forms.Label;$note.Location=New-Object Drawing.Point(12,(35+65*$row));$note.Size=New-Object Drawing.Size(975,120)
        $note.Text=switch($name){
            Entra {'Application mono-tenant, plateforme Web. Redirection OIDC : https://'+$instance.config.network.public_hostname+'/auth/callback. Ne pas saisir votre mot de passe Microsoft. Les app roles et habilitations seront verifies cote serveur.'}
            Teams {'Endpoint du bot a configurer : https://'+$instance.config.network.public_hostname+'/api/teams/messages. Le bot doit appartenir au meme tenant. Aucun message ne sera envoye a un tiers sans autorisation explicite de test.'}
            Passbolt {'Conserver le Passbolt existant et ses partages. Identite technique plateforme dediee ; les coffres personnels seront enroles individuellement. Aucun mot de passe maitre personnel a fournir.'}
            Recuperation {'Recuperation par au moins deux ingenieurs ; cles privees hors GitHub. Les destinataires age sont publics. Le parcours Passbolt/offline et le second ingenieur restent a verifier avant release.'}
            IA {'Les cles restent dans les services internes, jamais dans Hermes. Fournisseurs gratuits qualifies seulement ; depense payante desactivee initialement. Telemetrie des outils de build desactivee.'}
            TLS {'Domaine : '+$instance.config.network.public_hostname+'. Certificat valide et cle correspondante requis pour les acces externes et Teams. NAT 443 uniquement vers la VIP HTTPS ; aucune publication API Kubernetes. Ne pas placer de cle dans OneDrive/Git.'}
        };$page.Controls.Add($note)
    }
    $message=New-Object Windows.Forms.Label;$message.Text='Les champs peuvent etre enregistres progressivement. Le programme chiffre les valeurs hors OneDrive/Git. Aucun champ secret dans le chat.'
    $message.Location=New-Object Drawing.Point(15,580);$message.Size=New-Object Drawing.Size(1020,65);$form.Controls.Add($message)
    $save=New-Object Windows.Forms.Button;$save.Text='Enregistrer les integrations sous chiffrement';$save.Location=New-Object Drawing.Point(515,665);$save.Size=New-Object Drawing.Size(520,35);$form.Controls.Add($save)
    $save.Add_Click({
        try{
            $values=@{}
            foreach($definition in $definitions){
                $value=$fields[$definition.key].Text
                if(-not $definition.secret){$value=$value.Trim()}
                if($value -and $definition.kind -eq 'guid'){$parsed=[guid]::Empty;if(-not [guid]::TryParse($value,[ref]$parsed) -or $parsed -eq [guid]::Empty){$message.Text='GUID valide requis : '+$definition.label;return}}
                if($value -and $definition.kind -eq 'https'){$uri=$null;if(-not [Uri]::TryCreate($value,[UriKind]::Absolute,[ref]$uri) -or $uri.Scheme -ne 'https' -or $uri.UserInfo -or $uri.Fragment){$message.Text='URL HTTPS sans identifiants requise pour Passbolt.';return}}
                if($value -and $definition.kind -eq 'file' -and -not (Test-Path -LiteralPath $value -PathType Leaf)){$message.Text='Fichier local introuvable : '+$definition.label;return}
                $values[$definition.key]=$value
            }
            $bundle=@{schema_version=1;operation_id=$instance.operation_id;values=$values;paid_llm_enabled=$false;external_messages_authorized=$false}
            $temporary=Join-Path $root ('integrations-'+[guid]::NewGuid().ToString('N')+'.dpapi')
            Save-ProtectedBundle $temporary ($bundle|ConvertTo-Json -Depth 12 -Compress)
            if(Test-Path -LiteralPath $destination){[IO.File]::Replace($temporary,$destination,[NullString]::Value)}else{Move-Item -LiteralPath $temporary -Destination $destination}
            $safe=@{status='saved';code='INTEGRATIONS_SAVED_PROTECTED';identity_fields_present=[bool]($values.tenant_id -and $values.oidc_client_id -and $values.oidc_client_secret -and $values.admin_object_id);teams_fields_present=[bool]($values.teams_app_id -and $values.teams_client_secret);passbolt_fields_present=[bool]($values.passbolt_url -and $values.passbolt_service_email -and $values.passbolt_private_key_path);tls_fields_present=[bool]$values.tls_certificate_path;openrouter_key_present=[bool]$values.openrouter_api_key;qualified=$false}
            [IO.File]::WriteAllText((Join-Path $root 'integrations-status.json'),($safe|ConvertTo-Json),[Text.Encoding]::UTF8)
            $message.Text='Enregistrement confirme. Les valeurs sont chiffrees. Les champs manquants ne sont pas consideres qualifies.';$form.Refresh()
            $values=$null;$bundle=$null
        }catch{$message.Text='Enregistrement local impossible. Aucun secret a recopier dans le chat.'}
    })
    $form.Add_Shown({[IO.File]::WriteAllText((Join-Path $root 'integrations-form-status.json'),'{"status":"visible","code":"INTEGRATIONS_PROTECTED_FORM_SHOWN"}')})
    $null=$form.ShowDialog()
}catch{Write-Output 'PROTECTED_INTEGRATIONS_FORM_FAILED';exit 2}
finally{$instance=$null;$saved=$null;$fields=$null}
