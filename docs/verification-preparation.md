# Vérification de la préparation — 11 octobre 2026

## Exécuté localement

| Contrôle | Résultat |
|---|---|
| Python 3.14.7, unittest | 28 tests synthétiques réussis |
| PowerShell, quatre scripts | Parse sans erreur |
| ProtectedState, DPAPI et ACL | Roundtrip réussi, canari absent du fichier chiffré, ACL restreinte |
| ProtectedState, refus | Écrasement existant et chemin dans le workspace refusés |
| JSON Schema draft 2020-12 | Schéma et fixture valides |
| YAML | Tous les manifests/playbooks parsés |
| Ansible 2.21.5 sur WSL Python 3.14.4 | Syntaxe preflight.yml et site.yml valide |
| Ansible sur inventaire synthétique | Installation refusée au premier play local, avant SSH |
| CLI plan synthétique | safe_mode=true, installation_ready=false, release_ready=false |
| Sources officielles | Tags/commits et SHA256 K3s relevés ; pas d'image applicative qualifiée |

Commandes reproductibles : README.md, requirements-validation.txt et
scripts/validate_sources.py. Le test DPAPI utilise seulement un canari synthétique
et supprime ses fichiers exacts après essai. Le wizard interactif complet et la
mise à jour administrative des gates ne sont pas qualifiés de bout en bout.

La CI reproduit tests Python, schéma/YAML/Ansible et test DPAPI sur runners hébergés
sans secret d'entreprise. Les actions checkout/setup-python sont épinglées par
commit résolu sur leurs tags officiels. Aucun runner avec route vers les clients.

## Non exécuté

Préflight de VM réelle, application Kubernetes et admission serveur, installation
K3s, idempotence sur cible, CSI/CPI, propriété unique/fencing, bascule PG et endpoints,
Desktop/OIDC/Teams, coffres, assainissement, tunnels/kill switch, sauvegarde chiffrée
et rebuild neuf. Aucune release installable ou disponibilité garantie.

## Limites

Les tests statiques de manifests ne démontrent pas le datapath réseau réel. Le mode
sûr déclaratif doit être implémenté par les futurs services. Paquets apt et
dépendances transitives ne constituent pas encore un lock de release avec hashes.
Les scripts refusent l'adoption/migration d'un cluster existant ; la reprise réelle
d'une interruption doit être testée sur les VM de qualification.
