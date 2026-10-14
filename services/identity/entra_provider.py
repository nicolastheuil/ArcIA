"""Native Hermes OIDC provider, restricted to the explicitly enrolled test owner."""
import os
from uuid import UUID
from hermes_cli.dashboard_auth import InvalidCodeError
from plugins.dashboard_auth.self_hosted import SelfHostedOIDCProvider


def authorize_entra_claims(claims, tenant, owner):
    try:
        expected_tenant=str(UUID(tenant));expected_owner=str(UUID(owner))
        actual_tenant=str(UUID(claims['tid']));actual_owner=str(UUID(claims['oid']))
    except (ValueError,TypeError,KeyError,AttributeError):
        raise InvalidCodeError('ENTRA_TEST_IDENTITY_REQUIRED') from None
    if actual_tenant!=expected_tenant or actual_owner!=expected_owner:
        raise InvalidCodeError('ENTRA_TEST_OWNER_REFUSED')
    if claims.get('iss')!='https://login.microsoftonline.com/'+expected_tenant+'/v2.0':
        raise InvalidCodeError('ENTRA_TEST_ISSUER_REFUSED')
    return claims


class ArcIAEntraTestProvider(SelfHostedOIDCProvider):
    name='entra'
    display_name='Microsoft Entra ID'

    def __init__(self,*,tenant,owner,**kwargs):
        self.tenant=str(UUID(tenant));self.owner=str(UUID(owner))
        super().__init__(issuer='https://login.microsoftonline.com/'+self.tenant+'/v2.0',
                         scopes='openid profile email offline_access',id_token_leeway=0,**kwargs)

    def _verify_id_token(self,token):
        claims=super()._verify_id_token(token)
        return authorize_entra_claims(claims,self.tenant,self.owner)

    # The native base class aliases this method; bind our guard on both paths.
    _claims_for=_verify_id_token


def register(ctx):
    required=('ARCIA_ENTRA_TENANT_ID','ARCIA_ENTRA_CLIENT_ID','ARCIA_ENTRA_OWNER_OBJECT_ID','ARCIA_ENTRA_CLIENT_SECRET')
    if not all(os.environ.get(key) for key in required):
        raise ValueError('ENTRA_TEST_PROTECTED_ENROLLMENT_REQUIRED')
    ctx.register_dashboard_auth_provider(ArcIAEntraTestProvider(
        tenant=os.environ['ARCIA_ENTRA_TENANT_ID'],owner=os.environ['ARCIA_ENTRA_OWNER_OBJECT_ID'],
        client_id=os.environ['ARCIA_ENTRA_CLIENT_ID'],client_secret=os.environ['ARCIA_ENTRA_CLIENT_SECRET']))
