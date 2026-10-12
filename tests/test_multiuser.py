import base64
import copy
import json
from pathlib import Path
import sys
import unittest
import asyncio
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import multiuser_deploy
import node_multiuser
sys.path.insert(0,str(ROOT/'services/multiuser'))
from dashboard_boundary import Revocations,SessionRevocation

class MultiuserBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.lock=json.loads((ROOT/'versions.lock.yaml').read_text(encoding='utf-8'))
        self.config=json.loads((ROOT/'examples/synthetic/instance.json').read_text(encoding='utf-8'))
        self.main={'username':'synthetic-a','password':'synthetic-only-a','password_salt':base64.b64encode(b'synthetic-salt16').decode(),
            'session_secret':'synthetic-secret-a','tls_certificate':'PUBLIC_CERT','tls_private_key':'synthetic-TLS-key'}
        self.second={**self.main,'username':'synthetic-b','password':'synthetic-only-b','session_secret':'synthetic-secret-b'}

    def test_second_runtime_does_not_inherit_first_auth_or_tls_key(self):
        value=multiuser_deploy.payload(self.lock,self.config,self.main,self.second)
        docs=value['documents'];raw=json.dumps(docs)
        for forbidden in (self.main['session_secret'],self.main['tls_private_key'],self.main['password'],self.second['password']):
            self.assertNotIn(forbidden,raw)
        self.assertNotIn('"namespace": "arcia-hermes"',raw)
        self.assertEqual({d['metadata']['namespace'] for d in docs if 'namespace' in d['metadata']},{multiuser_deploy.SECOND})
        spec=value['deployment']['spec']['template']['spec']
        self.assertFalse(spec['automountServiceAccountToken'])
        self.assertEqual(value['deployment']['spec']['strategy']['type'],'Recreate')
        self.assertEqual(len([v for v in spec['volumes'] if 'persistentVolumeClaim' in v]),2)

    def test_trusted_prefix_and_immutable_config_match(self):
        value=multiuser_deploy.payload(self.lock,self.config,self.main,self.second)
        docs=value['documents'];stable=next(d for d in docs if d['kind']=='ConfigMap' and d['metadata']['name']=='hermes-pilot-config')
        immutable=next(d for d in docs if d.get('immutable'))
        self.assertEqual(stable['data'],immutable['data'])
        self.assertIn('/qualification-b',stable['data']['config.yaml'])
        nginx=next(d for d in value['ingress'] if d['kind']=='ConfigMap')['data']['nginx.conf']
        self.assertIn('proxy_set_header X-Forwarded-Prefix /qualification-b;',nginx)
        self.assertIn('proxy_set_header X-Forwarded-Prefix "";',nginx)
        self.assertIn('resolver ',nginx)

    def test_foreign_runtime_is_refused_before_install_mutates(self):
        foreign=json.dumps({'metadata':{'annotations':{'arcia.io/operation-id':'other'}}})
        with patch.object(node_multiuser,'kube',return_value=foreign) as kube:
            with self.assertRaisesRegex(ValueError,'MULTIUSER_FOREIGN_RESOURCE'):
                node_multiuser.install({'operation_id':'synthetic-operation'})
            self.assertEqual(kube.call_count,1)

    def test_revocation_is_durable_and_stores_no_raw_cookie(self):
        with tempfile.TemporaryDirectory() as folder:
            path=str(Path(folder)/'revocations.sqlite');store=Revocations(path)
            store.revoke('synthetic-access-token',time.time()+300)
            self.assertTrue(Revocations(path).contains('synthetic-access-token'))
            self.assertFalse(store.contains('other-synthetic-token'))
            self.assertNotIn(b'synthetic-access-token',Path(path).read_bytes())
            with self.assertRaises(ValueError):store.revoke('invalid-expiry',time.time()-1)

    def test_logout_cookie_and_bearer_replay_rejected_but_login_remains_public(self):
        async def scenario(path):
            calls=[];sent=[]
            async def app(scope,receive,send):
                calls.append(scope['path']);await send({'type':'http.response.start','status':200,'headers':[]})
            async def receive():return {'type':'http.request','body':b''}
            async def send(message):sent.append(message)
            middleware=SessionRevocation(app,path,lambda token:SimpleNamespace(expires_at=time.time()+300))
            await middleware({'type':'http','path':'/auth/logout','method':'POST','headers':[(b'cookie',b'__Host-hermes_session_at=synthetic-token')]},receive,send)
            for headers in ([(b'cookie',b'__Host-hermes_session_at=synthetic-token')],[(b'authorization',b'Bearer synthetic-token')]):
                sent.clear();await middleware({'type':'http','path':'/api/config','method':'GET','headers':headers},receive,send)
                self.assertEqual(sent[0]['status'],401)
            sent.clear();await middleware({'type':'http','path':'/login','method':'GET','headers':[(b'cookie',b'__Host-hermes_session_at=synthetic-token')]},receive,send)
            self.assertEqual(sent[0]['status'],200)
            self.assertEqual(calls,['/auth/logout','/login'])
        with tempfile.TemporaryDirectory() as folder:asyncio.run(scenario(str(Path(folder)/'revocations.sqlite')))

if __name__=='__main__':unittest.main()
