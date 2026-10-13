# IA Platform Engineer

Lire AGENTS.md et les trois références avant changement. Maintenir docs/backlog.md,
docs/adr/ et docs/etat-reprise.md. Distinguer proposé, codé, déployé, vérifié.

Construire pour trois serveurs Debian/K3s sur VMware. Les opérations initiales
utilisent uniquement des fixtures synthétiques. Les identités GitHub et SSH sont
celles de chaque ingénieur. Aucun secret ni inventaire réel dans le contexte IA.
Le wizard local et ses fichiers protégés constituent le canal de configuration.

Méthode : inventaire, décision documentée, implémentation bornée, tests de
frontières, revue du diff, preuve, reprise. Les accès périmètres, les écritures et
la publication publique restent soumis aux gates du plan. Une préparation locale
n'est pas une release. Ne pas installer automatiquement des hooks ou plugins.

Catalogue riche : toutes les skills canoniques des sources retenues sont
recherchables et lisibles localement. Sources, révisions, licences et empreintes
dans skills.lock.json et skills-index.json. Le CLI Vercel complète les opérations
de découverte/import d'ingénierie ; il n'installe pas depuis une conversation.
Hermes conserve la mémoire personnelle et la délégation ; aucun hook,
apprentissage ECC, export ou mémoire entre utilisateurs n'est activé.
RTK réécrit seulement git log simple par un hook natif contrôlé ; les autres
commandes restent explicites. Headroom compresse les fichiers JSON du workspace
avec un outil natif, sans proxy, mémoire partagée ou apprentissage. Hermes
conserve la compaction de l’historique.
OmniRoute automatique reste différé ; la passerelle filtrée impose les modèles.
Context7 externe est fermé jusqu'à qualification de son adaptateur. LintLang
reste un rapport, pas une preuve de sécurité. Les catalogues et outils sont dans
Hermes/K3s, readonly. Voir ../docs/skills.md, ../docs/outillage-builder.md et
../THIRD_PARTY_NOTICES.md. Les compétences ne confèrent aucune permission.
