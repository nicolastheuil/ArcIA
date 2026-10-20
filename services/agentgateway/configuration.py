"""Séparer le bootstrap de qualification de la migration d'une instance."""


def deployment_profile(config):
    if 'gateway' not in config:
        return 'legacy'
    gateway = config['gateway']
    if not isinstance(gateway, dict) or gateway.get('implementation') != 'agentgateway':
        raise ValueError('gateway.implementation doit désigner agentgateway.')
    if set(gateway) - {'implementation', 'mode'}:
        raise ValueError('Paramètre gateway non pris en charge par le schéma de qualification.')
    if gateway.get('mode') != 'qualification_only':
        raise ValueError('agentgateway reste en qualification_only avant recette et migration.')
    return 'agentgateway'


def require_qualified_deployment(config):
    if deployment_profile(config) == 'agentgateway':
        raise ValueError('agentgateway : qualification synthétique uniquement ; migration complète non qualifiée. '
                         'Utilisez scripts/qualify_gateway_stack.py ; aucun déploiement historique déclenché.')
