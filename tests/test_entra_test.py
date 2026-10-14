import copy
import importlib.util
import json
from pathlib import Path
import socket
import sys
import threading
from types import ModuleType,SimpleNamespace
import unittest
from unittest.mock import patch
import yaml

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import entra_deploy

# Test the ArcIA authorization layer while the native verifier owns JWT validation.
auth=ModuleType('hermes_cli.dashboard_auth')
auth.InvalidCodeError=type('InvalidCodeError',(ValueError,),{})
native=ModuleType('plugins.dashboard_auth.self_hosted')


class NativeFixture:
    def __init__(self,**kwargs):self.kwargs=kwargs
    def _verify_id_token(self,token):
        if not isinstance(token,dict):raise auth.InvalidCodeError('NATIVE_TOKEN_REFUSED')
        return token


native.SelfHostedOIDCProvider=NativeFixture
spec=importlib.util.spec_from_file_location('entra_authorization_under_test',ROOT/'services/identity/entra_provider.py')
provider=importlib.util.module_from_spec(spec)
with patch.dict(sys.modules,{'hermes_cli.dashboard_auth':auth,'plugins.dashboard_auth.self_hosted':native}):
    spec.loader.exec_module(provider)
spec=importlib.util.spec_from_file_location('entra_egress_under_test',ROOT/'services/identity/entra_egress.py')
egress=importlib.util.module_from_spec(spec);spec.loader.exec_module(egress)


class EntraAuthorizationTests(unittest.TestCase):
    tenant='12345678-1234-1234-1234-123456789abc'
    owner='23456789-1234-1234-1234-123456789abc'

    def setUp(self):
        self.claims={'tid':self.tenant,'oid':self.owner,'sub':'application-pairwise-subject',
                     'iss':'https://login.microsoftonline.com/'+self.tenant+'/v2.0'}

    def test_test_owner_is_selected_by_tenant_and_object_id_not_email(self):
        self.assertEqual(provider.authorize_entra_claims(dict(self.claims,email='mutable@example.invalid'),self.tenant,self.owner)['oid'],self.owner)
        for key in ('oid','tid','iss'):
            invalid=dict(self.claims);invalid[key]='34567890-1234-1234-1234-123456789abc'
            with self.assertRaises(ValueError):provider.authorize_entra_claims(invalid,self.tenant,self.owner)

    def test_missing_and_malformed_identity_fail_closed(self):
        for key in ('tid','oid'):
            for value in (None,'',{},'not-a-guid'):
                with self.assertRaises(ValueError):provider.authorize_entra_claims(dict(self.claims,**{key:value}),self.tenant,self.owner)

    def test_native_verification_is_used_on_login_and_session_readback(self):
        instance=provider.ArcIAEntraTestProvider(tenant=self.tenant,owner=self.owner,client_id=self.tenant,client_secret='synthetic-only')
        self.assertEqual(instance.kwargs['scopes'],'openid profile email offline_access')
        self.assertEqual(instance.kwargs['id_token_leeway'],0)
        for method in (instance._verify_id_token,instance._claims_for):
            self.assertEqual(method(self.claims),self.claims)
            with self.assertRaisesRegex(ValueError,'NATIVE_TOKEN_REFUSED'):method('unverified token')
            with self.assertRaisesRegex(ValueError,'OWNER_REFUSED'):method(dict(self.claims,oid=self.tenant))

    def test_registration_requires_all_protected_fields(self):
        context=SimpleNamespace(register_dashboard_auth_provider=lambda value:self.fail('incomplete registration'))
        with patch.dict('os.environ',{},clear=True):
            with self.assertRaisesRegex(ValueError,'ENROLLMENT_REQUIRED'):provider.register(context)


class EntraRendererTests(unittest.TestCase):
    def setUp(self):
        self.lock=json.loads((ROOT/'versions.lock.yaml').read_text(encoding='utf-8'))
        self.config=json.loads((ROOT/'examples/synthetic/instance.json').read_text(encoding='utf-8'))
        self.enrolled={'operation_id':'synthetic-operation','tenant_id':EntraAuthorizationTests.tenant,
                       'client_id':EntraAuthorizationTests.tenant,'owner_object_id':EntraAuthorizationTests.owner,'client_secret':'synthetic-only-secret'}
        self.admin={'username':'admin','password':'synthetic-only-password','password_salt':'c3ludGhldGljLXNhbHQxNg==','session_secret':'synthetic-only-signing'}

    def render(self):return entra_deploy.payload(self.lock,self.config,self.admin,self.enrolled,'synthetic-operation')

    def test_canary_has_its_own_state_and_native_plugin_without_keycloak(self):
        before=copy.deepcopy(self.lock);result=self.render();docs=result['documents']
        self.assertEqual(self.lock,before)
        self.assertEqual({d['metadata']['namespace'] for d in docs if 'namespace' in d['metadata']},{entra_deploy.NS})
        self.assertEqual(result['job']['metadata']['namespace'],entra_deploy.NS)
        raw=json.dumps(docs);self.assertFalse('keycloak' in raw);self.assertFalse('arcia-hermes.svc' in raw)
        spec=result['deployment']['spec']['template']['spec']
        self.assertFalse(spec['automountServiceAccountToken'])
        self.assertEqual(result['deployment']['spec']['strategy']['type'],'Recreate')
        self.assertIn('entra-plugin',{v['name'] for v in spec['volumes']})

    def test_secrets_are_only_in_named_secrets(self):
        for doc in self.render()['documents']:
            if doc['kind']!='Secret':
                self.assertNotIn(self.enrolled['client_secret'],json.dumps(doc))
                self.assertNotIn(self.admin['password'],json.dumps(doc))

    def test_canary_cannot_call_cloud_models_directly_or_through_auth_relay(self):
        docs=self.render()['documents']
        policy=next(d for d in docs if d['kind']=='NetworkPolicy' and d['metadata']['name']=='hermes-auth-only')
        self.assertNotIn('ipBlock',json.dumps(policy))
        self.assertEqual(policy['spec']['egress'][1]['ports'],[{'port':8088,'protocol':'TCP'}])
        config=next(d for d in docs if d['kind']=='ConfigMap' and d['metadata']['name']=='hermes-pilot-config')
        values=yaml.safe_load(config['data']['config.yaml'])
        self.assertEqual(values['model']['default'],'qualification-disabled')
        self.assertFalse(values['platform']['cloud_calls_enabled'])
        self.assertEqual(values['plugins']['enabled'],['arcia-entra-test'])

    def test_wrong_operation_or_extra_local_account_is_refused(self):
        with self.assertRaisesRegex(ValueError,'ENROLLMENT_SCOPE'):
            entra_deploy.payload(self.lock,self.config,self.admin,self.enrolled,'different-operation')
        with self.assertRaisesRegex(ValueError,'SINGLE_LOCAL_ADMIN'):
            entra_deploy.payload(self.lock,self.config,dict(self.admin,username='second-user'),self.enrolled,'synthetic-operation')

    def test_prefix_and_immutable_config_agree(self):
        result=self.render();docs=result['documents']
        config=next(d for d in docs if d['kind']=='ConfigMap' and d['metadata']['name']=='hermes-pilot-config')['data']
        immutable=next(d for d in docs if d['kind']=='ConfigMap' and d['metadata']['name'].startswith('hermes-config-'))
        self.assertEqual(config,immutable['data']);self.assertTrue(immutable['immutable'])
        self.assertTrue(yaml.safe_load(config['config.yaml'])['dashboard']['public_url'].endswith('/entra-test'))
        route=entra_deploy.ingress_route('10.43.0.10')
        self.assertIn('proxy_set_header X-Forwarded-Prefix /entra-test;',route)
        self.assertNotIn('keycloak',route)


class EntraEgressTests(unittest.TestCase):
    def test_only_the_exact_microsoft_tls_authority_is_accepted(self):
        self.assertEqual(egress.destination('CONNECT login.microsoftonline.com:443 HTTP/1.1'),(egress.HOST,443))
        for value in ('CONNECT api.openai.com:443 HTTP/1.1','CONNECT login.microsoftonline.com:80 HTTP/1.1',
                      'CONNECT login.microsoftonline.com.evil.invalid:443 HTTP/1.1','GET / HTTP/1.1',
                      'CONNECT 127.0.0.1:443 HTTP/1.1','CONNECT user@login.microsoftonline.com:443 HTTP/1.1'):
            with self.assertRaises(ValueError):egress.destination(value)

    def test_real_http_connection_denies_unapproved_destination_without_upstream(self):
        with egress.Relay(('127.0.0.1',0),egress.Handler) as server:
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                with patch.object(egress.socket,'getaddrinfo',side_effect=AssertionError('must not resolve')):
                    with socket.socket() as connection:
                        connection.settimeout(3);connection.connect(server.server_address)
                        connection.sendall(b'CONNECT api.openai.com:443 HTTP/1.1\r\n\r\n')
                        self.assertIn(b'403 Forbidden',connection.recv(4096))
            finally:server.shutdown();thread.join()


if __name__=='__main__':unittest.main()
