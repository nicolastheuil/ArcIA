"""Per-runtime OIDC authentication with central, online session revocation.

Uses the pinned Hermes provider contract; never receives a realm-admin identity.
"""
import os
import hashlib
import httpx
from hermes_cli.dashboard_auth import InvalidCodeError, ProviderError, LoginStart
from plugins.dashboard_auth.self_hosted import SelfHostedOIDCProvider
from plugins.dashboard_auth._shared import (
    exchange_token, refresh_token_from, session_from_claims)


def verify_access_token(token, jwks_client, *, audience, issuer):
    import jwt
    try:
        key=jwks_client.get_signing_key_from_jwt(token)
    except jwt.PyJWKClientConnectionError:
        raise ProviderError('ARCIA_IDENTITY_UNAVAILABLE') from None
    except Exception:
        raise InvalidCodeError('ARCIA_TOKEN_REFUSED') from None
    try:
        return jwt.decode(token,key.key,algorithms=['RS256'],audience=audience,issuer=issuer,leeway=0,
                          options={'require':['exp','iat','aud','iss','sub']})
    except jwt.InvalidTokenError:
        raise InvalidCodeError('ARCIA_TOKEN_REFUSED') from None


def authorize_claims(claims, owner, client_id):
    if not owner or claims.get('sub') != owner:
        raise InvalidCodeError('ARCIA_RUNTIME_OWNER_REQUIRED')
    if claims.get('azp') != client_id:
        raise InvalidCodeError('ARCIA_RUNTIME_CLIENT_REQUIRED')
    if 'ArcIA.User' not in claims.get('arcia_roles', []):
        raise InvalidCodeError('ARCIA_USER_ROLE_REQUIRED')


class ArcIAIdentityProvider(SelfHostedOIDCProvider):
    name = 'arcia'
    display_name = 'Compte ArcIA ou SSO'

    def __init__(self, *, owner, **kwargs):
        super().__init__(**kwargs)
        if not owner:
            raise ValueError('ARCIA_RUNTIME_IDENTITY_REQUIRED')
        self._owner = owner

    def start_login(self, *, redirect_uri):
        start=super().start_login(redirect_uri=redirect_uri)
        verifier=start.cookie_payload['hermes_session_pkce'].split(';verifier=',1)[1]
        nonce=hashlib.sha256(verifier.encode()).hexdigest()
        return LoginStart(redirect_url=start.redirect_url+'&nonce='+nonce,cookie_payload=start.cookie_payload)

    def _claims_for(self, token):
        # Access tokens are audience-bound and revalidated online at each request.
        try:
            claims = verify_access_token(token, self._get_jwks_client(),
                                         audience=self._client_id, issuer=self._issuer)
        except InvalidCodeError:
            raise InvalidCodeError('ARCIA_TOKEN_REFUSED') from None
        except ProviderError:
            raise ProviderError('ARCIA_IDENTITY_UNAVAILABLE') from None
        authorize_claims(claims, self._owner, self._client_id)
        try:
            response = httpx.get(self._issuer + '/protocol/openid-connect/userinfo',
                headers={'Authorization':'Bearer '+token}, timeout=5, follow_redirects=False)
            if response.status_code in (401,403):
                raise InvalidCodeError('ARCIA_SESSION_INACTIVE')
            if response.status_code != 200:
                raise ProviderError('ARCIA_IDENTITY_UNAVAILABLE')
            current = response.json()
        except (httpx.RequestError, ValueError):
            raise ProviderError('ARCIA_IDENTITY_UNAVAILABLE') from None
        if current.get('sub') != self._owner:
            raise InvalidCodeError('ARCIA_SESSION_INACTIVE')
        return claims

    def _grant(self, data, *, bad_request_exc, headers=None, previous_refresh_token=''):
        disco = self._get_discovery()
        extra_data, extra_headers = self._token_endpoint_auth(disco)
        try:
            token, payload = exchange_token(disco['token_endpoint'], {**data, **extra_data},
                headers=extra_headers, bad_request_exc=bad_request_exc,
                idp='ArcIA', endpoint='ArcIA token endpoint', token_key='access_token',
                missing_msg='ARCIA_ACCESS_TOKEN_REQUIRED')
            # Validate ID token too, but never use an identity token as the session bearer.
            id_claims = self._verify_id_token(payload.get('id_token', ''))
            if data.get('grant_type')=='authorization_code':
                nonce=hashlib.sha256(data.get('code_verifier','').encode()).hexdigest()
                if id_claims.get('nonce')!=nonce:raise InvalidCodeError('ARCIA_NONCE_MISMATCH')
            claims = self._claims_for(token)
            if id_claims['sub'] != claims['sub']:
                raise InvalidCodeError('ARCIA_SUBJECT_MISMATCH')
            return self._session(token, refresh_token_from(payload, previous_refresh_token), claims)
        except (InvalidCodeError, ProviderError):
            raise bad_request_exc('ARCIA_LOGIN_REFUSED') from None

    def _session(self, token, refresh_token, claims):
        return session_from_claims(self.name, claims, access_token=token, refresh_token=refresh_token,
                                   display_name=str(claims.get('preferred_username', '')))


def register(ctx):
    issuer = os.environ.get('ARCIA_IDENTITY_ISSUER', '')
    if not issuer:
        return
    ctx.register_dashboard_auth_provider(ArcIAIdentityProvider(
        issuer=issuer, client_id=os.environ['ARCIA_IDENTITY_CLIENT_ID'],
        client_secret='',
        owner=os.environ['ARCIA_IDENTITY_OWNER_SUBJECT'], scopes='openid profile', id_token_leeway=0))
