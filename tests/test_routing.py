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

    def test_all_sources_requires_explicit_private_firewall_boundary(self):
        value=dict(self.admin,lan_cidrs=['0.0.0.0/0'])
        with self.assertRaisesRegex(ValueError,'PRIVATE_LAN_ONLY'):policy.validate_admin_policy(value)
        self.assertTrue(policy.validate_admin_policy(dict(value,private_firewall_boundary=True))['private_firewall_boundary'])
        with self.assertRaisesRegex(ValueError,'PRIVATE_LAN_ONLY'):
            policy.validate_admin_policy(dict(value,lan_cidrs=['8.8.8.0/24'],private_firewall_boundary=True))

    def test_private_renderer_has_no_public_ingress_or_hermes_bypass(self):
        lock=json.loads((ROOT/'versions.lock.yaml').read_text())
        config=json.loads((ROOT/'examples/synthetic/instance.json').read_text())
        payload=routing_deploy.payload(lock,config,self.admin['lan_cidrs'])
        docs=payload['documents']+[payload['deployment'],payload['lan'],payload['job']]
        self.assertFalse(any(d['kind']=='Ingress' or d['kind']=='Service' and d['spec'].get('type')=='LoadBalancer' for d in docs))
        nginx=next(d for d in docs if d['kind']=='ConfigMap' and d['metadata']['name'].startswith('routing-nginx-'))
        gateway=nginx['data']['nginx.conf']
        self.assertTrue(nginx['immutable'])
        self.assertIn('fastcgi_temp_path /tmp/fastcgi',gateway)
        self.assertIn('uwsgi_temp_path /tmp/uwsgi',gateway)
        self.assertIn('scgi_temp_path /tmp/scgi',gateway)
        self.assertIn('deny all;',gateway);self.assertIn('allow 192.168.40.0/24;',gateway)
        self.assertIn('return 403;',gateway)
        api=next(d for d in docs if d['kind']=='NetworkPolicy' and d['metadata']['name']=='omniroute-controlled')
        self.assertNotIn('arcia-hermes',json.dumps(api));self.assertIn('cloud-egress',json.dumps(api))
        self.assertEqual(payload['deployment']['spec']['replicas'],1)
        self.assertEqual(payload['deployment']['spec']['strategy']['type'],'Recreate')
        self.assertFalse(payload['deployment']['spec']['template']['spec']['enableServiceLinks'])
        namespaces={d['metadata']['name']:d['metadata']['labels']['pod-security.kubernetes.io/enforce'] for d in docs if d['kind']=='Namespace'}
        self.assertEqual(namespaces['arcia-routing'],'restricted')
        self.assertEqual(namespaces['arcia-routing-lan'],'privileged')
        self.assertEqual(payload['lan']['metadata']['namespace'],'arcia-routing-lan')
        relay=payload['lan']['spec']['template']['spec']['containers'][0]
        self.assertEqual(relay['readinessProbe']['tcpSocket']['port'],8443)

    def test_foreign_resources_are_refused_before_apply(self):
        foreign={'metadata':{'annotations':{'arcia.io/operation-id':'other'}}}
        doc={'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':'routing-policy','namespace':'arcia-routing'}}
        with patch.object(node_routing,'kube',return_value=json.dumps(foreign)) as kube:
            with self.assertRaisesRegex(ValueError,'FOREIGN_ROUTING_RESOURCE'):node_routing.apply([doc],'ours')
            self.assertEqual(kube.call_count,1)

    def test_private_probe_refuses_public_address_before_any_connection(self):
        with patch.object(routing_deploy.socket,'create_connection') as connect:
            with self.assertRaisesRegex(ValueError,'PRIVATE_ROUTER_PROBE_TARGET_REQUIRED'):
                routing_deploy.probe_lan('arcia.example.invalid',['192.168.40.1','192.168.40.2','8.8.8.8'])
            connect.assert_not_called()

    def test_ip_https_uses_a_private_vip_certificate_and_rejects_other_hosts(self):
        lock=json.loads((ROOT/'versions.lock.yaml').read_text());config=json.loads((ROOT/'examples/synthetic/instance.json').read_text())
        result=routing_deploy.payload(lock,config,self.admin['lan_cidrs'],ip_https_vip='192.168.40.20')
        nginx=next(d for d in result['documents'] if d['kind']=='ConfigMap' and d['metadata']['name'].startswith('routing-nginx-'))['data']['nginx.conf']
        self.assertIn('server_name 192.168.40.20',nginx)
        self.assertIn('ssl_certificate /ip-tls/tls.crt',nginx)
        self.assertIn('if ($host != "192.168.40.20") { return 444; }',nginx)
        pod=result['lan']['spec']['template']['spec']
        self.assertIn('routing-ip-tls',{v.get('secret',{}).get('secretName') for v in pod['volumes']})
        self.assertTrue(next(m for m in pod['containers'][0]['volumeMounts'] if m['name']=='ip-tls')['readOnly'])
        self.assertTrue(result['policy']['ip_https_enabled'])

    def test_public_vip_cannot_enable_private_ip_https(self):
        lock=json.loads((ROOT/'versions.lock.yaml').read_text());config=json.loads((ROOT/'examples/synthetic/instance.json').read_text())
        with self.assertRaisesRegex(ValueError,'PRIVATE_ROUTING_VIP_REQUIRED'):
            routing_deploy.payload(lock,config,self.admin['lan_cidrs'],ip_https_vip='8.8.8.8')

    def test_reconcile_preserves_credentials_and_does_not_reset_password(self):
        lock=json.loads((ROOT/'versions.lock.yaml').read_text());config=json.loads((ROOT/'examples/synthetic/instance.json').read_text())
        values=dict(routing_deploy.payload(lock,config,self.admin['lan_cidrs']),operation_id='ours')
        deployment=copy.deepcopy(values['deployment'])
        def owned(kind,name,*args,**kwargs):
            return deployment if kind=='Deployment' else {'data':{'existing':'protected'}}
        with patch.object(node_routing,'owned',side_effect=owned),patch.object(node_routing,'apply') as apply,\
             patch.object(node_routing,'kube'),patch.object(node_routing,'enforce_private') as enforce,patch.object(node_routing,'native') as native,\
             patch.object(node_routing,'inspect',return_value={'router_ready':True,'lan_ready_nodes':3}):
            result=node_routing.install(values)
            self.assertTrue(result['credentials_preserved']);self.assertTrue(result['existing_volumes_preserved'])
            native.assert_not_called();enforce.assert_called_once_with('ours')
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
