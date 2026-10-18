<p align="left">
  <a href="../../README.md"><img src="https://img.shields.io/badge/🏠_Accueil-ArcIA_v0.5.0-1659E4?style=flat-square" alt="Accueil ArcIA"></a>
  <a href="../README.md"><img src="https://img.shields.io/badge/📖_Docs-Hub_Central-0C2762?style=flat-square" alt="Documentation"></a>
  <img src="https://img.shields.io/badge/Runbooks-Exploitation_&_PRA-FA7B4E?style=flat-square" alt="Runbooks">
</p>

# 🛠️ Runbooks d'exploitation et procédures opérationnelles — ArcIA

> **[🏠 Accueil ArcIA](../../README.md)** › **[📖 Documentation](../README.md)** › **Runbooks Opérationnels**

Ce dossier regroupe les procédures opérationnelles pas-à-pas destinées aux équipes DevOps, SRE et administrateurs pour installer, mettre à jour sans interruption de service, superviser et restaurer une instance **ArcIA**.

---

## 📋 Sommaire des runbooks

| Procédure | Fichier | Objectif opérationnel |
|---|---|---|
| 🚀 **Démarrage Rapide (Quickstart)** | **[quickstart.md](quickstart.md)** | Installation complète via le Wizard en **3 parcours dédiés** (`.\wizard.ps1` ou `./wizard.sh`), mise à jour en ligne Zero-Downtime, création de Pods Power Users (`.\scripts\Spawn-PowerUser.ps1`) et recette. |
| 🔍 **Exploitation & Maintenance (MCO)** | **[exploitation.md](exploitation.md)** | Supervision quotidienne des Pods, consultation des journaux, rotation des secrets, gestion des quotas LiteLLM et mises à jour RollingUpdate. |
| 🔄 **Sauvegarde, Restauration & PRA** | **[sauvegarde-reconstruction.md](sauvegarde-reconstruction.md)** | Sauvegarde chiffrée (`AES-256-GCM`) du coffre d'instance et des volumes persistants (SQLite / ChromaDB / PostgreSQL), et reconstruction sur cluster neuf. |

---

## 🛡️ Règle de qualification des opérations

> [!IMPORTANT]
> Conformément à la charte d'ingénierie ArcIA ([`AGENTS.md`](../../AGENTS.md)), tout état rapporté en exploitation distingue strictement :
> * **Proposé** : cible décidée dans les spécifications.
> * **Codé** : scripts et manifestes validés dans Git et couverts par les tests unitaires.
> * **Déployé** : appliqué avec succès sur le cluster cible.
> * **Vérifié** : recette fonctionnelle exécutée et contrôles de santé validés de bout en bout.
