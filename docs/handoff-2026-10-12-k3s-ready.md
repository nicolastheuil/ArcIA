# Handoff — K3s HA installé et validé (12/10/2026 14:22 UTC)

## État cluster
- **3 nœuds Debian 13** sur 3 ESXi distincts : `arcia-k3s-01` (172.31.210.61), `arcia-k3s-02` (172.31.210.62), `arcia-k3s-03` (172.31.210.63)
- **K3s v1.37.1+k3s1** (upgrade depuis v1.35.9+k3s1 pour corriger bug re-exec)
- **HA embedded etcd** : 3 control-planes, quorum OK
- **Secrets encryption** : AES-CBC activé, rotation `start`, hashes match
- **Nodes** : tous `Ready`, roles `control-plane,etcd`, version `v1.37.1+k3s1`
- **Container runtime** : containerd 2.3.4-k3s1
- **CNI** : Flannel VXLAN (pod CIDR 10.42.0.0/16, service CIDR 10.43.0.0/16)
- **Cloud controller** : désactivé (`disable-cloud-controller: true`, `kubelet-arg: cloud-provider=external`)
- **VIP Keepalived** : opérationnel (bascule 12/12 validée précédemment)

## Corrections appliquées
1. **Upgrade K3s** v1.35.9 → v1.37.1+k3s1 (commit 356c025475bbefaa09cf0d7e48e8e2adbbde57db)
2. **Wrapper scripts** `k3s-server` / `k3s-agent` avec protection re-exec (`K3S_REEXEC_DONE`)
3. **Launcher** `k3s-server-launcher` (exec -a k3s-server)
4. **ExecStartPre** : `rm -rf /var/lib/rancher/k3s/data` pour éviter boucle artefact
5. **Service systemd** : Type=notify, Restart=always, daemon_reload idempotent
6. **versions.lock.yaml** mis à jour avec SHA256 vérifiés (installer, binary, images)

## Fichiers modifiés
- `versions.lock.yaml` — k3s v1.37.1+k3s1 + digests
- `docs/versions-officielles.md` — version + notes qualification
- `infra/ansible/roles/k3s/tasks/main.yml` — wrappers, launcher, ExecStartPre, démarrage idempotent
- `scripts/Invoke-ClusterFoundation.ps1` — chemin Python corrigé (venv Codex)

## Prochaines étapes (plan §25-26)
1. **CPI vSphere** — `deploy/vendor/vmware/cpi/` (v1.35.1, image digest épinglée)
2. **CSI vSphere** — `deploy/vendor/vmware/csi/` (v3.7.3, sidecars + digests)
3. **PVC synthétiques** — qualification stockage RWOP/RWX
4. **CloudNativePG** — cluster PG HA (v1.30.1)
5. **Hermes** — agent v0.21.6
6. **Lots 0+** — Entra/Teams/VPN/coffres/DLP

## Secrets & état privé
- Archive portable : `secrets/local/arcia-private.arciap` (clé 1Password "ArcIA Platform Encryption Key")
- Bundles DPAPI restaurés dans `%LOCALAPPDATA%\ArcIA-Harness` : `vmware-target.dpapi`, `ssh-trust.dpapi`, `instance.dpapi`, `vmware-operation.dpapi`
- Lock d'opération : `cluster-operation.lock`

## Commandes utiles
```powershell
# Inspection cluster
pwsh scripts/Invoke-ClusterFoundation.ps1 -Action inspect_k3s
pwsh scripts/Diagnose-Cluster.ps1

# SSH nœuds
ssh -i %LOCALAPPDATA%\ArcIA-Harness\ssh\arcia-vm_ed25519 nicolas@172.31.210.61 "sudo /usr/local/bin/k3s kubectl get nodes -o wide"
```