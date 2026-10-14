import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock,patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'services/routing'))
from self_service import Control,Identity,owner_id
from native import Native
from store import Store
from gateway import Gateway,RuntimeIdentity


class PersonalRoutingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.store=Store(Path(self.temp.name)/'state.db',b'synthetic-key'*4)
        self.native=Mock();self.native.connections.return_value=[]
        self.native.create.return_value='12345678-1234-1234-1234-123456789abc'
        self.control=Control(self.store,self.native)
        self.user={'iss':'https://identity.example.invalid','sub':'subject-a','arcia_roles':['ArcIA.User','ArcIA.ProviderSelfService']}
        self.other={**self.user,'sub':'subject-b'}
        self.admin={**self.user,'arcia_roles':['ArcIA.User','ArcIA.Admin']}
        self.settings=self.store.settings();self.settings['personal_providers_enabled']=True;self.store.save_settings(self.settings)
        self.value={'provider':'openai','label':'Personal example','api_key':'SYNTHETIC_API_CANARY'}

    def tearDown(self):self.store.db.close();self.temp.cleanup()

    def test_native_cloud_sync_is_disabled_without_password_or_login_changes(self):
        native=Native('synthetic-jwt-key')
        with patch.object(native,'request',side_effect=[{'requireLogin':True,'cloudEnabled':True},{},{'requireLogin':True,'cloudEnabled':False}]) as call:
            native.enforce_private()
            self.assertEqual(call.call_args_list[1].args,('POST','/api/sync/cloud',{'action':'disable'}))
        with patch.object(native,'request',return_value={'requireLogin':False,'cloudEnabled':False}) as call:
            with self.assertRaises(PermissionError):native.enforce_private()
            self.assertEqual(call.call_count,1)

    def test_uncertain_key_is_revoked_by_reserved_name_before_a_new_request(self):
        self.settings.update(enterprise_connections=['enterprise-id'],allowed_models=['openai/synthetic-model'])
        self.store.save_settings(self.settings)
        self.native.connections.return_value=[{'id':'enterprise-id','provider':'openai','name':'Enterprise','isActive':True}]
        owner=owner_id(self.user)
        self.store.credential(owner,{'id':None,'phase':'pending','native_name':'reserved-unique-name'})
        self.native.keys.return_value=[{'id':'pending-id','name':'reserved-unique-name'},{'id':'foreign-id','name':'other-name'}]
        with self.assertRaisesRegex(RuntimeError,'RECOVERED_RETRY'):self.control.profile(self.user)
        self.native.revoke_key.assert_called_once_with('pending-id')
        self.native.scoped_key.assert_not_called()
        self.assertIsNone(self.store.credential(owner))

    def test_role_and_instance_switch_required_before_native_write(self):
        user={**self.user,'arcia_roles':['ArcIA.User']}
        with self.assertRaisesRegex(PermissionError,'PERSONAL_PROVIDER_ROLE'):self.control.create(user,self.value)
        self.settings['personal_providers_enabled']=False;self.store.save_settings(self.settings)
        with self.assertRaisesRegex(PermissionError,'PERSONAL_PROVIDER_ROLE'):self.control.create(self.user,self.value)
        self.native.create.assert_not_called()

    def test_personal_write_never_returns_or_stores_provider_key(self):
        result=self.control.create(self.user,self.value)
        self.assertNotIn('SYNTHETIC_API_CANARY',json.dumps(result))
        self.assertNotIn('SYNTHETIC_API_CANARY',json.dumps(self.store.connections()))
        self.assertEqual(self.store.connections()[0]['issuer'],self.user['iss'])
        self.assertEqual(self.store.connections()[0]['subject'],self.user['sub'])
        self.assertEqual(self.control.state(self.other)['connections'],[])

    def test_cross_owner_delete_refused_and_role_removal_hides_personal_records(self):
        identifier=self.control.create(self.user,self.value)['connections'][0]['id']
        with self.assertRaisesRegex(PermissionError,'OWNER'):self.control.delete(self.other,identifier)
        self.native.delete.assert_not_called()
        result=self.control.state({**self.user,'arcia_roles':['ArcIA.User']})
        self.assertFalse(result['personal_allowed']);self.assertEqual(result['connections'],[])

    def test_prompt_cannot_set_endpoint_owner_priority_or_role(self):
        for field in ('baseUrl','issuer','subject','globalPriority','arcia_roles'):
            with self.assertRaisesRegex(ValueError,'CONNECTION_FIELDS'):self.control.create(self.user,{**self.value,field:'attacker'})
        with self.assertRaisesRegex(PermissionError,'PROVIDER_NOT_ALLOWED'):
            self.control.create(self.user,{**self.value,'provider':'http://127.0.0.1:8080'})
        self.native.create.assert_not_called()

    def test_failed_create_is_reconciled_without_replaying_a_write(self):
        self.native.create.side_effect=RuntimeError('TIMEOUT')
        with self.assertRaises(RuntimeError):self.control.create(self.user,self.value)
        row=self.store.connections()[0];self.assertEqual(row['phase'],'pending')
        self.native.connections.return_value=[{'id':'native-id','provider':'openai','name':row['native_name']}]
        self.control.reconcile()
        self.assertEqual(self.store.connections()[0]['native_id'],'native-id')
        self.assertEqual(self.native.create.call_count,1)

    def test_enterprise_pool_never_adopts_personal_connections(self):
        self.control.create(self.user,self.value);row=self.store.connections()[0]
        self.native.connections.return_value=[{'id':row['native_id'],'provider':'openai','name':row['native_name'],'isActive':True}]
        value={**self.settings,'enterprise_connections':[row['native_id']]}
        with self.assertRaisesRegex(PermissionError,'ENTERPRISE_CONNECTION_SCOPE'):
            self.control.configure(self.admin,value)
        with self.assertRaisesRegex(PermissionError,'ADMIN_REQUIRED'):
            self.control.configure(self.user,self.settings)

    def test_native_adapter_has_only_loopback_paths_and_no_probe_on_key_entry(self):
        with self.assertRaisesRegex(ValueError,'LOOPBACK'):Native('fixture','https://attacker.example.invalid')
        native=Native('synthetic-jwt-key')
        with patch.object(native,'request',side_effect=[{'requireLogin':True,'cloudEnabled':False},
                {'created':[{'id':'12345678-1234-1234-1234-123456789abc'}]},{}]) as call:
            native.create('openai','synthetic-name','SYNTHETIC_API_CANARY')
            create=call.call_args_list[1]
            self.assertEqual(create.args[1],'/api/providers/bulk')
            self.assertFalse(create.args[2]['validateKeys'])
            self.assertFalse(create.args[2]['providerSpecificData']['autoFetchModels'])
            self.assertNotIn('/test',json.dumps([c.args[1] for c in call.call_args_list]))

    def test_cloud_sync_or_disabled_login_prevents_credential_submission(self):
        for settings in ({'cloudEnabled':True,'requireLogin':True},{'cloudEnabled':False,'requireLogin':False}):
            native=Native('fixture')
            with patch.object(native,'request',return_value=settings) as call:
                with self.assertRaisesRegex(PermissionError,'PRIVATE_AUTHENTICATED'):
                    native.create('openai','fixture','SYNTHETIC_API_CANARY')
                self.assertEqual(call.call_count,1)

    def test_encrypted_sessions_and_credentials_are_context_bound(self):
        payload={'created':time.time(),'access_token':'SYNTHETIC_TOKEN_CANARY','csrf':'fixture'}
        self.store.session('opaque-session',payload)
        self.assertEqual(self.store.session('opaque-session'),payload)
        raw=self.store.db.execute('SELECT value FROM sessions').fetchone()[0]
        self.assertNotIn(b'SYNTHETIC_TOKEN_CANARY',raw)
        with self.assertRaises(Exception):self.store.open(raw,'different-context')
        self.store.credential(owner_id(self.user),{'id':'fixture','key':'SYNTHETIC_KEY_CANARY'})
        self.assertIsNone(self.store.credential(owner_id(self.other)))
        self.store.logout('opaque-session')
        with self.assertRaises(PermissionError):self.store.session('opaque-session')

    def test_online_roles_override_stale_token_roles_and_disabled_user_is_refused(self):
        identity=Identity({'hostname':'arcia.example.invalid'},b'synthetic-key')
        claims={**self.user,'azp':'arcia-routing'}
        response=Mock(status_code=200);response.json.return_value={'sub':self.user['sub'],'arcia_roles':['ArcIA.User']}
        with patch.object(identity,'claims',return_value=claims),patch('self_service.httpx.get',return_value=response):
            self.assertNotIn('ArcIA.ProviderSelfService',identity.authenticate('fixture')['arcia_roles'])
            response.status_code=401
            with self.assertRaises(PermissionError):identity.authenticate('fixture')

    def test_state_cannot_be_forged_or_reused_after_expiry(self):
        identity=Identity({'hostname':'arcia.example.invalid'},b'synthetic-key')
        pending=identity.sign({'created':time.time(),'state':'fixture'})
        self.assertEqual(identity.pending(pending)['state'],'fixture')
        with self.assertRaises(Exception):identity.pending(pending+'x')
        with self.assertRaises(PermissionError):identity.pending(identity.sign({'created':time.time()-301}))

    def test_effective_override_is_owner_scoped_and_revocation_returns_to_enterprise(self):
        personal=self.control.create(self.user,self.value)['connections'][0]['id']
        row=self.store.connections()[0];company='87654321-4321-4321-4321-cba987654321'
        self.settings.update(enterprise_connections=[company],allowed_models=['openai/synthetic-model'])
        self.store.save_settings(self.settings)
        self.native.connections.return_value=[{'id':row['native_id'],'provider':'openai','name':row['native_name'],'isActive':True},
            {'id':company,'provider':'openai','name':'Company synthetic','isActive':True}]
        self.native.scoped_key.side_effect=[{'id':'key-company','key':'SYNTHETIC_COMPANY'},
            {'id':'key-personal','key':'SYNTHETIC_PERSONAL'},{'id':'key-restored','key':'SYNTHETIC_RESTORED'}]
        self.assertEqual(self.control.profile(self.user)['connections'],[company])
        self.control.preference(self.user,{'enabled':True})
        own=self.control.profile(self.user)
        self.assertEqual(own['connections'],[row['native_id']]);self.assertTrue(own['personal'])
        self.assertEqual(own['model'],'auto/smart')
        revoked={**self.user,'arcia_roles':['ArcIA.User']}
        restored=self.control.profile(revoked)
        self.assertFalse(restored['personal']);self.assertEqual(restored['connections'],[company])
        self.native.revoke_key.assert_any_call('key-personal')
        self.assertNotIn('api_key',self.control.state(self.user))

    def test_unavailable_personal_pool_never_falls_back_to_company(self):
        self.control.preference(self.user,{'enabled':True})
        self.settings.update(enterprise_connections=['12345678-1234-1234-1234-123456789abc'],allowed_models=['openai/synthetic-model'])
        self.store.save_settings(self.settings)
        self.native.connections.return_value=[{'id':self.settings['enterprise_connections'][0],
            'provider':'openai','name':'Company synthetic','isActive':True}]
        with self.assertRaisesRegex(PermissionError,'ADMIN_ROUTING_CONFIGURATION'):
            self.control.profile(self.user)
        self.native.scoped_key.assert_not_called()

    def test_cloud_content_is_sanitized_before_native_inference_and_mode_is_admin_owned(self):
        control=Mock();control.profile.return_value={'model':'auto/smart','api_key':'SYNTHETIC_ROUTING_KEY','route_class':'cloud'}
        identity=Mock();identity.authenticate.return_value=self.user
        gateway=Gateway(control,identity)
        value={'model':'auto/smart','messages':[{'role':'user','content':'SYNTHETIC_RAW'}]}
        clean={'model':'auto/smart','messages':[{'role':'user','content':'SYNTHETIC_FILTERED'}]}
        with patch('gateway.http_json',side_effect=[{'body':clean},{'choices':[]}]) as calls:
            gateway.complete('synthetic-runtime-token',value)
            self.assertIn('/v1/sanitize-completion',calls.call_args_list[0].args[0])
            inference=calls.call_args_list[1]
            self.assertEqual(inference.args[0],'http://127.0.0.1:20128/v1/chat/completions')
            self.assertNotIn('SYNTHETIC_RAW',json.dumps(inference.args[2]))
            self.assertIn('SYNTHETIC_FILTERED',json.dumps(inference.args[2]))
        with patch('gateway.http_json') as calls:
            with self.assertRaisesRegex(PermissionError,'ADMIN_AUTO_MODE'):gateway.complete('fixture',{**value,'model':'arbitrary/paid-model'})
            calls.assert_not_called()

    def test_sanitizer_failure_and_missing_runtime_identity_never_call_model(self):
        control=Mock();control.profile.return_value={'model':'auto/smart','api_key':'SYNTHETIC_ROUTING_KEY','route_class':'cloud'}
        identity=Mock();identity.authenticate.return_value=self.user;gateway=Gateway(control,identity)
        with patch('gateway.http_json',side_effect=RuntimeError('FILTER_DOWN')) as calls:
            with self.assertRaises(RuntimeError):gateway.complete('fixture',{'model':'auto/smart','messages':[]})
            self.assertEqual(calls.call_count,1)
        identity.authenticate.side_effect=PermissionError('RUNTIME_BINDING_REQUIRED')
        with patch('gateway.http_json') as calls:
            with self.assertRaises(PermissionError):gateway.complete('fixture',{'model':'auto/smart','messages':[]})
            calls.assert_not_called()

    def test_runtime_token_binding_is_read_from_server_and_user_roles_rechecked_online(self):
        config={'hostname':'arcia.example.invalid','operation_id':'synthetic-operation','slots':{'p01':'arcia-user-p01'}}
        identity=RuntimeIdentity(config,{'client_secret':'SYNTHETIC_SERVICE_KEY'},
            {'tokens':{'synthetic-runtime-token':'personal-p01'},'legacy_bindings':{}},self.temp.name)
        Path(self.temp.name,'token').write_text('SYNTHETIC_KUBE_TOKEN');Path(self.temp.name,'ca.crt').write_text('fixture')
        binding={'metadata':{'annotations':{'arcia.io/operation-id':'synthetic-operation'}},
            'data':{'binding.json':json.dumps({'issuer':identity.issuer,'subject':'subject-a'})}}
        results=[binding,{'access_token':'SYNTHETIC_READONLY_TOKEN'},{'id':'subject-a','enabled':True},[{'name':'ArcIA.User'}]]
        with patch('gateway.ssl.create_default_context',return_value=Mock()),patch('gateway.http_json',side_effect=results) as calls:
            result=identity.authenticate('synthetic-runtime-token')
            self.assertEqual(result['sub'],'subject-a');self.assertEqual(result['arcia_roles'],['ArcIA.User'])
            self.assertIn('/namespaces/arcia-user-p01/configmaps/slot-binding',calls.call_args_list[0].args[0])
            self.assertIn('/users/subject-a/role-mappings/realm/composite',calls.call_args_list[3].args[0])
        with patch('gateway.http_json') as calls:
            with self.assertRaisesRegex(PermissionError,'RUNTIME_TOKEN_REQUIRED'):identity.authenticate('foreign-runtime-token')
            calls.assert_not_called()


if __name__=='__main__':unittest.main()
