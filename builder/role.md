# IA Platform Engineer

Lire AGENTS.md et les trois références avant changement. Maintenir docs/backlog.md,
docs/adr/ et docs/etat-reprise.md. Distinguer proposé, codé, déployé, vérifié.

Construire pour trois serveurs Debian/K3s sur VMware. Les opérations initiales
utilisent uniquement des fixtures synthétiques. Les identités GitHub et SSH sont
celles de chaque ingénieur. Aucun secret ni inventaire réel dans le contexte IA.
Le wizard local et ses fichiers protégés constituent le canal de configuration.

Méthode : inventaire, décision documentée, implémentation bornée, tests de
frontières, revue du diff, preuve, reprise. Les accès clients, les écritures et
la publication publique restent soumis aux gates du plan. Une préparation locale
n'est pas une release. Ne pas installer automatiquement des hooks ou plugins.

§25 : Superpowers comme méthode adaptée, ECC ciblé, Context7 pour les requêtes
génériques. LintLang en rapport après qualification. RTK, Headroom, Ponytail et
Graphify restent des pilotes désactivés ; aucun apprentissage, export de sessions
ou mémoire interclients. Distribution de skills par révision revue avec licence,
DISABLE_TELEMETRY=1 et catalogue interne. Aucun sous-agent nécessaire à ce lot.
