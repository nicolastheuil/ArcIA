#Requires -Version 5.1
<#
.SYNOPSIS
    Synchronise et met à jour les compétences partagées (skills) d'ArcIA.
.DESCRIPTION
    Déploie les compétences internes natives (ponytail, graphify, public-apis)
    et synchronise les catalogues standards (ECC, Superpowers, Vercel, Anthropics)
    dans le répertoire cible partagé.
.PARAMETER TargetDir
    Répertoire cible où stocker les compétences partagées.
.PARAMETER Update
    Actualise les dépôts externes existants.
.PARAMETER LocalOnly
    Synchronise uniquement les compétences locales ArcIA sans appels réseau.
#>
[CmdletBinding()]
param (
    [string]$TargetDir = "/var/data/arcia/shared-skills",
    [switch]$Update,
    [switch]$LocalOnly
)

$ErrorActionPreference = "Stop"

Write-Host "==============================================================================" -ForegroundColor Cyan
Write-Host " ArcIA — Synchronisation des Compétences Partagées (Skills)" -ForegroundColor Cyan
Write-Host " Cible : $TargetDir" -ForegroundColor Cyan
Write-Host "==============================================================================" -ForegroundColor Cyan

if (-not (Test-Path $TargetDir)) {
    New-Item -ItemType Directory -Path $TargetDir -Force | Out-Null
}

# 1. Compétences Natives ArcIA (100% locales et autonomes)
$SkillsSourceDir = Join-Path $PSScriptRoot "..\skills"
if (Test-Path $SkillsSourceDir) {
    Write-Host "[*] Déploiement des compétences natives ArcIA..." -ForegroundColor Yellow
    Get-ChildItem -Directory -Path $SkillsSourceDir | ForEach-Object {
        $skillName = $_.Name
        if ($skillName -ne "node_modules") {
            $destPath = Join-Path $TargetDir "arcia\$skillName"
            if (-not (Test-Path $destPath)) {
                New-Item -ItemType Directory -Path $destPath -Force | Out-Null
            }
            Copy-Item -Path "$($_.FullName)\*" -Destination $destPath -Recurse -Force
            Write-Host "  [+] Compétence native installée : arcia/$skillName" -ForegroundColor Green
        }
    }
}

# 2. Catalogues Standards Externes (ECC, Superpowers, Vercel, Anthropics)
if (-not $LocalOnly) {
    Write-Host "[*] Synchronisation des catalogues externes standards..." -ForegroundColor Yellow

    $hasNpx = $null -ne (Get-Command npx -ErrorAction SilentlyContinue)
    $hasSkillsCli = $null -ne (Get-Command skills -ErrorAction SilentlyContinue)

    $catalogs = @(
        @{ Repo = "affaan-m/everything-claude-code"; Dest = "ecc" },
        @{ Repo = "obra/superpowers"; Dest = "superpowers" },
        @{ Repo = "vercel/ai-sdk"; Dest = "vercel" },
        @{ Repo = "anthropics/anthropic-quickstarts"; Dest = "anthropics" }
    )

    foreach ($cat in $catalogs) {
        $destPath = Join-Path $TargetDir $cat.Dest
        $exists = Test-Path $destPath

        if ($exists -and $Update) {
            Write-Host "  [~] Mise à jour du catalogue : $($cat.Repo) -> $($cat.Dest)" -ForegroundColor Cyan
            if ($hasSkillsCli) {
                & skills update $cat.Repo --destination $destPath 2>$null
            } elseif ($hasNpx) {
                & npx -y skills add $cat.Repo --destination $destPath --force 2>$null
            }
        } elseif (-not $exists) {
            Write-Host "  [+] Téléchargement du catalogue : $($cat.Repo) -> $($cat.Dest)" -ForegroundColor Green
            if ($hasSkillsCli) {
                & skills add $cat.Repo --destination $destPath 2>$null
            } elseif ($hasNpx) {
                & npx -y skills add $cat.Repo --destination $destPath 2>$null
            }
        } else {
            Write-Host "  [=] Catalogue déjà présent : $($cat.Dest) (utiliser -Update pour actualiser)" -ForegroundColor Gray
        }
    }
} else {
    Write-Host "[*] Mode local-only activé : Catalogues externes ignorés." -ForegroundColor Gray
}

# 3. Récapitulatif
$skillFiles = Get-ChildItem -Path $TargetDir -Filter "SKILL.md" -Recurse -ErrorAction SilentlyContinue
$totalCount = if ($skillFiles) { $skillFiles.Count } else { 0 }

Write-Host "==============================================================================" -ForegroundColor Cyan
Write-Host "[OK] Synchronisation réussie dans $TargetDir" -ForegroundColor Green
Write-Host "[+] Nombre total de compétences opérationnelles : $totalCount" -ForegroundColor Green
Write-Host "==============================================================================" -ForegroundColor Cyan
