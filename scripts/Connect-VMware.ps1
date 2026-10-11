[CmdletBinding()]
param([switch]$CheckOnly, [switch]$PromptFingerprint)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'ProtectedState.ps1')
$stateDirectory = Join-Path $env:LOCALAPPDATA 'ArcIA-Harness'
$connectionPath = Join-Path $stateDirectory 'vmware.dpapi'
$inventoryPath = Join-Path $stateDirectory 'vmware-inventory.dpapi'
$statusPath = Join-Path $stateDirectory 'vmware-status.json'
$pythonPath = Join-Path $env:LOCALAPPDATA 'ArcIA-Validation\venv\Scripts\python.exe'
$safeCodes = @('TLS_TRUST_FAILED','TLS_HANDSHAKE_FAILED','VCENTER_DNS_FAILED','VCENTER_TIMEOUT',
    'VCENTER_NETWORK_FAILED','CA_FILE_UNREADABLE','SDK_RUNTIME_ERROR','VCENTER_AUTHENTICATION_FAILED',
    'VCENTER_PERMISSION_DENIED','VCENTER_CONNECTION_OR_INVENTORY_FAILED','CONNECTION_FIELDS',
    'SERVER_HOSTNAME_REQUIRED','PORT_INVALID','CREDENTIALS_REQUIRED','CA_REFERENCE_INVALID','VCENTER_REQUIRED',
    'TLS_FINGERPRINT_CHANGED','TLS_FINGERPRINT_INVALID','TLS_HANDSHAKE_REQUIRED')
$script:acceptedFingerprint = ''
$localMessages = @{
    TLS_TRUST_FAILED='Certificat non approuve ou nom incorrect. Indiquer la CA PEM fournie par votre administrateur.'
    TLS_HANDSHAKE_FAILED='Echec TLS. Verifier le port HTTPS et la configuration TLS du serveur.'
    VCENTER_DNS_FAILED='Nom vCenter introuvable. Verifier le DNS et la connexion VPN.'
    VCENTER_TIMEOUT='Connexion expiree. Verifier VPN, routage et pare-feu vers vCenter.'
    VCENTER_NETWORK_FAILED='Serveur inaccessible. Verifier adresse, port, VPN et pare-feu.'
    CA_FILE_UNREADABLE='Fichier CA PEM introuvable ou inaccessible.'
    SDK_RUNTIME_ERROR='Runtime VMware indisponible. Reparer les dependances locales.'
    VCENTER_AUTHENTICATION_FAILED='Authentification refusee. Verifier votre compte personnel et le mot de passe.'
    VCENTER_PERMISSION_DENIED='Droits insuffisants pour inventorier la cible avec ce compte.'
    SERVER_HOSTNAME_REQUIRED='Saisir uniquement le nom ou IP du serveur, sans https:// ni chemin.'
    VCENTER_REQUIRED='La cible est un hote ESXi direct. Indiquer le serveur vCenter.'
    TLS_FINGERPRINT_CHANGED='Certificat different de celui accepte. Connexion bloquee avant authentification.'
}

function Set-SafeVMwareStatus {
    param([string]$Status, [string]$Code, [int]$ClusterCount = 0, [int]$TemplateCount = 0, [int]$ExistingVMCount = 0,
          [int]$FailureLine = 0, [string]$FailureType = '')
    # Safe fixed fields only. No names, URLs, identity, paths, passwords or fault text.
    $value = @{status=$Status; code=$Code; cluster_count=$ClusterCount; template_count=$TemplateCount;
               existing_arcia_vm_count=$ExistingVMCount; deployed=$false; local_failure_line=$FailureLine}
    if ($FailureType -in @('MethodInvocationException','RuntimeException','ParameterBindingException',
        'PSArgumentException','PropertyNotFoundException','PSInvalidOperationException')) { $value.local_failure_type=$FailureType }
    [IO.File]::WriteAllText($statusPath, ($value | ConvertTo-Json), [Text.Encoding]::UTF8)
}

function Invoke-PrivateDiscovery {
    param([string]$Bundle, [switch]$CertificateOnly)
    $start = New-Object Diagnostics.ProcessStartInfo
    $start.FileName = $pythonPath
    $start.Arguments = '"' + (Join-Path $PSScriptRoot 'vmware_inventory.py') + '"'
    if ($CertificateOnly) { $start.Arguments += ' --certificate' }
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardInput = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $start.StandardInputEncoding = New-Object Text.UTF8Encoding($false)
    $start.StandardOutputEncoding = [Text.Encoding]::UTF8
    $process = New-Object Diagnostics.Process
    $process.StartInfo = $start
    $null = $process.Start()
    $process.StandardInput.Write($Bundle)
    $process.StandardInput.Close()
    $outputTask = $process.StandardOutput.ReadToEndAsync()
    $errorTask = $process.StandardError.ReadToEndAsync()
    if (-not $process.WaitForExit(90000)) { $process.Kill(); throw 'DISCOVERY_TIMEOUT' }
    $privateResponse = $outputTask.GetAwaiter().GetResult()
    $null = $errorTask.GetAwaiter().GetResult()
    $result = $privateResponse | ConvertFrom-Json
    if ($CertificateOnly -and $process.ExitCode -eq 0 -and $result.status -eq 'certificate_pending') {
        $process.Dispose()
        return $result
    }
    if ($process.ExitCode -ne 0 -or $result.status -ne 'connected') {
        $code = 'VCENTER_CONNECTION_OR_INVENTORY_FAILED'
        if ($result.code -in $safeCodes) { $code = $result.code }
        Set-SafeVMwareStatus -Status blocked -Code $code
        $process.Dispose()
        throw $code
    }
    $temporary = Join-Path $stateDirectory ('inventory-' + [guid]::NewGuid().ToString('N') + '.dpapi')
    Save-ProtectedBundle -Path $temporary -Bundle $privateResponse
    if (Test-Path -LiteralPath $inventoryPath) { [IO.File]::Replace($temporary, $inventoryPath, [NullString]::Value) }
    else { Move-Item -LiteralPath $temporary -Destination $inventoryPath }
    Set-SafeVMwareStatus -Status connected -Code INVENTORY_READY -ClusterCount @($result.inventory.clusters).Count -TemplateCount @($result.inventory.templates).Count -ExistingVMCount @($result.inventory.arcia_vms).Count
    $privateResponse = $null; $result = $null
    $process.Dispose()
}

$setupStage = 'PRIVATE_DIRECTORY'
try {
    Initialize-PrivateDirectory -Path $stateDirectory
    $setupStage = 'SDK_RUNTIME'
    if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'SDK_RUNTIME_MISSING' }
    if ($CheckOnly) {
        $setupStage = 'READ_CONNECTION'
        $bundle = Read-ProtectedBundle -Path $connectionPath
        $setupStage = 'DISCOVERY'
        Invoke-PrivateDiscovery -Bundle $bundle
        Write-Host 'VCENTER_INVENTORY_READY; NO_VM_CREATED'
        exit 0
    }
    $setupStage = 'WINDOWS_FORMS'
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    [Windows.Forms.Application]::EnableVisualStyles()
    $form = New-Object Windows.Forms.Form
    $form.Text = 'ArcIA - Connexion VMware protegee'
    $form.ClientSize = New-Object Drawing.Size(660, 355)
    $form.StartPosition = 'CenterScreen'
    $form.FormBorderStyle = 'FixedDialog'
    $form.MaximizeBox = $false
    $form.TopMost = $true
    $labels = @('vCenter (FQDN ou IP, sans https://)', 'Port HTTPS', 'Votre identite vCenter', 'Mot de passe', 'Certificat CA PEM (facultatif si deja approuve)')
    $fields = @()
    for ($index = 0; $index -lt $labels.Count; $index++) {
        $label = New-Object Windows.Forms.Label
        $label.Text = $labels[$index]
        $label.Location = New-Object Drawing.Point(15, (18 + 45 * $index))
        $label.Size = New-Object Drawing.Size(310, 25)
        $form.Controls.Add($label)
        $field = New-Object Windows.Forms.TextBox
        $field.Location = New-Object Drawing.Point(330, (15 + 45 * $index))
        $field.Size = New-Object Drawing.Size(310, 25)
        $form.Controls.Add($field)
        $fields += $field
    }
    $fields[1].Text = '443'
    $fields[3].UseSystemPasswordChar = $true
    if (Test-Path -LiteralPath $connectionPath) {
        try {
            $stored = (Read-ProtectedBundle -Path $connectionPath) | ConvertFrom-Json
            $fields[0].Text = $stored.server; $fields[1].Text = [string]$stored.port
            $fields[2].Text = $stored.username; $fields[3].Text = $stored.password
            $fields[4].Text = $stored.ca_file
            if ($stored.certificate_sha256) { $script:acceptedFingerprint = $stored.certificate_sha256 }
        } catch { } finally { $stored = $null }
    }
    function Get-LocalConnection {
        $value = @{server=$fields[0].Text.Trim();port=[int]$fields[1].Text;username=$fields[2].Text;
                   password=$fields[3].Text;ca_file=$fields[4].Text.Trim()}
        if ($script:acceptedFingerprint) { $value.certificate_sha256 = $script:acceptedFingerprint }
        return $value
    }
    $fields[0].Add_TextChanged({ $script:acceptedFingerprint = '' })
    $fields[1].Add_TextChanged({ $script:acceptedFingerprint = '' })
    $message = New-Object Windows.Forms.Label
    $message.Text = 'Saisie locale uniquement. TLS verifie. Inventaire en lecture seule.'
    $message.Location = New-Object Drawing.Point(15, 250)
    $message.Size = New-Object Drawing.Size(630, 45)
    $form.Controls.Add($message)
    $connectButton = New-Object Windows.Forms.Button
    $connectButton.Text = 'Connecter et inventorier'
    $connectButton.Location = New-Object Drawing.Point(380, 310)
    $connectButton.Size = New-Object Drawing.Size(260, 30)
    $form.Controls.Add($connectButton)
    $trustButton = New-Object Windows.Forms.Button
    $trustButton.Text = 'Afficher / accepter empreinte SHA-256'
    $trustButton.Location = New-Object Drawing.Point(15, 310)
    $trustButton.Size = New-Object Drawing.Size(350, 30)
    $form.Controls.Add($trustButton)
    $trustButton.Add_Click({
        $trustButton.Enabled = $false
        try {
            $connection = Get-LocalConnection
            $certificate = Invoke-PrivateDiscovery -Bundle ($connection | ConvertTo-Json) -CertificateOnly
            if ($certificate.sha256 -notmatch '^[a-f0-9]{64}$') { throw 'TLS_FINGERPRINT_INVALID' }
            $display = (($certificate.sha256.ToUpper() -split '(.{2})' | Where-Object { $_ }) -join ':')
            $prompt = "vCenter : " + $connection.server + "`r`n`r`nSHA-256 :`r`n" + $display +
                "`r`n`r`nAccepter ce certificat pour cette cible ? Comparez l'empreinte avec celle du vCenter attendue. Tout changement bloquera la connexion."
            Set-SafeVMwareStatus -Status awaiting_local_input -Code TLS_FINGERPRINT_PROMPT_OPEN
            $answer = [Windows.Forms.MessageBox]::Show($form, $prompt, 'ArcIA - Accepter le certificat vCenter',
                [Windows.Forms.MessageBoxButtons]::YesNo, [Windows.Forms.MessageBoxIcon]::Question,
                [Windows.Forms.MessageBoxDefaultButton]::Button2)
            if ($answer -eq [Windows.Forms.DialogResult]::Yes) {
                $script:acceptedFingerprint = $certificate.sha256
                $fields[4].Clear()
                $message.Text = 'Empreinte acceptee localement. Cliquer sur Connecter et inventorier.'
                Set-SafeVMwareStatus -Status awaiting_local_input -Code TLS_FINGERPRINT_ACCEPTED
                if ($PromptFingerprint) { $connectButton.PerformClick() }
            }
        } catch {
            $code = $_.Exception.Message
            $message.Text = 'Impossible de lire le certificat. Verifier serveur, port et reseau.'
            if ($localMessages.ContainsKey($code)) { $message.Text = $localMessages[$code] }
        } finally { $certificate=$null; $connection=$null; $trustButton.Enabled=$true }
    })
    $connectButton.Add_Click({
        $connectButton.Enabled = $false
        $message.Text = 'Connexion et inventaire en cours...'
        [Windows.Forms.Application]::DoEvents()
        try {
            $connection = Get-LocalConnection
            $bundle = $connection | ConvertTo-Json
            # Persist locally before discovery, so a failed connection can be
            # re-checked without asking the user to reveal or retype a secret.
            $temporary = Join-Path $stateDirectory ('connection-' + [guid]::NewGuid().ToString('N') + '.dpapi')
            Save-ProtectedBundle -Path $temporary -Bundle $bundle
            if (Test-Path -LiteralPath $connectionPath) { [IO.File]::Replace($temporary, $connectionPath, [NullString]::Value) }
            else { Move-Item -LiteralPath $temporary -Destination $connectionPath }
            Invoke-PrivateDiscovery -Bundle $bundle
            $fields[3].Clear()
            $message.Text = 'Connexion validee. Inventaire chiffre enregistre. Aucune VM creee.'
            $connectButton.Text = 'Inventaire termine'
            $connectButton.Enabled = $false
        } catch {
            $code = $_.Exception.Message
            if ($code -notin $safeCodes) {
                Set-SafeVMwareStatus -Status blocked -Code LOCAL_PROGRAM_FAILED -FailureLine $_.InvocationInfo.ScriptLineNumber -FailureType $_.Exception.GetType().Name
            }
            $message.Text = 'Connexion refusee. Verifier les champs et les droits vCenter.'
            if ($localMessages.ContainsKey($code)) { $message.Text = $localMessages[$code] }
            $connectButton.Enabled = $true
        } finally { $bundle=$null; $connection=$null }
    })
    $setupStage = 'SHOW_FORM'
    $form.Add_Shown({ if ($PromptFingerprint) { $trustButton.PerformClick() } })
    Set-SafeVMwareStatus -Status awaiting_local_input -Code VCENTER_FORM_OPEN
    $null = $form.ShowDialog()
} catch {
    if (Test-Path -LiteralPath $stateDirectory) {
        if ($_.Exception.Message -notin $safeCodes) {
            Set-SafeVMwareStatus -Status blocked -Code ('LOCAL_VMWARE_SETUP_FAILED_' + $setupStage) -FailureLine $_.InvocationInfo.ScriptLineNumber -FailureType $_.Exception.GetType().Name
        }
    }
    Write-Host 'VMWARE_CONNECTION_BLOCKED'
    exit 2
} finally { $bundle = $null }
