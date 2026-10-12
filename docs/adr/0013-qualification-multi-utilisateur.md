# ADR 0013 — Runtimes personnels et qualification locale multi-utilisateur

Statut : adopté pour la qualification synthétique du 12 octobre 2026. La gestion d’identités d’entreprise reste une cible distincte.

Deux profils dans un même processus Hermes ne séparent pas suffisamment les fichiers, mémoires, SQLite et outils. La qualification utilise donc deux namespaces et deux runtimes, avec chacun son état, son outillage RWOP et ses secrets propres. Le second espace utilise un préfixe HTTPS supporté nativement par Hermes, sur le même domaine et certificat ; aucune troisième entrée DNS n’est nécessaire.

Le corpus d’entreprise commun se partage par un service documentaire autorisé, jamais par le partage des répertoires Hermes. Chaque jeton possède des périmètres de lecture serveur ; PostgreSQL FORCE RLS filtre avant recherche/classement et téléchargement, et vérifie séparément le périmètre d’écriture. Les agents disposent uniquement d’un lecteur.

La recette réelle a révélé qu’effacer les cookies à la déconnexion native ne révoquait pas immédiatement une copie du jeton d’accès. Le harness ajoute une frontière ASGI sans modifier les fichiers Hermes épinglés : empreinte du jeton vérifié, expiration et registre durable propre au runtime, vérification sur les demandes HTTP et upgrades WebSocket portant un cookie/bearer. La recette teste le rejeu après déconnexion. Les connexions déjà ouvertes et le cycle complet SSO restent à intégrer.

Le bootstrap installe et vérifie ce second runtime avec les mêmes sources épinglées que le premier. Les [tests et limites](../multi-utilisateur.md) et la [sécurisation des données](../securisation-plateforme-donnees.md) définissent la portée. Cette qualification locale ne vaut pas homologation d’un annuaire central, de tous les connecteurs, ni d’une instance alimentée en données confidentielles réelles.
