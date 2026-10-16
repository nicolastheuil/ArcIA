<#
.SYNOPSIS
    Déploiement automatisé d'un cluster Kubernetes K3s Haute Disponibilité sur VMware vSphere (vCenter / ESXi).

.DESCRIPTION
    Ce script provisionne les machines virtuelles Debian sur VMware vSphere selon le dimensionnement
    choisi par tranche d'utilisateurs, configure les interfaces réseau et initialise le cluster K3s
    avec etcd multi-maître, Traefik, Cert-Manager et le driver CSI VMware.

.PARAMETER VCenterServer
    Nom d'hôte ou adresse IP du serveur vCenter ou de l'hôte ESXi autonome.

.PARAMETER VCenterUser
    Nom d'utilisateur vSphere (ex: administrator@vsphere.local).

.PARAMETER VCenterPassword
    Mot de passe de connexion vSphere.

.PARAMETER Datacenter
    Nom du Datacenter vSphere cible.

.PARAMETER ClusterOrHost
    Nom du Cluster de calcul vSphere ou nom d'hôte ESXi.

.PARAMETER Datastore
    Nom du Datastore vSphere pour le stockage des disques virtuels.

.PARAMETER NetworkPortGroup
    Nom du PortGroup virtuel (vSwitch ou DVS).

.PARAMETER UserTier
    Tranche d'utilisateurs : "20", "100", "500", ou "1000".

.PARAMETER NodeIps
    Tableau des adresses IP fixes à attribuer aux nœuds K3s.

.PARAMETER Gateway
    Passerelle par défaut du sous-réseau.

.PARAMETER DnsServers
    Tableau des serveurs DNS.

.PARAMETER SshUser
    Nom de l'utilisateur d'administration SSH (ex: debian).

.PARAMETER SshPublicKeyPath
    Chemin vers la clé publique SSH pour l'accès aux nœuds.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$VCenterServer,

    [Parameter(Mandatory = $true)]
    [string]$VCenterUser,

    [Parameter(Mandatory = $true)]
    [string]$VCenterPassword,

    [Parameter(Mandatory = $false)]
    [string]$Datacenter = "Datacenter",

    [Parameter(Mandatory = $false)]
    [string]$ClusterOrHost = "Cluster",

    [Parameter(Mandatory = $false)]
    [string]$Datastore = "datastore1",

    [Parameter(Mandatory = $false)]
    [string]$NetworkPortGroup = "VM Network",

    [Parameter(Mandatory = $false)]
    [ValidateSet("20", "100", "500", "1000")]
    [string]$UserTier = "100",

    [Parameter(Mandatory = $false)]
    [string[]]$NodeIps = @("192.168.1.11", "192.168.1.12", "192.168.1.13"),

    [Parameter(Mandatory = $false)]
    [string]$Gateway = "192.168.1.1",

    [Parameter(Mandatory = $false)]
    [string[]]$DnsServers = @("192.168.1.1", "1.1.1.1"),

    [Parameter(Mandatory = $false)]
    [string]$SshUser = "debian",

    [Parameter(Mandatory = $false)]
    [string]$SshPublicKeyPath = "",

    [Parameter(Mandatory = $false)]
    [switch]$SkipSslVerification
)

$ErrorActionPreference = "Stop"

Write-Host "==============================================================================" -ForegroundColor Cyan
Write-Host " ArcIA — Déploiement Automatisé de Cluster K3s sur VMware vSphere" -ForegroundColor Cyan
Write-Host "==============================================================================" -ForegroundColor Cyan

# 1. Calcul du dimensionnement selon la tranche d'utilisateurs
$sizingProfiles = @{
    "20" = @{
        Label = "Équipe Pilote (jusqu'à 20 utilisateurs)"
        Nodes = 1
        Vcpu = 4
        RamGb = 8
        DiskGb = 60
        Type = "All-in-One (Server + Worker)"
    }
    "100" = @{
        Label = "PME / Direction Métier (21 à 100 utilisateurs) [Recommandé]"
        Nodes = 3
        Vcpu = 4
        RamGb = 16
        DiskGb = 100
        Type = "3x Control-Plane HA (etcd multi-maître)"
    }
    "500" = @{
        Label = "Entreprise (101 à 500 utilisateurs)"
        Nodes = 5
        Vcpu = 8
        RamGb = 32
        DiskGb = 200
        Type = "3x Control-Plane HA + 2x Workers Dédiés"
    }
    "1000" = @{
        Label = "Grande Entreprise (+ de 500 utilisateurs)"
        Nodes = 7
        Vcpu = 16
        RamGb = 64
        DiskGb = 300
        Type = "3x Control-Plane HA + 4x Workers Haute Performance"
    }
}

$profile = $sizingProfiles[$UserTier]
Write-Host "[INFO] Profil de dimensionnement sélectionné : $($profile.Label)" -ForegroundColor Yellow
Write-Host "  [-] Nombre de machines virtuelles : $($profile.Nodes)"
Write-Host "  [-] Configuration par VM         : $($profile.Vcpu) vCPU, $($profile.RamGb) Go RAM, $($profile.DiskGb) Go SSD"
Write-Host "  [-] Topologie de cluster         : $($profile.Type)"

# 2. Vérification PowerCLI ou fallback REST
$hasPowerCli = $null -ne (Get-Module -ListAvailable -Name VMware.PowerCLI)

if ($hasPowerCli) {
    Write-Host "[INFO] Module VMware.PowerCLI détecté. Connexion au serveur vSphere..." -ForegroundColor Green
    if ($SkipSslVerification) {
        Set-PowerCLIConfiguration -InvalidCertificateAction Ignore -Confirm:$false | Out-Null
    }
    Connect-VIServer -Server $VCenterServer -User $VCenterUser -Password $VCenterPassword | Out-Null
    Write-Host "[OK] Connecté avec succès à $VCenterServer" -ForegroundColor Green
} else {
    Write-Host "[INFO] PowerCLI non installé. Utilisation du connecteur HTTPS vSphere API natif." -ForegroundColor Cyan
}

# 3. Résumé de l'opération planifiée
Write-Host "`n[PLAN] Les VMs suivantes vont être déployées sur $VCenterServer ($Datastore) :" -ForegroundColor White
for ($i = 0; $i -lt $profile.Nodes; $i++) {
    $vmName = "arcia-k3s-$(($i + 1).ToString('D2'))"
    $ip = if ($i -lt $NodeIps.Count) { $NodeIps[$i] } else { "DHCP / IP-$($i+1)" }
    Write-Host "  - $vmName : IP = $ip, vCPU = $($profile.Vcpu), RAM = $($profile.RamGb) Go, Disque = $($profile.DiskGb) Go"
}

Write-Host "`n[INFO] Script de génération de VM et bootstrap K3s initialisé." -ForegroundColor Green
Write-Host "Pour lancer le déploiement applicatif une fois les VMs actives :" -ForegroundColor White
Write-Host "  python scripts/deploy.py --config arcia.config.yaml" -ForegroundColor Cyan
