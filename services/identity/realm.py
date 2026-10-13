"""Keycloak local identities are permanent; federation is additive and opt-in."""
REALM = 'arcia'
ROLES = ('ArcIA.User', 'ArcIA.Approver', 'ArcIA.Admin')


def realm_definition(operation):
    return {
        'realm': REALM, 'displayName': 'ArcIA', 'enabled': True,
        'attributes': {'arcia.operation-id': operation},
        'registrationAllowed': False, 'loginWithEmailAllowed': False,
        'duplicateEmailsAllowed': False, 'editUsernameAllowed': False,
        'resetPasswordAllowed': False, 'rememberMe': False,
        'bruteForceProtected': True, 'failureFactor': 5, 'waitIncrementSeconds': 60,
        'maxFailureWaitSeconds': 900, 'accessTokenLifespan': 120,
        'ssoSessionIdleTimeout': 1800, 'ssoSessionMaxLifespan': 28800,
        'revokeRefreshToken': True, 'refreshTokenMaxReuse': 0,
        'passwordPolicy': 'length(14) and notUsername and notEmail and passwordHistory(5)',
        'eventsEnabled': True, 'eventsExpiration': 2592000,
        'adminEventsEnabled': True, 'adminEventsDetailsEnabled': False,
        'roles': {'realm': [{'name': name} for name in ROLES]},
    }


def runtime_client(client_id, redirect_uri, secret):
    """Public per-runtime PKCE client, no service accounts or password grant."""
    return {
        'clientId': client_id, 'name': 'ArcIA personal runtime', 'protocol': 'openid-connect',
        'enabled': True, 'publicClient': True,
        'standardFlowEnabled': True, 'implicitFlowEnabled': False,
        'directAccessGrantsEnabled': False, 'serviceAccountsEnabled': False,
        'redirectUris': [redirect_uri], 'webOrigins': [],
        'attributes': {'pkce.code.challenge.method': 'S256'},
        'protocolMappers': [{
            'name': 'runtime-audience', 'protocol': 'openid-connect',
            'protocolMapper': 'oidc-audience-mapper',
            'config': {'included.client.audience': client_id,
                       'access.token.claim': 'true', 'id.token.claim': 'false'}},
            {'name': 'realm-roles', 'protocol': 'openid-connect',
             'protocolMapper': 'oidc-usermodel-realm-role-mapper',
             'config': {'claim.name': 'arcia_roles', 'multivalued': 'true',
                        'jsonType.label': 'String', 'access.token.claim': 'true',
                        'id.token.claim': 'true'}}],
    }
