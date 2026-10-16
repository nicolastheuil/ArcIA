# ADR 0018 — Plan borné de réparation de la sortie Keycloak

Statut : Remplacé le 15 octobre 2026 par le socle ArcIA v0.2 (abandon de Keycloak au profit d'OAuth2-Proxy et Microsoft Entra ID).
Règle historique déployée lors de la phase de transition.

Actualisation documentaire du 14 octobre : le snapshot `/32` ci-dessous est
historique, remplacé sur le pilote par l’option explicite de sortie publique
IPv4 TCP/443 et le filtrage amont. Consulter l’[état courant](../etat-reprise.md)
avant toute reprise ; cet ADR conserve la décision et les limites du correctif
initial et n’autorise pas sa réapplication.

Les sondes réelles établissent une sortie IPv4/TLS fonctionnelle sur les trois
VM et un refus des connexions Microsoft par la chaîne de politique de Keycloak.
Les VM et ce Pod n'ont aucune route IPv6. Le réseau de l'organisation est en
sortie directe, sans proxy administré.

Préparer une NetworkPolicy additive `keycloak-microsoft-egress`, réservée à
`app=keycloak` dans `arcia-identity`, TCP/443 et adresses IPv4 publiques `/32`
résolues pour `login.microsoftonline.com` et `graph.microsoft.com`. Aucun
changement de deny-all, de routage K3s, de credential ou de fournisseur. Une
préférence JVM IPv4 n'est pas incluse : le refus IPv4 est le premier obstacle
mesuré, et aucune reproduction du choix d'adresse de Java n'a été exécutée.

Ce plan est une réparation de qualification à vérifier, pas une architecture
durable avec filtrage de noms. Une IP Microsoft peut être partagée ; le filtre
L3 ne garantit pas le hostname et TLS conserve sa validation de nom. Une
rotation DNS peut interrompre le login ; l'expiration du plan après dix minutes
ne supprime pas une éventuelle règle Kubernetes déjà appliquée. Pas de refresh
automatique sans procédure contrôlée. Une solution durable doit couvrir ces
limites, par un mécanisme FQDN/egress adapté et qualifié.

Le plan collecte trois résolutions sur chacun des trois nœuds, puis une
résolution au moment de la préparation finale. Il lie opération, Deployment UID/resourceVersion, état antérieur de la
règle, nouvelles adresses, document exact et hash. Une propriété étrangère,
destination supplémentaire, IP non publique/IPv6/CIDR ou dérive de cible est
refusée. La commande de plan n'appelle jamais apply.
L'approbation Teams côté serveur exigée par AGENTS.md n'est pas implémentée ;
aucun booléen local ne la simule. Le propriétaire doit préciser toute exception
administrative à cette exigence avant application exceptionnelle.

Le propriétaire a explicitement autorisé l'exception « pour ce correctif
uniquement » dans le chat. L'action distincte de réparation exige le hash
exact du plan autorisé, sa fraîcheur et une cible inchangée ; elle utilise
create ou replace avec précondition resourceVersion, puis relit la règle.
Elle enregistre `operator_exception_for_named_repair` et
`teams_approval_verified=false`. Cette exception n'est pas une autorisation
permanente de nouvelles ouvertures ou de refresh automatique.

Le renderer local de l'identité reste fermé à Internet par défaut. L'étape de
plan est opt-in dans Audit, hors Fresh/Reconcile/Verify. Une inspection Audit
contrôle la borne de la règle et détecte des IP DNS manquantes, sans élargir
la règle. Locks, couverture,
runbook et handoff accompagnent le code ; aucun nouveau composant ou secret.

[État courant](../etat-reprise.md),
[NetworkPolicy Kubernetes](https://kubernetes.io/docs/concepts/services-networking/network-policies/),
[endpoints Microsoft](https://learn.microsoft.com/en-us/microsoft-365/enterprise/urls-and-ip-address-ranges).
