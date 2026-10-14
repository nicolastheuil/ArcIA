import base64
import asyncio
import copy
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
from pathlib import Path
import sys
import time
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'services/identity'))
sys.path.insert(0,str(ROOT/'scripts'))
from slots import Slots,BindingError,CapacityError
from portal import Portal
import portal_deploy
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa


class MemoryAPI:
    def __init__(self):self.docs={};self.writes=[]
    def __call__(self,method,path,body=None):
        current=self.docs[path]
        if method=='GET':return copy.deepcopy(current)
        if body.get('metadata',{}).get('resourceVersion',current['metadata']['resourceVersion'])!=current['metadata']['resourceVersion']:raise ValueError('CONFLICT')
        self.writes.append((method,path,copy.deepcopy(body)))
        if method=='PUT':self.docs[path]=copy.deepcopy(body)
        else:
            for key,value in body.items():
                if key!='metadata':current.setdefault(key,{}).update(value)
        self.docs[path]['metadata']['resourceVersion']=str(int(current['metadata']['resourceVersion'])+1)
        return copy.deepcopy(self.docs[path])


class PersonalSlotTests(unittest.TestCase):
    def setUp(self):
        self.api=MemoryAPI();self.slots=[{'id':'p01','namespace':'arcia-user-p01','prefix':'/u/p01','job':'fixed-job'},
            {'id':'p02','namespace':'arcia-user-p02','prefix':'/u/p02','job':'fixed-job'}]
        self.store=Slots(self.api,self.slots,'https://identity.example.invalid','synthetic')
        for slot in self.slots:
            self.api.docs[self.store.resource(slot,'configmaps','slot-binding')]={
                'metadata':{'resourceVersion':'1','annotations':{'arcia.io/operation-id':'synthetic'}},'data':{'binding.json':'{}'}}
            self.api.docs[self.store.resource(slot,'secrets','arcia-oidc-runtime')]={
                'metadata':{'resourceVersion':'1'},'data':{'ARCIA_IDENTITY_OWNER_SUBJECT':''}}
            self.api.docs[self.store.resource(slot,'jobs','fixed-job','/apis/batch/v1')]={
                'metadata':{'resourceVersion':'1'},'spec':{'suspend':True}}
            for name in ('context7-docs','hermes-pilot'):
                self.api.docs[self.store.resource(slot,'deployments',name,'/apis/apps/v1')+'/scale']={
                    'metadata':{'resourceVersion':'1'},'spec':{'replicas':0}}

    def test_concurrent_first_logins_allocate_once(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            results=list(pool.map(lambda _:self.store.allocate('subject-a'),range(20)))
        self.assertEqual({r['id'] for r in results},{'p01'})
        self.assertEqual(len(self.api.writes),1)

    def test_new_uuid_does_not_inherit_deleted_account_slot(self):
        self.assertEqual(self.store.allocate('deleted-subject')['id'],'p01')
        self.assertEqual(self.store.allocate('recreated-same-login-new-subject')['id'],'p02')
        with self.assertRaises(CapacityError):self.store.allocate('third-subject')

    def test_foreign_slot_prevents_allocation(self):
        path=self.store.resource(self.slots[0],'configmaps','slot-binding')
        self.api.docs[path]['metadata']['annotations']['arcia.io/operation-id']='foreign'
        with self.assertRaises(BindingError):self.store.allocate('subject-a')
        self.assertFalse(self.api.writes)

    def test_secret_rebinding_is_refused_without_starting_workloads(self):
        self.store.allocate('subject-a')
        path=self.store.resource(self.slots[0],'secrets','arcia-oidc-runtime')
        self.api.docs[path]['data']['ARCIA_IDENTITY_OWNER_SUBJECT']=base64.b64encode(b'other-subject').decode()
        before=len(self.api.writes)
        with self.assertRaises(BindingError):self.store.progress('subject-a')
        self.assertEqual(len(self.api.writes),before)

    def test_fixed_installer_then_scale_only_after_completion(self):
        self.assertEqual(self.store.progress('subject-a'),{'phase':'installing'})
        job=self.store.resource(self.slots[0],'jobs','fixed-job','/apis/batch/v1')
        self.api.docs[job]['status']={'succeeded':1}
        self.assertEqual(self.store.progress('subject-a')['phase'],'starting')
        scales=[(path,body) for _,path,body in self.api.writes if path.endswith('/scale')]
        self.assertEqual(len(scales),2)
        self.assertTrue(all(body['spec']=={'replicas':1} for _,body in scales))
        before=len(self.api.writes);self.store.progress('subject-a')
        self.assertEqual(len(self.api.writes),before)

    def test_omitted_zero_scale_fields_do_not_block_new_space(self):
        self.store.progress('subject-a')
        job=self.store.resource(self.slots[0],'jobs','fixed-job','/apis/batch/v1')
        self.api.docs[job]['status']={'succeeded':1}
        for name in ('context7-docs','hermes-pilot'):
            path=self.store.resource(self.slots[0],'deployments',name,'/apis/apps/v1')+'/scale'
            self.api.docs[path].pop('spec')
        self.assertEqual(self.store.progress('subject-a')['phase'],'starting')


class PortalAuthTests(unittest.TestCase):
    def setUp(self):
        self.portal=Portal({'hostname':'synthetic.example.invalid','identity_internal':'http://keycloak.example.invalid/identity',
            'operation_id':'synthetic','slots':[]},b'synthetic-hmac-key',Mock())
        self.key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        self.portal.jwks=Mock();self.portal.jwks.get_signing_key_from_jwt.return_value=SimpleNamespace(key=self.key.public_key())
        self.claims={'iss':self.portal.issuer,'aud':'arcia-portal','azp':'arcia-portal','sub':'subject-a',
            'exp':int(time.time())+120,'iat':int(time.time()),'arcia_roles':['ArcIA.User']}
    def token(self,**claims):return jwt.encode({**self.claims,**claims},self.key,algorithm='RS256')

    def test_pkce_state_integrity_and_lifetime(self):
        value={'state':'synthetic-state','verifier':'synthetic-verifier','nonce':'synthetic-nonce','created':time.time()}
        signed=self.portal.sign(value)
        self.assertEqual(self.portal.verify_state(signed),value)
        with self.assertRaises(ValueError):self.portal.verify_state(signed[:-1]+('x' if signed[-1]!='x' else 'y'))
        with self.assertRaises(ValueError):self.portal.verify_state(self.portal.sign({**value,'created':time.time()-301}))

    def test_verified_signature_issuer_and_audience_are_required(self):
        self.assertEqual(self.portal.claims(self.token())['sub'],'subject-a')
        for claims in ({'aud':'other-client'},{'iss':'https://other.invalid'},{'exp':int(time.time())-1}):
            with self.assertRaises(jwt.InvalidTokenError):self.portal.claims(self.token(**claims))

    def test_online_state_and_application_role_are_required(self):
        with patch('portal.httpx.get',return_value=SimpleNamespace(status_code=200,json=lambda:{'sub':'subject-a','arcia_roles':['ArcIA.User']})):
            self.assertEqual(self.portal.authenticate(self.token())['sub'],'subject-a')
            with patch('portal.httpx.get',return_value=SimpleNamespace(status_code=200,json=lambda:{'sub':'subject-a','arcia_roles':[]})):
                with self.assertRaises(PermissionError):self.portal.authenticate(self.token())
        with patch('portal.httpx.get',return_value=SimpleNamespace(status_code=401)):
            with self.assertRaises(ValueError):self.portal.authenticate(self.token())
        self.assertNotEqual(self.portal.csrf('subject-a'),self.portal.csrf('subject-b'))


class PersonalRenderTests(unittest.TestCase):
    def setUp(self):
        self.lock=json.loads((ROOT/'versions.lock.yaml').read_text());self.lock['identity']['personal_slots']=2
        self.config=json.loads((ROOT/'examples/synthetic/instance.json').read_text())
        self.render=portal_deploy.payload(self.lock,self.config,{'tls_certificate':'synthetic','tls_private_key':'synthetic'},
            'synthetic-operation','10.43.0.99','192.0.2.3')

    def test_no_cluster_permissions_no_arbitrary_pods_no_agent_token(self):
        docs=self.render['documents']
        self.assertFalse(any(d['kind'] in ('ClusterRole','ClusterRoleBinding') for d in docs))
        for role in (d for d in docs if d['kind']=='Role'):
            for rule in role['rules']:
                self.assertTrue(rule['resourceNames']);self.assertNotIn('*',rule['verbs'])
                self.assertNotIn('create',rule['verbs']);self.assertNotIn('pods',rule['resources'])
                self.assertNotIn('deployments',rule['resources'])
        for deployment in (d for d in docs if d['kind']=='Deployment' and d['metadata']['namespace'].startswith('arcia-user-')):
            self.assertEqual(deployment['spec']['replicas'],0)
            self.assertFalse(deployment['spec']['template']['spec']['automountServiceAccountToken'])
        self.assertTrue(all(d['spec']['suspend'] for d in docs if d['kind']=='Job'))

    def test_each_slot_has_separate_rwop_claims_and_no_basic_auth(self):
        docs=self.render['documents'];claims=[d for d in docs if d['kind']=='PersistentVolumeClaim']
        self.assertEqual(len(claims),4)
        self.assertEqual(len({(d['metadata']['namespace'],d['metadata']['name']) for d in claims}),4)
        self.assertTrue(all(d['spec']['accessModes']==['ReadWriteOncePod'] for d in claims))
        containers=[c for d in docs if d['kind']=='Deployment' for c in d['spec']['template']['spec']['containers']]
        self.assertFalse(any('BASIC_AUTH' in env['name'] for c in containers for env in c.get('env',[])))
        self.assertFalse(any(d['metadata']['name']=='hermes-pilot-auth' for d in docs if d['kind']=='Secret'))
        conf=next(d for d in self.render['ingress'] if d['kind']=='ConfigMap')['data']['nginx.conf']
        self.assertIn('location = / { return 302 /portal/; }',conf)
        portal_config=json.loads(next(d for d in docs if d['kind']=='ConfigMap' and d['metadata']['name']=='portal-config')['data']['portal.json'])
        self.assertTrue(portal_config['identity_internal'].endswith('/identity/realms/arcia'))


class BoundHTTPTests(unittest.TestCase):
    def test_missing_or_unverifiable_provider_cannot_expose_personal_api(self):
        import os
        sys.path.insert(0,str(ROOT/'services/multiuser'))
        from dashboard_boundary import SessionRevocation
        async def exercise(path,cookie):
            sent=[];called=[]
            async def app(scope,receive,send):called.append(True)
            async def send(message):sent.append(message)
            with tempfile.TemporaryDirectory() as directory:
                boundary=SessionRevocation(app,str(Path(directory)/'revocations.db'),verifier=lambda token:None)
                scope={'type':'http','method':'GET','path':path,'headers':[(b'cookie',cookie.encode())]}
                await boundary(scope,None,send)
            return sent,called
        with patch.dict(os.environ,{'ARCIA_IDENTITY_ISSUER':'https://id.example.invalid',
            'HERMES_DASHBOARD_PUBLIC_URL':'https://synthetic.example.invalid/u/p01'}):
            for cookie in ('','hermes_session_at=synthetic-invalid'):
                sent,called=asyncio.run(exercise('/api/config',cookie))
                self.assertEqual(sent[0]['status'],401);self.assertFalse(called)
            sent,called=asyncio.run(exercise('/',''))
            self.assertEqual(sent[0]['status'],303)
            self.assertIn((b'location',b'https://synthetic.example.invalid/u/p01/auth/login?provider=arcia'),sent[0]['headers'])
            self.assertFalse(called)


if __name__=='__main__':unittest.main()
