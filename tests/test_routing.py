import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
sys.path.insert(0,str(ROOT/'services/routing'))
import policy
import routing_deploy
import node_routing


class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.admin={'automatic_mode':'auto/smart','lan_cidrs':['192.168.40.0/24'],
                    'personal_providers_enabled':False,'personal_role':policy.PERSONAL_ROLE}
        self.user={'iss':'https://identity.example.invalid','sub':'synthetic-owner','arcia_roles':['ArcIA.User']}
        self.enterprise={'route_class':'cloud','connection_classes':['cloud'],
            'allowed_connections':['12345678-1234-1234-1234-123456789abc'],'credential_ref':'secretref://routing/enterprise'}

    def test_standard_user_has_admin_auto_mode_and_cloud_filter(self):
        route=policy.select(self.user,self.admin,self.enterprise)
        self.assertEqual(route['model'],'auto/smart')
        self.assertTrue(route['presidio_required'])

    def test_internal_route_does_not_require_presidio(self):
        profile=dict(self.enterprise,route_class='internal',connection_classes=['internal'])
        self.assertFalse(policy.select(self.user,self.admin,profile)['presidio_required'])

    def test_personal_override_requires_switch_role_and_exact_owner(self):
        personal=dict(self.enterprise,issuer=self.user['iss'],subject=self.user['sub'])
        with self.assertRaisesRegex(PermissionError,'ROLE_REQUIRED'):policy.select(self.user,self.admin,self.enterprise,personal)
        admin=dict(self.admin,personal_providers_enabled=True)
        with self.assertRaisesRegex(PermissionError,'ROLE_REQUIRED'):policy.select(self.user,admin,self.enterprise,personal)
        user=dict(self.user,arcia_roles=['ArcIA.User',policy.PERSONAL_ROLE])
        self.assertEqual(policy.select(user,admin,self.enterprise,personal)['model'],'auto/smart')
        personal['subject']='other-owner'
        with self.assertRaisesRegex(PermissionError,'OWNER_REQUIRED'):policy.select(user,admin,self.enterprise,personal)

    def test_unauthorized_identity_and_mixed_fallback_fail_closed(self):
        with self.assertRaisesRegex(PermissionError,'USER_REQUIRED'):policy.select({},self.admin,self.enterprise)
        mixed=dict(self.enterprise,connection_classes=['cloud','internal'])
        with self.assertRaisesRegex(ValueError,'MIXED_CLASS'):policy.select(self.user,self.admin,mixed)

    def test_public_dashboard_cidrs_and_arbitrary_modes_are_refused(self):
        for cidr in ('0.0.0.0/0','8.8.8.0/24','::/0','100.64.0.0/10'):
            with self.assertRaisesRegex(ValueError,'PRIVATE_LAN'):policy.validate_admin_policy(dict(self.admin,lan_cidrs=[cidr]))
        with self.assertRaisesRegex(ValueError,'ADMIN_AUTO'):policy.validate_admin_policy(dict(self.admin,automatic_mode='paid/model'))

    def test_private_renderer_has_no_public_ingress_or_hermes_bypass(self):
        lock=json.loads((ROOT/'versions.lock.yaml').read_text())
        config=json.loads((ROOT/'examples/synthetic/instance.json').read_text())
        payload=routing_deploy.payload(lock,config,self.admin['lan_cidrs'])
        docs=payload['documents']+[payload['deployment'],payload['lan'],payload['job']]
        self.assertFalse(any(d['kind']=='Ingress' or d['kind']=='Service' and d['spec'].get('type')=='LoadBalancer' for d in docs))
        gateway=next(d for d in docs if d['kind']=='ConfigMap' and d['metadata']['name']=='routing-nginx')['data']['nginx.conf']
        self.assertIn('deny all;',gateway);self.assertIn('allow 192.168.40.0/24;',gateway)
        self.assertIn('return 403;',gateway)
        api=next(d for d in docs if d['kind']=='NetworkPolicy' and d['metadata']['name']=='omniroute-controlled')
        self.assertNotIn('arcia-hermes',json.dumps(api));self.assertIn('cloud-egress',json.dumps(api))
        self.assertEqual(payload['deployment']['spec']['replicas'],1)
        self.assertEqual(payload['deployment']['spec']['strategy']['type'],'Recreate')
        self.assertFalse(payload['deployment']['spec']['template']['spec']['enableServiceLinks'])

    def test_foreign_resources_are_refused_before_apply(self):
        foreign={'metadata':{'annotations':{'arcia.io/operation-id':'other'}}}
        doc={'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':'routing-policy','namespace':'arcia-routing'}}
        with patch.object(node_routing,'kube',return_value=json.dumps(foreign)) as kube:
            with self.assertRaisesRegex(ValueError,'FOREIGN_ROUTING_RESOURCE'):node_routing.apply([doc],'ours')
            self.assertEqual(kube.call_count,1)

    def test_reconcile_preserves_credentials_and_does_not_reset_password(self):
        lock=json.loads((ROOT/'versions.lock.yaml').read_text());config=json.loads((ROOT/'examples/synthetic/instance.json').read_text())
        values=dict(routing_deploy.payload(lock,config,self.admin['lan_cidrs']),operation_id='ours')
        deployment=copy.deepcopy(values['deployment'])
        def owned(kind,name,*args,**kwargs):
            return deployment if kind=='Deployment' else {'data':{'existing':'protected'}}
        with patch.object(node_routing,'owned',side_effect=owned),patch.object(node_routing,'apply') as apply,\
             patch.object(node_routing,'kube'),patch.object(node_routing,'native') as native,\
             patch.object(node_routing,'inspect',return_value={'router_ready':True,'lan_ready_nodes':3}):
            result=node_routing.install(values)
            self.assertTrue(result['credentials_preserved']);self.assertTrue(result['existing_volumes_preserved'])
            native.assert_not_called()
            self.assertFalse(any(d.get('metadata',{}).get('name')=='routing-credentials' for call in apply.call_args_list for d in call.args[0]))

    def test_runtime_change_never_mutates_without_explicit_repair(self):
        previous={'spec':{'template':{'metadata':{'annotations':{'arcia.io/runtime-sha256':'old'}}}}}
        with patch.object(node_routing,'owned',return_value=previous),patch.object(node_routing,'apply') as apply:
            with self.assertRaisesRegex(ValueError,'CONTROLLED_ROUTER_RUNTIME_UPGRADE_REQUIRED'):
                node_routing.install({'operation_id':'ours','digest':'new'})
            apply.assert_not_called()

    def test_qualified_runtime_cannot_use_first_startup_repair(self):
        previous={'spec':{'template':{'metadata':{'annotations':{'arcia.io/runtime-sha256':'old'}}}}}
        with patch.object(node_routing,'owned',return_value=previous),patch.object(node_routing,'apply') as apply:
            with self.assertRaisesRegex(ValueError,'QUALIFIED_ROUTER_REPAIR_REFUSED'):
                node_routing.install({'operation_id':'ours','digest':'new','repair_unqualified_runtime':True})
            apply.assert_not_called()


if __name__=='__main__':unittest.main()
