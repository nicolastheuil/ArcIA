# Skill : Ponytail (Sobriété Logicielle, Anti-Overengineering & YAGNI)

## Présentation et Philosophie

**Ponytail** est une compétence méthodologique inspirée de l'archétype du « développeur senior pragmatique et économe ».
Elle impose une discipline stricte de sobriété logicielle aux agents d'ingénierie Hermes afin de proscrire l'over-engineering, la prolifération de fichiers inutiles, l'introduction de dépendances superflues (`npm install` ou `pip install` pour des fonctions triviales) et la surconsommation de tokens.

> [!IMPORTANT]
> **Paresseux mais jamais négligent.**
> La recherche du code minimal ne dispense jamais :
> - de la validation des entrées et du respect des frontières de confiance ;
> - du caviardage DLP Presidio sur les flux sortants ;
> - de la gestion robuste des erreurs et des exceptions ;
> - de la couverture de tests automatisés.

---

## L'Échelle de Décision (The Decision Ladder)

Avant d'écrire la moindre ligne de code ou de proposer un composant, l'agent **doit gravir rigoureusement chaque échelon** dans l'ordre strict suivant :

1. **YAGNI (You Aren't Gonna Need It)** :
   *Ce composant / cette fonction doit-il réellement exister ?*
   Si le besoin est hypothétique, futuriste ou prématuré : **abandonner immédiatement**.

2. **Réutilisation Interne** :
   *Le pattern, helper ou utilitaire existe-t-il déjà dans le codebase ?*
   Réutiliser en priorité le code existant et tester les fonctions partagées.

3. **Bibliothèque Standard** :
   *La bibliothèque standard du runtime (Python stdlib, Node.js core, Go stdlib) résout-elle le problème ?*
   Privilégier `ast`, `json`, `re`, `subprocess`, `pathlib` au lieu d'ajouter des dépendances tierces.

4. **Capacité Native de la Plateforme** :
   *Le système d'exploitation, Kubernetes, Traefik ou le navigateur fournissent-ils déjà cette fonction ?*
   (Ex: Ingress routing plutôt qu'un routeur applicatif personnalisé ; forward-auth plutôt qu'un serveur auth bespoke).

5. **Dépendance Déjà Installée** :
   *Une bibliothèque déjà déclarée dans les locks du projet (`tools.lock.json`, `package.json`, `requirements.txt`) couvre-t-elle le besoin ?*
   Interdiction formelle d'ajouter un nouveau package externe sans validation architecturale préalable.

6. **Simplicité Maximale** :
   *Peut-on l'écrire en quelques lignes claires plutôt qu'une hiérarchie de classes ou une factory abstraite ?*
   Une fonction simple de 10 lignes lisibles est préférable à une classe abstraite avec 3 interfaces.

7. **Écriture Minimale Définitive** :
   *Uniquement si les étapes 1 à 6 ont été validées :*
   Écrire la quantité absolue minimale de code nécessaire pour satisfaire la recette et les tests.

---

## Modes d'Application

- **Mode Standard (Défaut)** :
  Appliquer l'échelle de décision à chaque instruction de modification de code ou de création de fichier.
- **Mode Revue / Audit** :
  Examiner un module pour identifier le code mort, les dépendances inutilisées et les abstractions excessives. Proposer des simplifications mesurées.

---

## Intégration ArcIA & Tokenmaxing

Dans ArcIA, Ponytail agit en synergie directe avec :
- **Tokenmaxing** : En limitant le volume de code écrit et les traces de débogage, il réduit drastiquement les tokens consommés par Hermes.
- **Superpowers (TDD & Systematic Debugging)** : Ponytail s'assure que le test guide l'implémentation minimale requise pour faire passer le test au vert.
