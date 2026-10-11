# Portable encrypted checkpoints. PowerShell 7.4+ / .NET 8+, no secret stdout.
Add-Type -AssemblyName System.Security
Add-Type -AssemblyName System.IO.Compression

function Get-PortableDigest([byte[]]$Bytes){
    return [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($Bytes)).ToLowerInvariant()
}
function Get-PortableKey([string]$Password,[byte[]]$Salt){
    return ,[Security.Cryptography.Rfc2898DeriveBytes]::Pbkdf2($Password,$Salt,1000000,[Security.Cryptography.HashAlgorithmName]::SHA256,32)
}
function Get-PortableStrings($Value){
    if($Value -is [string]){return $Value}
    if($Value -is [Collections.IDictionary]){foreach($v in $Value.Values){Get-PortableStrings $v};return}
    if($Value -is [Collections.IEnumerable]){foreach($v in $Value){Get-PortableStrings $v}}
}
function Update-PortableReferences($Value,[Collections.IDictionary]$Mappings){
    if($Value -is [string]){
        foreach($old in @($Mappings.Keys|Sort-Object Length -Descending)){
            if($Value.Equals($old,[StringComparison]::OrdinalIgnoreCase)){return $Mappings[$old]}
            if($Value.StartsWith($old.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase)){
                return $Mappings[$old].TrimEnd('\')+$Value.Substring($old.TrimEnd('\').Length)
            }
        }
        return $Value
    }
    if($Value -is [Collections.IDictionary]){
        $result=@{};foreach($key in $Value.Keys){$result[$key]=Update-PortableReferences $Value[$key] $Mappings};return $result
    }
    if($Value -is [Collections.IEnumerable]){
        $result=@(foreach($v in $Value){Update-PortableReferences $v $Mappings});return ,$result
    }
    return $Value
}
function Read-PortableArchive([string]$Archive,[string]$Password){
    $inputFile=[IO.File]::OpenRead($Archive)
    try{
        $reader=[IO.BinaryReader]::new($inputFile)
        if([Text.Encoding]::ASCII.GetString($reader.ReadBytes(8)) -ne 'ARCIAP01'){throw 'PORTABLE_FORMAT_INVALID'}
        $length=$reader.ReadInt32();if($length -lt 20 -or $length -gt 8192){throw 'PORTABLE_HEADER_INVALID'}
        $aad=$reader.ReadBytes($length);$header=[Text.Encoding]::UTF8.GetString($aad)|ConvertFrom-Json -AsHashtable
        if($header.schema_version -ne 1 -or $header.cipher -ne 'AES-256-GCM' -or $header.kdf -ne 'PBKDF2-SHA256' -or $header.iterations -ne 1000000){throw 'PORTABLE_PARAMETERS_INVALID'}
        $remaining=$inputFile.Length-$inputFile.Position
        if($remaining -lt 17 -or $remaining -gt 1GB){throw 'PORTABLE_SIZE_INVALID'}
        $cipher=$reader.ReadBytes([int]($remaining-16));$tag=$reader.ReadBytes(16)
        $salt=[Convert]::FromBase64String($header.salt);$nonce=[Convert]::FromBase64String($header.nonce)
        if($salt.Length -ne 16 -or $nonce.Length -ne 12){throw 'PORTABLE_NONCE_INVALID'}
        $key=Get-PortableKey $Password $salt;$plain=New-Object byte[] $cipher.Length
        $aes=[Security.Cryptography.AesGcm]::new($key,16)
        try{$aes.Decrypt($nonce,$cipher,$tag,$plain,$aad)}finally{$aes.Dispose();[Array]::Clear($key)}
        return @{bytes=$plain;header=$header}
    }finally{$inputFile.Dispose()}
}
function Get-PortableManifest([byte[]]$Bytes){
    $stream=[IO.MemoryStream]::new($Bytes,$false);$zip=[IO.Compression.ZipArchive]::new($stream,[IO.Compression.ZipArchiveMode]::Read)
    try{
        $manifestEntry=$zip.GetEntry('__arcia_manifest.json');if(-not $manifestEntry){throw 'PORTABLE_MANIFEST_MISSING'}
        $reader=[IO.StreamReader]::new($manifestEntry.Open(),[Text.Encoding]::UTF8)
        try{$manifest=$reader.ReadToEnd()|ConvertFrom-Json -AsHashtable}finally{$reader.Dispose()}
        if($manifest.schema_version -ne 1 -or $zip.Entries.Count -ne $manifest.files.Count+1){throw 'PORTABLE_MANIFEST_INVALID'}
        $seen=[Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
        foreach($file in $manifest.files){
            $name=[string]$file.name
            if(-not $seen.Add($name) -or $name -match '(^/|(^|/)\.\.(/|$)|\\|:)' -or $name.StartsWith('__arcia_')){throw 'PORTABLE_ENTRY_PATH_INVALID'}
            $entry=$zip.GetEntry($name)
            if(-not $entry -or $entry.Length -ne $file.size -or $entry.Length -gt 1GB){throw 'PORTABLE_ENTRY_SIZE_INVALID'}
            $data=[IO.MemoryStream]::new();$source=$entry.Open()
            try{$source.CopyTo($data);if((Get-PortableDigest $data.ToArray()) -ne $file.sha256){throw 'PORTABLE_ENTRY_HASH_INVALID'}}finally{$source.Dispose();$data.Dispose()}
        }
        return $manifest
    }finally{$zip.Dispose();$stream.Dispose()}
}
function Export-PortableState([string]$Source,[string]$Workspace,[string]$Archive,[string]$Password){
    $temporary=$null
    if($Password.Length -lt 16){throw 'PORTABLE_PASSWORD_TOO_SHORT'}
    $sourceRoot=[IO.Path]::GetFullPath($Source).TrimEnd('\')
    $files=@(Get-ChildItem -LiteralPath $sourceRoot -Recurse -File -Force|Where-Object {$_.Extension -ne '.lock'})
    if(-not $files.Count -or ($files|Measure-Object Length -Sum).Sum -gt 900MB){throw 'PORTABLE_SOURCE_SIZE_INVALID'}
    $physicalRoot=([IO.DirectoryInfo]::new($sourceRoot)).FullName
    # Resolve MSIX path through the same Python runtime used by protected workers.
    $python=Join-Path $env:LOCALAPPDATA 'ArcIA-Validation/venv/Scripts/python.exe'
    if(Test-Path -LiteralPath $python){
        $resolved=& $python -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve())' $sourceRoot
        if($LASTEXITCODE -eq 0 -and $resolved){$physicalRoot=[string]$resolved}
    }
    $records=[Collections.Generic.List[object]]::new();$references=@{};$originals=@{}
    $memory=[IO.MemoryStream]::new();$zip=[IO.Compression.ZipArchive]::new($memory,[IO.Compression.ZipArchiveMode]::Create,$true)
    try{
        foreach($file in $files){
            if($file.LinkType -in @('SymbolicLink','Junction')){throw 'PORTABLE_LINK_REFUSED'}
            $name=[IO.Path]::GetRelativePath($sourceRoot,$file.FullName).Replace('\','/')
            $bytes=[IO.File]::ReadAllBytes($file.FullName);$originals[$file.FullName]=Get-PortableDigest $bytes
            $dpapi=$file.Extension -eq '.dpapi'
            if($dpapi){
                $bytes=[Security.Cryptography.ProtectedData]::Unprotect($bytes,$null,[Security.Cryptography.DataProtectionScope]::CurrentUser)
                $parsed=[Text.Encoding]::UTF8.GetString($bytes)|ConvertFrom-Json -AsHashtable
                foreach($value in @(Get-PortableStrings $parsed)){
                    # Local file references only; never follow UNC shares or query client systems.
                    if($value -match '^[A-Za-z]:[\\/]' -and [IO.File]::Exists($value) -and
                       -not $value.StartsWith($sourceRoot+'\',[StringComparison]::OrdinalIgnoreCase) -and
                       -not $value.StartsWith($physicalRoot+'\',[StringComparison]::OrdinalIgnoreCase)){
                        $extension=[IO.Path]::GetExtension($value);if($extension -notmatch '^\.[a-zA-Z0-9]{1,8}$'){$extension='.bin'}
                        $references[$value]='references/'+(Get-PortableDigest ([Text.Encoding]::UTF8.GetBytes($value)))+$extension
                    }
                }
            }
            $entry=$zip.CreateEntry($name,[IO.Compression.CompressionLevel]::Optimal);$destination=$entry.Open()
            try{$destination.Write($bytes)}finally{$destination.Dispose()}
            $records.Add(@{name=$name;size=$bytes.Length;sha256=(Get-PortableDigest $bytes);dpapi=$dpapi})
            [Array]::Clear($bytes)
        }
        foreach($reference in $references.Keys){
            $bytes=[IO.File]::ReadAllBytes($reference);$originals[$reference]=Get-PortableDigest $bytes
            $entry=$zip.CreateEntry($references[$reference],[IO.Compression.CompressionLevel]::Optimal);$destination=$entry.Open()
            try{$destination.Write($bytes)}finally{$destination.Dispose()}
            $records.Add(@{name=$references[$reference];size=$bytes.Length;sha256=(Get-PortableDigest $bytes);dpapi=$false});[Array]::Clear($bytes)
        }
        $manifest=@{schema_version=1;private_root=$sourceRoot;physical_root=$physicalRoot;workspace=[IO.Path]::GetFullPath($Workspace);
            created_at=[DateTime]::UtcNow.ToString('o');files=@($records.ToArray());references=$references}
        $entry=$zip.CreateEntry('__arcia_manifest.json');$writer=[IO.StreamWriter]::new($entry.Open(),[Text.UTF8Encoding]::new($false))
        try{$writer.Write(($manifest|ConvertTo-Json -Depth 60 -Compress))}finally{$writer.Dispose()}
    }finally{$zip.Dispose()}
    try{
        $plain=$memory.ToArray();$salt=[Security.Cryptography.RandomNumberGenerator]::GetBytes(16);$nonce=[Security.Cryptography.RandomNumberGenerator]::GetBytes(12)
        $header=@{schema_version=1;cipher='AES-256-GCM';kdf='PBKDF2-SHA256';iterations=1000000;
            salt=[Convert]::ToBase64String($salt);nonce=[Convert]::ToBase64String($nonce)}
        $aad=[Text.Encoding]::UTF8.GetBytes(($header|ConvertTo-Json -Compress))
        $key=Get-PortableKey $Password $salt;$cipher=New-Object byte[] $plain.Length;$tag=New-Object byte[] 16
        $aes=[Security.Cryptography.AesGcm]::new($key,16)
        try{$aes.Encrypt($nonce,$plain,$cipher,$tag,$aad)}finally{$aes.Dispose();[Array]::Clear($key);[Array]::Clear($plain)}
        $temporary=$Archive+'.'+[guid]::NewGuid().ToString('N')+'.part'
        $outputFile=[IO.File]::Open($temporary,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
        try{$writer=[IO.BinaryWriter]::new($outputFile);$writer.Write([Text.Encoding]::ASCII.GetBytes('ARCIAP01'));$writer.Write([int]$aad.Length);$writer.Write($aad);$writer.Write($cipher);$writer.Write($tag);$writer.Flush();$outputFile.Flush($true)}finally{$outputFile.Dispose()}
        [Array]::Clear($cipher)
        $verified=Read-PortableArchive $temporary $Password
        try{$null=Get-PortableManifest $verified.bytes}finally{[Array]::Clear($verified.bytes)}
        foreach($name in $originals.Keys){if((Get-PortableDigest ([IO.File]::ReadAllBytes($name))) -ne $originals[$name]){throw 'PORTABLE_SOURCE_CHANGED_RETRY'}}
        if(Test-Path -LiteralPath $Archive){
            $previous=$Archive+'.previous';if(Test-Path -LiteralPath $previous){Remove-Item -LiteralPath $previous}
            [IO.File]::Replace($temporary,$Archive,$previous)
        }else{Move-Item -LiteralPath $temporary -Destination $Archive}
        return @{status='verified';code='PORTABLE_ARCHIVE_CREATED_AND_VERIFIED';file_count=$records.Count;
            rebound_dpapi_count=@($records|Where-Object dpapi).Count;referenced_file_count=$references.Count;portable_across_windows_accounts=$true}
    }finally{$memory.Dispose();if($temporary -and (Test-Path -LiteralPath $temporary)){Remove-Item -LiteralPath $temporary}}
}
function Import-PortableState([string]$Archive,[string]$Destination,[string]$Workspace,[string]$Password){
    $root=[IO.Path]::GetFullPath($Destination).TrimEnd('\')
    if((Test-Path -LiteralPath $root) -and @(Get-ChildItem -LiteralPath $root -Force).Count){throw 'PORTABLE_DESTINATION_NOT_EMPTY'}
    if((Test-Path -LiteralPath $root) -and ((Get-Item -LiteralPath $root).Attributes -band [IO.FileAttributes]::ReparsePoint)){throw 'PORTABLE_DESTINATION_LINK_REFUSED'}
    $stage=$root+'.restore-'+[guid]::NewGuid().ToString('N')
    $data=Read-PortableArchive $Archive $Password
    try{
        $manifest=Get-PortableManifest $data.bytes
        $mappings=@{};$mappings[$manifest.private_root]=$root;$mappings[$manifest.physical_root]=$root;$mappings[$manifest.workspace]=[IO.Path]::GetFullPath($Workspace)
        foreach($old in $manifest.references.Keys){$mappings[$old]=Join-Path $root $manifest.references[$old]}
        $stream=[IO.MemoryStream]::new($data.bytes,$false);$zip=[IO.Compression.ZipArchive]::new($stream,[IO.Compression.ZipArchiveMode]::Read)
        try{
            Initialize-PrivateDirectory $stage
            foreach($file in $manifest.files){
                $path=[IO.Path]::GetFullPath((Join-Path $stage $file.name))
                if(-not $path.StartsWith($stage+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'PORTABLE_RESTORE_PATH_SCOPE'}
                $null=[IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($path))
                $buffer=[IO.MemoryStream]::new();$entry=$zip.GetEntry($file.name).Open()
                try{$entry.CopyTo($buffer);$bytes=$buffer.ToArray()}finally{$entry.Dispose();$buffer.Dispose()}
                if($file.dpapi){
                    $object=[Text.Encoding]::UTF8.GetString($bytes)|ConvertFrom-Json -AsHashtable
                    $object=Update-PortableReferences $object $mappings
                    $revised=[Text.Encoding]::UTF8.GetBytes(($object|ConvertTo-Json -Depth 100 -Compress))
                    [Array]::Clear($bytes)
                    $bytes=[Security.Cryptography.ProtectedData]::Protect($revised,$null,[Security.Cryptography.DataProtectionScope]::CurrentUser)
                    [Array]::Clear($revised)
                }
                [IO.File]::WriteAllBytes($path,$bytes)
                if((Get-PortableDigest ([IO.File]::ReadAllBytes($path))) -ne (Get-PortableDigest $bytes)){throw 'PORTABLE_RESTORE_READBACK_FAILED'}
                [Array]::Clear($bytes)
            }
        }finally{$zip.Dispose();$stream.Dispose()}
        if(Test-Path -LiteralPath $root){[IO.Directory]::Delete($root,$false)} # Empty only; never erase existing state.
        [IO.Directory]::Move($stage,$root)
        return @{status='restored';code='PORTABLE_STATE_RESTORED_FOR_CURRENT_WINDOWS_USER';file_count=$manifest.files.Count;deployment_started=$false}
    }finally{
        [Array]::Clear($data.bytes)
        # Exact generated staging directory, checked inside the explicitly named parent.
        $checked=[IO.Path]::GetFullPath($stage)
        if($checked.StartsWith($root+'.restore-',[StringComparison]::OrdinalIgnoreCase) -and
            [IO.Path]::GetDirectoryName($checked) -eq [IO.Path]::GetDirectoryName($root) -and
            (Test-Path -LiteralPath $checked) -and
            -not ((Get-Item -LiteralPath $checked).Attributes -band [IO.FileAttributes]::ReparsePoint)){
            [IO.Directory]::Delete($checked,$true)
        }
    }
}
