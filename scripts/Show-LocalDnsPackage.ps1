# Private configuration stays in the local UI; never capture its content in tools.
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'ProtectedState.ps1')
try{
    $root=Join-Path $env:LOCALAPPDATA 'ArcIA-Harness'
    $reference=Get-ChildItem -LiteralPath $root -Filter 'dns-local-reference-*.dpapi'|Sort-Object LastWriteTime -Descending|Select-Object -First 1
    $package=(Read-ProtectedBundle $reference.FullName)|ConvertFrom-Json
    $operation=(Read-ProtectedBundle (Join-Path $root 'vmware-operation.dpapi'))|ConvertFrom-Json
    $directory=[IO.Path]::GetFullPath($package.directory)
    if($package.operation_id -ne $operation.id -or -not $directory.StartsWith(([IO.Path]::GetFullPath($root).TrimEnd('\')+'\'),[StringComparison]::OrdinalIgnoreCase)){throw 'DNS_PACKAGE_SCOPE_MISMATCH'}
    # Codex MSIX may virtualize LocalAppData. Show a physical path usable by Explorer.
    $physical=& (Join-Path $env:LOCALAPPDATA 'ArcIA-Validation/venv/Scripts/python.exe') -c 'import pathlib,sys; print(pathlib.Path(sys.argv[1]).resolve(strict=True))' $directory
    if($LASTEXITCODE -ne 0 -or -not [IO.Path]::IsPathRooted($physical)){throw 'DNS_PACKAGE_PHYSICAL_PATH_FAILED'}
    $directory=$physical.Trim()
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    $form=New-Object Windows.Forms.Form
    $form.Text='ArcIA - Dossier DNS local a copier';$form.StartPosition='CenterScreen';$form.TopMost=$true
    $form.ClientSize=New-Object Drawing.Size(1000,650)
    $label=New-Object Windows.Forms.Label;$label.Text='Copiez ce dossier complet sur le serveur DNS designe (aucun mot de passe dans ce dossier).'
    $label.Location=New-Object Drawing.Point(15,15);$label.Size=New-Object Drawing.Size(970,30);$form.Controls.Add($label)
    $pathBox=New-Object Windows.Forms.TextBox;$pathBox.ReadOnly=$true;$pathBox.Text=$directory
    $pathBox.Location=New-Object Drawing.Point(15,55);$pathBox.Size=New-Object Drawing.Size(970,30);$form.Controls.Add($pathBox)
    $box=New-Object Windows.Forms.TextBox;$box.Multiline=$true;$box.ReadOnly=$true;$box.ScrollBars='Vertical'
    $box.Text=Get-Content -LiteralPath (Join-Path $directory 'LIRE-MOI.txt') -Raw
    $box.Location=New-Object Drawing.Point(15,105);$box.Size=New-Object Drawing.Size(970,450);$form.Controls.Add($box)
    $copy=New-Object Windows.Forms.Button;$copy.Text='Copier le chemin du dossier'
    $copy.Location=New-Object Drawing.Point(15,590);$copy.Size=New-Object Drawing.Size(400,35)
    $copy.Add_Click({[Windows.Forms.Clipboard]::SetText($directory);$copy.Text='Chemin copie : collez-le dans l''Explorateur'});$form.Controls.Add($copy)
    $close=New-Object Windows.Forms.Button;$close.Text='Fermer';$close.Location=New-Object Drawing.Point(800,590);$close.Size=New-Object Drawing.Size(185,35)
    $close.Add_Click({$form.Close()});$form.Controls.Add($close)
    $form.Add_Shown({[IO.File]::WriteAllText((Join-Path $root 'dns-package-view-status.json'),'{"status":"visible","code":"LOCAL_DNS_PACKAGE_WINDOW_SHOWN"}')})
    $null=$form.ShowDialog()
}catch{Write-Output 'LOCAL_DNS_PACKAGE_VIEW_FAILED';exit 2}
