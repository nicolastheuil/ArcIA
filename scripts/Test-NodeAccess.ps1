[CmdletBinding()]
param([switch]$DiscoverOnly, [switch]$ValidateOnly, [switch]$PublishHostKeys, [switch]$StatusOnly, [switch]$RepairDisconnectedSeed, [switch]$CollectHostKeys)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'ProtectedState.ps1')
$privateRoot=Join-Path $env:LOCALAPPDATA 'ArcIA-Harness'
$statusPath=Join-Path $privateRoot 'ssh-preflight-status.json'
$lockStream=$null
$stage='INITIALIZE'
function Save-PrivateResult {
    param([string]$Name,[object]$Value)
    $temporary=Join-Path $privateRoot ('ssh-'+[guid]::NewGuid().ToString('N')+'.dpapi')
    Save-ProtectedBundle -Path $temporary -Bundle ($Value|ConvertTo-Json -Depth 16 -Compress)
    $destination=Join-Path $privateRoot $Name
    if(Test-Path -LiteralPath $destination){[IO.File]::Replace($temporary,$destination,[NullString]::Value)}
    else {Move-Item -LiteralPath $temporary -Destination $destination}
}
function Set-SafeStatus {
    param([string]$Status,[string]$Code,[int]$Discovered=0,[int]$Verified=0,[object]$Preflight=$null)
    $safe=@{status=$Status;code=$Code;discovered_count=$Discovered;verified_count=$Verified;k3s_installed=$false}
    if($null -ne $Preflight){
        $safe.passed=[bool]$Preflight.passed
        $safe.machine_id_and_uuid_unique=[bool]$Preflight.machine_id_and_uuid_unique
        $safe.nodes=@($Preflight.nodes)
        $safe.host_keys_preserved=[bool]$Preflight.host_keys_preserved
    }
    [IO.File]::WriteAllText($statusPath,($safe|ConvertTo-Json -Depth 8),[Text.Encoding]::UTF8)
}
function Invoke-Worker {
    param([object]$Payload,[switch]$Discovery,[switch]$Publication,[switch]$PublicationStatus)
    $start=New-Object Diagnostics.ProcessStartInfo
    $start.FileName=Join-Path $env:LOCALAPPDATA 'ArcIA-Validation\venv\Scripts\python.exe'
    $start.Arguments='"'+(Join-Path $PSScriptRoot 'ssh_vmware_preflight.py')+'"'
    if($Discovery){$start.Arguments+=' --discover'}
    if($Publication){$start.Arguments+=' --publish'}
    if($PublicationStatus){$start.Arguments+=' --status'}
    $start.UseShellExecute=$false;$start.CreateNoWindow=$true
    $start.RedirectStandardInput=$true;$start.RedirectStandardOutput=$true;$start.RedirectStandardError=$true
    if($PSVersionTable.PSEdition -eq 'Core'){$start.StandardInputEncoding=New-Object Text.UTF8Encoding($false)}
    $start.StandardOutputEncoding=[Text.Encoding]::UTF8
    $process=New-Object Diagnostics.Process;$process.StartInfo=$start
    try {
        $null=$process.Start()
        $process.StandardInput.Write(($Payload|ConvertTo-Json -Depth 16 -Compress));$process.StandardInput.Close()
        $output=$process.StandardOutput.ReadToEndAsync();$errors=$process.StandardError.ReadToEndAsync()
        if(-not $process.WaitForExit(700000)){$process.Kill();throw 'WORKER_TIMEOUT'}
        $result=$output.GetAwaiter().GetResult()|ConvertFrom-Json
        $null=$errors.GetAwaiter().GetResult()
        return $result
    } finally {$process.Dispose()}
}
function Get-ConsoleText {
    param([string]$EncodedImage)
    # Local Windows OCR only. Pixels and recognized inventory never leave this process.
    Add-Type -AssemblyName System.Runtime.WindowsRuntime
    $null=[Windows.Storage.Streams.InMemoryRandomAccessStream,Windows.Storage.Streams,ContentType=WindowsRuntime]
    $null=[Windows.Graphics.Imaging.BitmapDecoder,Windows.Graphics.Imaging,ContentType=WindowsRuntime]
    $null=[Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime]
    $null=[Windows.Media.Ocr.OcrResult,Windows.Foundation,ContentType=WindowsRuntime]
    $null=[Windows.Graphics.Imaging.SoftwareBitmap,Windows.Graphics.Imaging,ContentType=WindowsRuntime]
    $stream=New-Object Windows.Storage.Streams.InMemoryRandomAccessStream
    $writer=New-Object Windows.Storage.Streams.DataWriter($stream)
    try {
        $writer.WriteBytes([Convert]::FromBase64String($EncodedImage))
        $store=[System.WindowsRuntimeSystemExtensions]::AsTask($writer.StoreAsync())
        $store.Wait();$null=$writer.DetachStream();$stream.Seek(0)
        $decoder=Wait-WinRT ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
        $bitmap=Wait-WinRT ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
        try {
            $engine=[Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
            if($null -eq $engine){throw 'OCR_UNAVAILABLE'}
            $result=Wait-WinRT ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
            return $result.Text
        } finally {$bitmap.Dispose()}
    } finally {$writer.Dispose();$stream.Dispose()}
}
function Wait-WinRT {
    param($Operation,[Type]$ResultType)
    $method=[System.WindowsRuntimeSystemExtensions].GetMethods()|Where-Object {
        $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 -and
        $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
    }|Select-Object -First 1
    $task=$method.MakeGenericMethod($ResultType).Invoke($null,@($Operation))
    $task.Wait();return $task.Result
}
try {
    Initialize-PrivateDirectory -Path $privateRoot
    if(-not $StatusOnly){$lockStream=[IO.File]::Open((Join-Path $privateRoot 'ssh-preflight.lock'),[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::Write,[IO.FileShare]::None)}
    $stage='READ_PROTECTED_TARGET'
    $target=(Read-ProtectedBundle -Path (Join-Path $privateRoot 'vmware-target.dpapi'))|ConvertFrom-Json
    $operation=(Read-ProtectedBundle -Path (Join-Path $privateRoot 'vmware-operation.dpapi'))|ConvertFrom-Json
    $payload=@{target=$target;operation_id=$operation.id;private_root=$privateRoot}
    if($StatusOnly){
        $journalPath=Join-Path $privateRoot 'ssh-publication-repair.dpapi'
        if(-not (Test-Path -LiteralPath $journalPath)){$journalPath=Join-Path $privateRoot 'ssh-publication.dpapi'}
        $journal=(Read-ProtectedBundle -Path $journalPath)|ConvertFrom-Json
        $payload.challenges=$journal.challenges
        $payload.connection=(Read-ProtectedBundle -Path (Join-Path $privateRoot 'vmware.dpapi'))|ConvertFrom-Json
        $result=Invoke-Worker -Payload $payload -PublicationStatus
        [IO.File]::WriteAllText((Join-Path $privateRoot 'ssh-publication-status.json'),($result|ConvertTo-Json),[Text.Encoding]::UTF8)
        exit 0
    }
    if($PublishHostKeys -or $CollectHostKeys){
        $stage='PUBLISH_HOST_KEYS'
        $journalPath=Join-Path $privateRoot 'ssh-publication.dpapi'
        $repairPath=Join-Path $privateRoot 'ssh-publication-repair.dpapi'
        if(Test-Path -LiteralPath $repairPath){$journalPath=$repairPath}
        if($RepairDisconnectedSeed -and -not (Test-Path -LiteralPath $repairPath)){
            $previous=(Read-ProtectedBundle -Path (Join-Path $privateRoot 'ssh-publication-result.dpapi'))|ConvertFrom-Json
            $observed=Get-Content -LiteralPath (Join-Path $privateRoot 'ssh-publication-status.json') -Raw|ConvertFrom-Json
            if($previous.code -ne 'HOST_KEY_PUBLICATION_PENDING_NO_REPLAY' -or $observed.owned_count -ne 3 -or
                $observed.tools_running_count -ne 3 -or $observed.updated_seed_count -ne 0 -or $observed.pending_question_count -ne 0){throw 'SEED_REPAIR_PRECONDITION_FAILED'}
            $journalPath=Join-Path $privateRoot 'ssh-publication-repair.dpapi'
        }
        if($CollectHostKeys){
            $deployment=(Read-ProtectedBundle -Path (Join-Path $privateRoot 'vmware-deployment.dpapi'))|ConvertFrom-Json
            $challenges=@{}
            foreach($record in $deployment.created){$challenges[$record.name]=$record.host_key_challenge}
            $payload.challenges=$challenges
            $payload.read_only=$true
        } elseif(Test-Path -LiteralPath $journalPath){
            $journal=(Read-ProtectedBundle -Path $journalPath)|ConvertFrom-Json
            if($journal.operation_id -ne $operation.id){throw 'OPERATION_SCOPE_MISMATCH'}
            $payload.challenges=$journal.challenges
            $payload.read_only=$true
        } else {
            $challenges=@{}
            foreach($name in @('arcia-k3s-01','arcia-k3s-02','arcia-k3s-03')){$challenges[$name]=[guid]::NewGuid().ToString()}
            $journal=@{operation_id=$operation.id;status='dispatch_recorded';challenges=$challenges}
            Save-PrivateResult ([IO.Path]::GetFileName($journalPath)) $journal
            $payload.challenges=$challenges
            $payload.read_only=$false
        }
        $payload.connection=(Read-ProtectedBundle -Path (Join-Path $privateRoot 'vmware.dpapi'))|ConvertFrom-Json
        Set-SafeStatus running SSH_PUBLIC_KEY_PUBLICATION_RUNNING 3 0
        $publication=Invoke-Worker -Payload $payload -Publication
        $payload.Remove('connection')
        Save-PrivateResult 'ssh-publication-result.dpapi' $publication
        if($publication.status -ne 'verified'){
            Set-SafeStatus blocked $publication.code 3 0
            exit 2
        }
        Save-PrivateResult 'ssh-trust.dpapi' $publication
    } elseif(-not $ValidateOnly -and ($DiscoverOnly -or -not (Test-Path -LiteralPath (Join-Path $privateRoot 'ssh-trust.dpapi')))){
        Set-SafeStatus running SSH_CONSOLE_DISCOVERY_RUNNING
        $payload.connection=(Read-ProtectedBundle -Path (Join-Path $privateRoot 'vmware.dpapi'))|ConvertFrom-Json
        $stage='INVOKE_DISCOVERY'
        $discovery=Invoke-Worker -Payload $payload -Discovery
        $payload.Remove('connection')
        if($discovery.status -ne 'discovered'){
            Set-SafeStatus blocked $discovery.code
            exit 2
        }
        $count=0;$consoleCount=0;$ocrErrors=0;$fingerprintTextCount=0;$keyBannerCount=0
        foreach($node in $discovery.nodes){
            $matched=$false
            if($node.console_png){
                $consoleCount++
                try {
                    $text=Get-ConsoleText $node.console_png
                    # Exact fingerprint comparison; OCR errors cause a closed failure.
                    $compact=$text -replace '\s',''
                    if($text -match 'SHA256:'){$fingerprintTextCount++}
                    if($text -match 'HOST KEY|ssh-ed25519|FINGERPRINT'){$keyBannerCount++}
                    $matched=($node.fingerprint -and ($compact.Contains($node.fingerprint) -or $compact.Contains($node.key)))
                } catch {$ocrErrors++}
            }
            $node|Add-Member -NotePropertyName verified -NotePropertyValue $matched -Force
            $node|Add-Member -NotePropertyName verification_method -NotePropertyValue 'vcenter_console_ocr' -Force
            if($matched){$count++}
        }
        Save-PrivateResult 'ssh-discovery.dpapi' $discovery
        Set-SafeStatus pending SSH_KEYS_AWAITING_CONSOLE_VALIDATION 3 $count
        $safe=Get-Content -LiteralPath $statusPath -Raw|ConvertFrom-Json
        $safe|Add-Member -NotePropertyName console_image_count -NotePropertyValue $consoleCount
        $safe|Add-Member -NotePropertyName ocr_error_count -NotePropertyValue $ocrErrors
        $safe|Add-Member -NotePropertyName console_fingerprint_text_count -NotePropertyValue $fingerprintTextCount
        $safe|Add-Member -NotePropertyName console_key_banner_count -NotePropertyValue $keyBannerCount
        $safe|Add-Member -NotePropertyName scan_codes -NotePropertyValue @($discovery.nodes|ForEach-Object {if($_.scan_code){$_.scan_code}else{'HOST_KEY_SCANNED'}})
        [IO.File]::WriteAllText($statusPath,($safe|ConvertTo-Json),[Text.Encoding]::UTF8)
        if($count -eq 3){Save-PrivateResult 'ssh-trust.dpapi' $discovery}
        if($DiscoverOnly -or $count -ne 3){exit 0}
    }
    $payload.trust=(Read-ProtectedBundle -Path (Join-Path $privateRoot 'ssh-trust.dpapi'))|ConvertFrom-Json
    Set-SafeStatus running SSH_LINUX_PREFLIGHT_RUNNING 3 3
    $result=Invoke-Worker -Payload $payload
    $discoveryPath=Join-Path $privateRoot 'ssh-discovery.dpapi'
    if(Test-Path -LiteralPath $discoveryPath){
        $observed=(Read-ProtectedBundle -Path $discoveryPath)|ConvertFrom-Json
        $preserved=($observed.operation_id -eq $operation.id -and $observed.nodes.Count -eq 3)
        for($index=0;$index -lt 3;$index++){
            if($observed.nodes[$index].key -ne $payload.trust.nodes[$index].key){$preserved=$false}
        }
        $result|Add-Member -NotePropertyName host_keys_preserved -NotePropertyValue $preserved
    }
    Save-PrivateResult 'ssh-preflight.dpapi' $result
    Set-SafeStatus $result.status $result.code 3 3 $result
    if(-not $result.passed){exit 2}
} catch {
    if($lockStream){
        Set-SafeStatus blocked LOCAL_SSH_VALIDATION_FAILED
        $safe=Get-Content -LiteralPath $statusPath -Raw|ConvertFrom-Json
        $safe|Add-Member -NotePropertyName local_stage -NotePropertyValue $stage
        $safe|Add-Member -NotePropertyName local_failure_line -NotePropertyValue ([int]$_.InvocationInfo.ScriptLineNumber)
        [IO.File]::WriteAllText($statusPath,($safe|ConvertTo-Json),[Text.Encoding]::UTF8)
    }
    exit 2
} finally {
    $target=$null;$payload=$null;$discovery=$null;$text=$null
    if($lockStream){$lockStream.Dispose()}
}
