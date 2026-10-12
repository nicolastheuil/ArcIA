"""Create a private instance-code repository. Credentials never leave this process."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import urllib.request
import urllib.error

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--name',required=True);parser.add_argument('--directory',required=True)
    args=parser.parse_args()
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{2,63}',args.name):raise ValueError('REPOSITORY_NAME')
    directory=Path(args.directory).resolve()
    if directory.exists():raise ValueError('NEW_DIRECTORY_REQUIRED')
    raw=subprocess.run(['git','credential','fill'],input=b'protocol=https\nhost=github.com\n\n',capture_output=True,check=True,timeout=30).stdout
    credential=dict(line.split('=',1) for line in raw.decode().splitlines() if '=' in line)
    def api(method,path,body=None):
        request=urllib.request.Request('https://api.github.com'+path,data=json.dumps(body).encode() if body is not None else None,
            headers={'Authorization':'Bearer '+credential['password'],'Accept':'application/vnd.github+json','User-Agent':'arcia-instance-bootstrap','Content-Type':'application/json'},method=method)
        with urllib.request.urlopen(request,timeout=30) as response:return json.load(response)
    user=api('GET','/user');owner=user['login']
    try:
        repository=api('GET','/repos/'+owner+'/'+args.name)
        if not repository['private']:raise ValueError('EXISTING_REPOSITORY_MUST_BE_PRIVATE')
    except urllib.error.HTTPError as exc:
        if exc.code!=404:raise
        repository=api('POST','/user/repos',{'name':args.name,'private':True,'auto_init':False,
            'description':'Customisations et configuration privee d’une instance de la plateforme IA agentique ArcIA.'})
    # Existing nonempty repositories are never overwritten.
    try:api('GET','/repos/'+owner+'/'+args.name+'/commits?per_page=1');raise ValueError('EMPTY_REPOSITORY_REQUIRED')
    except urllib.error.HTTPError as exc:
        if exc.code!=409:raise
    directory.mkdir(parents=True)
    files={
        'README.md':'''# Instance ArcIA

Ce dépôt contient les adaptations d’une instance de la plateforme IA agentique d’entreprise [arcia-harness](https://github.com/'''+owner+'''/arcia-harness).
Le harness porte le socle générique, les outils, les contrôles de confidentialité et le bootstrap ; ce dépôt porte les usages propres à l’organisation.

| Dossier | Contenu attendu |
|---|---|
| `use-cases/` | Besoins, populations et critères de recette de chaque usage. |
| `corpora/` | Manifestes de sources, droits, classification et règles d’ingestion. |
| `connectors/` | Adaptateurs spécifiques et contrats d’API, sans identifiants. |
| `instance/` | Surcharges d’instance et références de secrets externes. |
| `docs/` | Décisions, exploitation et reprise propres à l’organisation. |

Les données ingérées définiront les usages réels : recherche documentaire, assistance, analyse, production de livrables ou actions approuvées.
Les droits sont vérifiés côté serveur, par utilisateur et périmètre ; un agent ne décide pas de son propre accès.

## Démarrage

Le dépôt est initialisé sur `main`. Les personnalisations ne sont pas encore développées ni déployées.
La version du harness sera fixée dans `instance/harness-reference.json` après publication de la prochaine livraison du socle.
Ne pas copier les inventaires, domaines ou comptes dans le dépôt générique.

## Données privées et récupération

Aucun secret, clé privée, token, kubeconfig, contrat ou document confidentiel en clair dans Git, même privé.
Les corpus restent dans le stockage privé de l’instance. Les configurations sensibles et exports autorisés sont chiffrés avant Git avec des clés externes.
Les fichiers `.example.json` ne contiennent que des références et des valeurs synthétiques. Les clés de récupération sont conservées hors dépôt.
''',
        'AGENTS.md':'''# Adaptations d’instance ArcIA

- Le socle réutilisable reste dans arcia-harness ; ce dépôt porte les adaptations de cette organisation.
- Lire README.md et docs/etat-reprise.md avant toute modification ou déploiement.
- Développer et livrer directement sur main selon l’instruction du propriétaire.
- Déployer seulement sur la cible protégée désignée, jamais installer les outils applicatifs sur le poste de contrôle.
- Secrets et inventaires passent par un programme protégé ; aucune valeur secrète au modèle.
- Corpus privés hors Git ; configurations sensibles chiffrées, clés externes.
- Qualifier sur des données synthétiques. Toute ouverture de données réelles exige une politique de droits et de sortie vérifiée côté serveur.
- Conserver les contrôles du harness ; aucune route fournisseur directe ni fallback contournant Presidio.
- Mettre à jour le bootstrap d’instance et l’état de reprise à chaque évolution. Distinguer codé, déployé et vérifié.
''',
        '.gitignore':'''# Private material belongs in external storage or encrypted bundles.
.env
.env.*
!.env.example
*.pem
*.key
*.pfx
*.p12
*.dpapi
*.kubeconfig
kubeconfig*
secrets/
private/
data/
backups/
*.pdf
*.docx
*.xlsx
*.db
*.sqlite*
__pycache__/
''',
        'docs/etat-reprise.md':'''# État de reprise

Dépôt privé initialisé ; personnalisations non commencées. Aucun document privé, secret ou inventaire réel importé.

Prochaines étapes : fixer la release du harness ; définir les premiers usages et populations ; décrire les sources et leurs ACL ; coder les connecteurs nécessaires ; qualifier puis intégrer au bootstrap d’instance.

Routage souhaité : OmniRoute automatique, puis OpenRouter free, puis OpenRouter auto. La qualification actuelle autorise uniquement les routes gratuites conformes ; le dernier repli reste soumis à une autorisation budgétaire future.
''',
        'instance/harness-reference.json':json.dumps({'repository':owner+'/arcia-harness','revision':None,'status':'awaiting_next_platform_delivery'},indent=2)+'\n',
        'instance/config.example.json':json.dumps({'schema_version':1,'instance_id':'synthetic-enterprise','harness_revision':'PIN_FULL_COMMIT_SHA',
            'private_configuration':'external-protected-reference','corpora':[],'connectors':[],'business_permissions_enabled':False},indent=2)+'\n'}
    for folder in ('use-cases','corpora','connectors'):
        files[folder+'/README.md']='# '+folder+'\n\nÀ définir lors du cadrage des premiers usages. Ne pas déposer de données privées en clair.\n'
    for relative,content in files.items():
        path=directory/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(content,encoding='utf-8',newline='\n')
    def git(*values):return subprocess.run(['git','-C',str(directory),*values],capture_output=True,check=True,timeout=120)
    git('init','-b','main');git('add','README.md','AGENTS.md','.gitignore','docs','instance','use-cases','corpora','connectors')
    git('commit','-m','Initialize private enterprise instance customizations')
    git('remote','add','origin',repository['clone_url']);git('push','-u','origin','main')
    verified=api('GET','/repos/'+owner+'/'+args.name)
    sha=git('rev-parse','HEAD').stdout.decode().strip()
    print(json.dumps({'status':'created','url':verified['html_url'],'private':verified['private'],'default_branch':verified['default_branch'],
        'directory':str(directory),'commit':sha,'raw_private_data_imported':False}))

if __name__=='__main__':
    try:main()
    except Exception as exc:print(json.dumps({'status':'blocked','error_type':type(exc).__name__}));raise SystemExit(2)
