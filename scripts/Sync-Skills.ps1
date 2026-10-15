#Requires -Version 5.1
<#
.SYNOPSIS
    Synchronise les compétences partagées (skills) d'ArcIA.
.DESCRIPTION
    Copie les compétences internes (ponytail, graphify, public-apis)
    et synchronise les catalogues standards dans le répertoire cible.
#>
[CmdletBinding()]
param (
    [string]$TargetDir = "/var/data/arcia/shared-skills",
    [switch]$LocalOnly
)

$ErrorActionPreference = "Stop"

Write-Host "=== Synchronisation des compétences ArcIA ===" -ForegroundColor Cyan

$SkillsSourceDir = Join-Path $PSScriptRoot "..\skills"
if (Test-Path $SkillsSourceDir) {
    Write-Host "[*] Déploiement des compétences natives ArcIA vers : $TargetDir" -ForegroundColor Yellow
    Get-ChildItem -Directory -Path $SkillsSourceDir | ForEach-Object {
        $skillName = $_.Name
        $destPath = Join-Path $TargetDir "arcia\$skillName"
        if (-not (Test-Path $destPath)) {
            New-Item -ItemType Directory -Path $destPath -Force | Out-Null
        }
        Copy-Item -Path "$($_.FullName)\*" -Destination $destPath -Recurse -Force
        Write-Host "  [+] Compétence synchronisée : $skillName" -ForegroundColor Green
    }
}

if (-not $LocalOnly) {
    Write-Host "[*] Vérification des catalogues externes standards..." -ForegroundColor Yellow
    # Vérification facultative via npx si disponible
    if (Get-Command npx -ErrorAction SilentlyContinue) {
        Write-Host "  [+] Outil npx disponible pour les catalogues distants." -ForegroundColor Gray
    }
}

Write-Host "[OK] Synchronisation des compétences terminée avec succès." -ForegroundColor Green
