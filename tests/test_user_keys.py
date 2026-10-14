import base64
import copy
import http.client
import json
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch,Mock
from http.server import ThreadingHTTPServer

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'services/routing'))
sys.path.insert(0,str(ROOT/'services/identity'))
sys.path.insert(0,str(ROOT/'scripts'))
from user_keys import UserKeys,KeyConfigError,ROLE,SECRET
from slots import Slots
from portal import Handler,Portal
import portal_deploy
import node_identity
from test_personal_portal import MemoryAPI


class UserKeyTests(unittest.TestCase):
    def setUp(self):
        self.api=MemoryAPI();self.issuer='https://synthetic.example.invalid/identity/realms/arcia'
        self.slots=[{'id':'p01','namespace':'arcia-user-p01','prefix':'/u/p01'},
                    {'id':'p02','namespace':'arcia-user-p02','prefix':'/u/p02'}]
        self.pool=Slots(self.api,self.slots,self.issuer,'synthetic')
        for slot in self.slots:
            for kind,name,data in [('configmaps','slot-binding',{'binding.json':'{}'}),('secrets',SECRET,{})]:
                self.api.docs[self.pool.resource(slot,kind,name)]={
                    'metadata':{'resourceVersion':'1','annotations':{'arcia.io/operation-id':'synthetic'}},'data':data}
        self.key=b'x'*32;self.store=UserKeys(self.pool,self.key,True)
        self.a={'iss':self.issuer,'sub':'subject-a','arcia_roles':['ArcIA.User',ROLE]}
        self.b={**self.a,'sub':'subject-b'}
        self.input={'provider':'openrouter','api_key':'synthetic-provider-key-a'}

    def test_only_explicit_selfservice_role_allows_any_access(self):
        for roles in ([],['ArcIA.User'],['ArcIA.User','ArcIA.Admin'],[ROLE]):
            identity={**self.a,'arcia_roles':roles}
            with self.assertRaises(PermissionError):self.store.list(identity)
            with self.assertRaises(PermissionError):self.store.change(identity,self.input)
        self.assertEqual(self.api.writes,[])

    def test_foreign_issuer_and_disabled_feature_cannot_access(self):
        with self.assertRaises(PermissionError):self.store.list({**self.a,'iss':'https://foreign.invalid'})
        with self.assertRaises(PermissionError):UserKeys(self.pool,self.key,False).change(self.a,self.input)

    def test_isolation_no_cleartext_no_secret_in_response(self):
        metadata=self.store.change(self.a,self.input)
        self.assertEqual(self.store.list(self.b),[])
        self.assertNotIn(self.input['api_key'],json.dumps(self.api.docs))
        self.assertNotIn('api_key',json.dumps(metadata))
        self.assertEqual(metadata[0]['status'],'stored_not_active')
        self.store.change(self.b,{**self.input,'api_key':'synthetic-provider-key-b'})
        self.assertEqual(self.store.list(self.a),metadata)

    def test_replace_delete_and_reapplication_keep_ownership(self):
        self.store.change(self.a,self.input)
        self.store.change(self.a,{**self.input,'api_key':'synthetic-rotated-key'})
        reopened=UserKeys(self.pool,self.key,True)
        self.assertEqual(len(reopened.list(self.a)),1)
        reopened.change(self.a,{'provider':'openrouter'},True)
        self.assertEqual(reopened.list(self.a),[])
        self.assertNotIn('synthetic-rotated-key',json.dumps(self.api.docs))

    def test_ciphertext_cannot_move_to_another_owner(self):
        self.store.change(self.a,self.input);self.pool.allocate(self.b['sub'])
        a=self.pool.resource(self.slots[0],'secrets',SECRET);b=self.pool.resource(self.slots[1],'secrets',SECRET)
        self.api.docs[b]['data']=copy.deepcopy(self.api.docs[a]['data'])
        with self.assertRaises(KeyConfigError):self.store.list(self.b)

    def test_wrong_encryption_key_refuses_existing_state(self):
        self.store.change(self.a,self.input)
        with self.assertRaises(KeyConfigError):UserKeys(self.pool,b'y'*32,True).list(self.a)

    def test_payload_cannot_choose_owner_namespace_endpoint_or_model(self):
        for extra in ('subject','issuer','namespace','endpoint','model','isActive'):
            with self.assertRaises(ValueError):self.store.change(self.a,{**self.input,extra:'other'})
        for key in ('short','synthetic\nkey','synthetic key',None):
            with self.assertRaises(ValueError):self.store.change(self.a,{**self.input,'api_key':key})
        self.assertFalse(self.api.writes)

    def test_role_revocation_blocks_old_identity_without_touching_other_keys(self):
        self.store.change(self.a,self.input)
        with self.assertRaises(PermissionError):self.store.change({**self.a,'arcia_roles':['ArcIA.User']},self.input)
        self.assertEqual(len(self.store.list(self.a)),1)

    def test_concurrent_edits_do_not_lose_different_provider_keys(self):
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(lambda provider:self.store.change(self.a,{'provider':provider,'api_key':'synthetic-key'}),
                              ['openrouter','openai','anthropic','gemini']))
        self.assertEqual(len(self.store.list(self.a)),4)

    def test_http_security_and_owner_isolation(self):
        portal=SimpleNamespace(config={'hostname':'synthetic.example.invalid'},origin='https://synthetic.example.invalid',
                               user_keys=self.store,csrf=lambda sub:'synthetic-csrf-'+sub)
        identities={'a':self.a,'b':self.b,'no-role':{**self.a,'arcia_roles':['ArcIA.User']}}
        def authenticate(token):
            if token not in identities:raise ValueError('LOGIN_REFUSED')
            return identities[token]
        portal.authenticate=authenticate
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.portal=portal
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def request(method,path,who='a',value=None,csrf=True,origin=True):
            conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
            headers={'Host':'synthetic.example.invalid','Cookie':'__Secure-arcia_portal_at='+who}
            if csrf:headers['X-ArcIA-CSRF']='synthetic-csrf-'+identities.get(who,self.a)['sub']
            if origin:headers['Origin']=portal.origin
            if value is not None:headers['Content-Type']='application/json'
            conn.request(method,path,body=json.dumps(value) if value is not None else None,headers=headers)
            response=conn.getresponse();body=response.read();status=response.status;conn.close()
            return status,body
        try:
            self.assertEqual(request('GET','/portal/api/keys','anonymous')[0],401)
            self.assertEqual(request('GET','/portal/api/keys','no-role')[0],403)
            self.assertEqual(request('POST','/portal/api/keys',value=self.input,csrf=False)[0],403)
            self.assertEqual(request('POST','/portal/api/keys',value=self.input,origin=False)[0],403)
            self.assertFalse(self.api.writes)
            status,body=request('POST','/portal/api/keys',value=self.input)
            self.assertEqual(status,200);self.assertNotIn(self.input['api_key'].encode(),body)
            self.assertEqual(json.loads(request('GET','/portal/api/keys','b')[1]),{'keys':[]})
            self.assertEqual(request('POST','/portal/api/keys',value={**self.input,'subject':'subject-b'})[0],400)
            page=request('GET','/portal/keys')[1]
            self.assertIn(b'type="password"',page);self.assertNotIn(self.input['api_key'].encode(),page)
            self.assertEqual(request('DELETE','/portal/api/keys',value={'provider':'openrouter'})[0],200)
            self.assertEqual(self.store.list(self.a),[])
        finally:server.shutdown();server.server_close();thread.join()


class KeyDeploymentTests(unittest.TestCase):
    def test_live_userinfo_removes_selfservice_even_when_old_jwt_has_it(self):
        portal=Portal({'hostname':'synthetic.example.invalid','identity_internal':'http://identity.invalid',
                       'slots':[],'operation_id':'synthetic'},b'synthetic-hmac',Mock())
        claims={'iss':portal.issuer,'sub':'subject-a','azp':'arcia-portal','arcia_roles':['ArcIA.User',ROLE]}
        with patch.object(portal,'claims',return_value=claims),patch('portal.httpx.get',
                return_value=SimpleNamespace(status_code=200,json=lambda:{'sub':'subject-a','arcia_roles':['ArcIA.User']})):
            current=portal.authenticate('synthetic-old-token')
            self.assertNotIn(ROLE,current['arcia_roles'])
            with self.assertRaises(PermissionError):UserKeys(portal.slots,b'x'*32,True).list(current)

    def test_key_request_schema_matches_strict_ownerless_contract(self):
        import jsonschema
        schema=json.loads((ROOT/'schemas/provider-key-config.schema.json').read_text())
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.validate({'provider':'openai','api_key':'synthetic-only'},schema)
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate({'provider':'openai','api_key':'synthetic-only','subject':'foreign'},schema)

    def test_key_resources_have_no_create_list_or_arbitrary_secret_access(self):
        docs=portal_deploy.key_resources([{'id':'p01','namespace':'arcia-user-p01'}])
        role=next(d for d in docs if d['kind']=='Role')
        self.assertEqual(role['rules'],[{'apiGroups':[''],'resources':['secrets'],'resourceNames':[SECRET],'verbs':['get','patch']}])
        with self.assertRaises(ValueError):portal_deploy.key_resources([{'id':'p01','namespace':'foreign'}])

    def test_missing_encryption_key_never_replaces_existing_encrypted_store(self):
        def owned(kind,name,ns,op,optional=False):
            return {'data':{'sealed':'synthetic-sealed'}} if name==SECRET else None
        with patch.object(node_identity,'owned',side_effect=owned),patch.object(node_identity,'apply') as apply:
            with self.assertRaisesRegex(ValueError,'RECOVERY_REQUIRED'):
                node_identity.ensure_key_encryption('synthetic',[{'namespace':'arcia-user-p01'}])
            apply.assert_not_called()

    def test_existing_encryption_key_is_preserved(self):
        with patch.object(node_identity,'owned',return_value={'data':{'key':base64.b64encode(b'x'*32).decode()}}),patch.object(node_identity,'apply') as apply:
            node_identity.ensure_key_encryption('synthetic',[]);apply.assert_not_called()


if __name__=='__main__':unittest.main()
