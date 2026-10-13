# Handoff — nouvelle vérification de l'authentification Microsoft 365

13 octobre 2026. Suite du [diagnostic réseau](handoff-2026-10-13-m365-broker-reseau.md).

## Symptôme et contrôles exécutés

L'utilisateur signale une attente puis « We are sorry… Unexpected error… »,
perçue avant la page Microsoft. Il confirme une infrastructure avec accès
Internet direct, sans proxy administré.

Inspection de la cible possédée via le transport SSH existant, confiance et
scopes DPAPI contrôlés. Keycloak disponible. Le fournisseur configuré est le
Microsoft prédéfini, activé, avec tenant spécifique et credential présent.
Cette présence ne valide pas le secret. Aucun changement de fournisseur,
tenant, credential, compte, permission ou ressource effectué.

Le parcours HTTPS réel `/portal/login` atteint la page de connexion avec HTTP
200 et un lien social. Ce lien retourne HTTP 303 vers
`login.microsoftonline.com`, sans erreur dans cette réponse. Le contrôleur
s'arrête à cette redirection : aucune connexion Microsoft ni utilisation de
compte utilisateur exécutée. Le symptôme avant Microsoft n'est donc pas
reproduit par cette sonde ; une session navigateur existante pourrait suivre
un autre parcours, ce qui reste une hypothèse.

Les journaux des trente dernières minutes (au plus 1 500 lignes et 512 Kio)
contiennent toujours le callback OAuth et « Network is unreachable », avec
l'hôte Microsoft de login. Les deux NetworkPolicies de sortie sélectionnant
Keycloak ne contiennent aucune règle TCP/443. Absence de marqueurs AADSTS,
`invalid_client`, UnknownHostException et SSLHandshakeException dans cet
échantillon ; aucune conclusion positive sur les credentials n'en découle.

Le blocage réseau est confirmé dans l'échantillon courant. L'accès Internet
des VM ne lève pas la restriction de sortie des Pods. IPv6/routage et réussite
de l'échange OAuth restent à vérifier après correction.

Preuves : [résultat assaini](qualification/2026-10-13-m365-broker-diagnostic.json).
Journaux, configuration et trace HTTP restent chiffrés hors dépôt dans
`m365-broker-current.dpapi`. Le contrôleur ponctuel a été exécuté depuis le
répertoire temporaire du poste ; il n'est pas une nouvelle étape du bootstrap.

## Correction à préparer et condition de déploiement

### Complément — tests réels du routage demandés par l'utilisateur

Les [preuves réseau](qualification/2026-10-13-m365-routing.json) précisent le
diagnostic précédent. Les trois VM ont chacune une route IPv4 par défaut et
réussissent les connexions TCP/TLS vers deux adresses IPv4 de chacun des deux
hôtes Microsoft (12/12, certificats validés). Les trois VM n'ont aucune route
IPv6 par défaut : les 12 essais IPv6 échouent avec ENETUNREACH/errno 101.

La sonde Keycloak utilise l'espace réseau du sandbox existant, identifié par
l'UID du Pod, sa ReplicaSet et le Deployment possédé. `nsenter` exécute le
Python système dans ce seul espace réseau, sans changer de namespace hôte,
sans modifier le conteneur et sans créer de Pod. Les adresses testées sont
les mêmes que celles vérifiées sur son nœud. Elle vérifie séparément les
requêtes DNS A/AAAA via le serveur DNS du Pod (4/4 réponses sans erreur),
l'accès TCP/5432 à son service PostgreSQL (réussi) et les routes du Pod.

Le Pod a une route IPv4 par défaut mais ses quatre connexions Microsoft IPv4
échouent avec ECONNREFUSED/errno 111. Pendant ces essais, la règle REJECT de
la chaîne `KUBE-POD-FW-*` identifiée pour l'IP de Keycloak augmente de quatre
paquets. Cela concorde avec les quatre refus et les NetworkPolicies sans
sortie TCP/443. Aucun compteur n'a été remis à zéro. L'IPv6 du Pod n'a pas de
route par défaut et renvoie ENETUNREACH pour les quatre essais IPv6.

Sur le nœud hébergeant Keycloak, le forwarding IPv4 est activé et les règles
Flannel POSTROUTING/MASQUERADE sont présentes. Un contrôle indépendant par
`kubectl exec` dans le Deployment `cloud-egress` possédé, déjà autorisé à
sortir, réussit deux connexions IPv4/TLS vers sa destination OpenRouter.
Aucune requête de modèle, authentification fournisseur ou donnée utilisateur
n'est envoyée : seules des connexions TCP et négociations TLS sont testées.

Conclusion bornée : Internet IPv4 des VM fonctionne et un chemin de sortie
Pod fonctionne ; le refus IPv4 propre à Keycloak est observé dans le pare-feu
K3s. Une panne globale de routage K3s n'est pas mise en évidence. L'absence de
route IPv6 est vérifiée, mais le choix/repli d'adresse exact de la JVM n'est
pas reproduit par ces sondes Python. Ne pas prétendre que tous les problèmes
réseau possibles sont exclus ni que forcer IPv4 lèverait le refus IPv4.

Preuves brutes chiffrées sous la racine privée :
`m365-routing-nodes.dpapi`, `m365-routing-pod.dpapi` et
`m365-routing-control.dpapi`. Les contrôleurs ponctuels restent dans le
répertoire temporaire local. Aucun changement de route, firewall, politique,
configuration JVM ou ressource Kubernetes effectué. Aucun login Microsoft
complet exécuté. Ces tests ne nécessitent aucune nouvelle étape de bootstrap.

La [documentation K3s](https://docs.k3s.io/networking/networking-services)
décrit l'application des NetworkPolicies par le contrôleur kube-router et
ses règles iptables. Les [options réseau](https://docs.k3s.io/networking/basic-network-options)
décrivent séparément IPv4/IPv6 et le masquerading Flannel. Sources officielles
consultées le 13 octobre 2026 ; aucune commande de désactivation/nettoyage des
politiques n'a été exécutée.

### Suite du plan

Le besoin est une sortie de Keycloak vers `login.microsoftonline.com:443` et
`graph.microsoft.com:443` (fournisseur Microsoft avec profil `/me`), en
préservant le deny-all et l'isolation d'Hermes. Aucun proxy d'entreprise n'est
disponible selon l'utilisateur. Le mécanisme de contrôle des destinations
reste à implémenter/qualifier ; aucun choix de nouveau service n'est déployé.
Ne pas ouvrir TCP/443 vers toutes les IP pour contourner ce manque.

La [documentation Kubernetes](https://kubernetes.io/docs/concepts/services-networking/network-policies/)
décrit les destinations IP/Pod/namespace et les règles de sortie additives.
La [configuration HTTP sortante Keycloak](https://www.keycloak.org/server/outgoinghttp)
prévoit un proxy sortant ; celui-ci est distinct du reverse proxy d'entrée.
Sources officielles consultées le 13 octobre 2026.

AGENTS.md exige un plan et une approbation Teams vérifiée côté serveur pour
une action externe à risque. Le mécanisme d'approbation est encore au backlog
L2 : aucune approbation serveur disponible n'a été constatée. La correction
d'ouverture réseau n'a donc pas été appliquée. Une réponse dans le chat ne
remplace pas cette vérification. Aucun test de connexion Microsoft complet,
réapplication ou rebuild neuf revendiqué.
