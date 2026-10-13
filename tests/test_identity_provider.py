import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch


class InvalidCodeError(Exception):pass
class ProviderError(Exception):pass


def provider_module():
    auth=ModuleType('hermes_cli.dashboard_auth')
    auth.InvalidCodeError=InvalidCodeError;auth.ProviderError=ProviderError;auth.LoginStart=SimpleNamespace
    base=ModuleType('plugins.dashboard_auth.self_hosted')
    class Parent:
        def __init__(self,**kwargs):
            self._issuer=kwargs['issuer'];self._client_id=kwargs['client_id'];self._client_secret=kwargs['client_secret']
        def _get_jwks_client(self):return 'test-jwks'
    base.SelfHostedOIDCProvider=Parent
    shared=ModuleType('plugins.dashboard_auth._shared')
    for name in ('exchange_token','refresh_token_from','session_from_claims','verify_jwt'):
        setattr(shared,name,Mock())
    spec=importlib.util.spec_from_file_location('arcia_identity_test_provider',Path(__file__).resolve().parents[1]/'services/identity/provider.py')
    module=importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules,{'hermes_cli.dashboard_auth':auth,
                                'plugins.dashboard_auth.self_hosted':base,
                                'plugins.dashboard_auth._shared':shared}):spec.loader.exec_module(module)
    return module


class IdentityProviderTests(unittest.TestCase):
    def setUp(self):
        self.module=provider_module()
        self.provider=self.module.ArcIAIdentityProvider(owner='owner-a',issuer='https://id.example.invalid/identity/realms/arcia',
                                                      client_id='runtime-a',client_secret='private-fixture')
        self.claims={'sub':'owner-a','azp':'runtime-a','arcia_roles':['ArcIA.User']}
        self.module.verify_access_token=Mock(return_value=self.claims)

    def test_wrong_owner_client_or_role_is_refused(self):
        for patch_values in ({'sub':'owner-b'},{'azp':'runtime-b'},{'arcia_roles':[]}):
            claims={**self.claims,**patch_values}
            with self.assertRaises(InvalidCodeError):
                self.module.authorize_claims(claims,'owner-a','runtime-a')

    def test_active_session_uses_verified_signature_and_online_state(self):
        response=SimpleNamespace(status_code=200,json=lambda:{'sub':'owner-a'})
        with patch.object(self.module.httpx,'get',return_value=response) as call:
            self.assertEqual(self.provider._claims_for('token-fixture'),self.claims)
        self.assertFalse(call.call_args.kwargs['follow_redirects'])
        self.assertEqual(self.module.verify_access_token.call_args.kwargs['audience'],'runtime-a')

    def test_revoked_and_other_subject_online_state_is_refused(self):
        for state in ({},{'sub':'owner-b'}):
            response=SimpleNamespace(status_code=200,json=lambda:state)
            with patch.object(self.module.httpx,'get',return_value=response):
                with self.assertRaises(InvalidCodeError):self.provider._claims_for('token-fixture')

    def test_identity_failure_is_closed_and_diagnostics_do_not_echo_input(self):
        with patch.object(self.module.httpx,'get',side_effect=self.module.httpx.ConnectError('sensitive-fixture')):
            with self.assertRaisesRegex(ProviderError,'^ARCIA_IDENTITY_UNAVAILABLE$'):
                self.provider._claims_for('token-fixture')
        self.module.verify_access_token.side_effect=ProviderError('untrusted-claim-fixture')
        with self.assertRaisesRegex(ProviderError,'^ARCIA_IDENTITY_UNAVAILABLE$'):
            self.provider._claims_for('token-fixture')


if __name__=='__main__':unittest.main()
