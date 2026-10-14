"""Server-side route choice: standard auto, optional owner-bound overrides."""
import ipaddress
import re
import uuid

PERSONAL_ROLE='ArcIA.ProviderSelfService'
AUTO_MODES={'auto','auto/smart','auto/coding','auto/fast','auto/cheap','auto/offline'}


def validate_admin_policy(value):
    if set(value)-{'automatic_mode','lan_cidrs','personal_providers_enabled','personal_role','private_firewall_boundary','ip_https_enabled'}:
        raise ValueError('ROUTING_POLICY_FIELDS')
    if value.get('automatic_mode') not in AUTO_MODES:raise ValueError('ADMIN_AUTO_MODE_REQUIRED')
    if value.get('personal_role',PERSONAL_ROLE)!=PERSONAL_ROLE:raise ValueError('PERSONAL_ROLE_REQUIRED')
    if not isinstance(value.get('personal_providers_enabled',False),bool):raise ValueError('PERSONAL_SWITCH_INVALID')
    if not isinstance(value.get('private_firewall_boundary',False),bool):raise ValueError('FIREWALL_BOUNDARY_INVALID')
    if not isinstance(value.get('ip_https_enabled',False),bool):raise ValueError('IP_HTTPS_FLAG_INVALID')
    cidrs=value.get('lan_cidrs',[])
    if not cidrs or len(cidrs)>32:raise ValueError('EXPLICIT_LAN_REQUIRED')
    private=[ipaddress.ip_network(n) for n in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16')]
    for cidr in cidrs:
        # Explicit instance/operator declaration: only private VM/VIP endpoints
        # behind the LAN/VPN firewall; accept all source addresses there.
        if cidr=='0.0.0.0/0' and value.get('private_firewall_boundary') is True:continue
        net=ipaddress.ip_network(cidr,strict=True)
        if net.version!=4 or not any(net.subnet_of(parent) for parent in private):raise ValueError('PRIVATE_LAN_ONLY')
    return value


def authorize_personal(identity,policy,owner):
    if not policy.get('personal_providers_enabled') or PERSONAL_ROLE not in identity.get('arcia_roles',[]):
        raise PermissionError('PERSONAL_PROVIDER_ROLE_REQUIRED')
    if (identity.get('iss'),identity.get('sub'))!=tuple(owner):raise PermissionError('PROVIDER_OWNER_REQUIRED')
    if 'ArcIA.User' not in identity.get('arcia_roles',[]):raise PermissionError('ARCIA_USER_REQUIRED')


def select(identity,policy,enterprise,personal=None):
    """Identity comes from verified OIDC, never from a model body."""
    validate_admin_policy(policy)
    if not identity.get('iss') or not identity.get('sub') or 'ArcIA.User' not in identity.get('arcia_roles',[]):
        raise PermissionError('ARCIA_USER_REQUIRED')
    chosen=enterprise
    if personal:
        authorize_personal(identity,policy,(personal['issuer'],personal['subject']))
        chosen=personal
    mode=policy['automatic_mode']
    if mode not in AUTO_MODES:raise ValueError('ADMIN_AUTO_MODE_REQUIRED')
    if chosen.get('route_class') not in ('cloud','internal'):raise ValueError('ROUTE_CLASS_REQUIRED')
    connections=chosen.get('allowed_connections',[])
    if not connections or any(not isinstance(c,str) or not re.fullmatch(r'[a-f0-9-]{36}',c) for c in connections):
        raise ValueError('EXPLICIT_CONNECTION_SCOPE_REQUIRED')
    try:
        if any(str(uuid.UUID(c))!=c for c in connections):raise ValueError()
    except ValueError:raise ValueError('EXPLICIT_CONNECTION_SCOPE_REQUIRED') from None
    if not isinstance(chosen.get('credential_ref'),str) or not chosen['credential_ref'].startswith('secretref://routing/'):
        raise ValueError('PROTECTED_ROUTER_CREDENTIAL_REQUIRED')
    # One key may not mix local and cloud connections: every fallback shares
    # the same filter requirement. Cross-class failover requires reselection.
    if set(chosen.get('connection_classes',[]))!={chosen['route_class']}:
        raise ValueError('MIXED_CLASS_FALLBACK_REFUSED')
    return {'model':mode,'allowed_connections':list(connections),'credential_ref':chosen['credential_ref'],
            'presidio_required':chosen['route_class']=='cloud','route_class':chosen['route_class']}
