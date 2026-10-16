# Runbooks d'Exploitation & Guides Opérationnels — ArcIA

Ce dossier contient les procédures d'exploitation pas-à-pas pour installer, administrer, surveiller et restaurer la plateforme ArcIA en environnement réel.

## Sommaire des Runbooks

| Procédure | Fichier | Objectif |
|---|---|---|
| **Démarrage Rapide (Quickstart)** | [quickstart.md](quickstart.md) | Guide d'installation complet en 3 étapes : prérequis VMware/Debian, assistant de configuration interactif et premier déploiement vérifié. |
| **Exploitation & Maintenance Quotidienne** | [exploitation.md](exploitation.md) | Diagnostics des services, consultation des logs, rotation des secrets et gestion des mises à jour des composants. |
| **Sauvegarde, Restauration & Reconstruction** | [sauvegarde-reconstruction.md](sauvegarde-reconstruction.md) | Sauvegarde chiffrée des volumes persistants (PVCs SQLite/ChromaDB), reprise d'activité après sinistre et reconstruction sur cluster neuf. |

## Règle de Qualification des Déploiements

Conformément à la charte d'ingénierie ArcIA :
* **Proposé** : cible décidée dans les spécifications.
* **Codé** : scripts et manifests validés dans Git.
* **Déployé** : appliqué avec succès sur le cluster cible.
* **Vérifié** : recette fonctionnelle exécutée et journalisée.
