import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import copy
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import vmware_foundation as foundation
import bootstrap_config
import harness
import network_preflight
import node_network_probe
import vmware_service_permissions


class FoundationTests(unittest.TestCase):
    def test_summary_does_not_disclose_inventory(self):
        value = {'vcenter_version': '9.1.1', 'hosts': [{'version': '9.1.1', 'id': 'SECRET_HOST'}],
                 'nodes': [{'name': 'SECRET_VM'}]*3, 'datastore_type': 'vsan',
                 'shared_datastore_accessible': True, 'capacity_1tib_available': True,
                 'policy_query_succeeded': True, 'policy_query_code': 'POLICIES_READ',
                 'policies': [{'name': 'SECRET_POLICY', 'id': 'SECRET_ID', 'compatible': True}]}
        result = foundation.summarize(value)
        self.assertNotIn('SECRET', json.dumps(result))
        self.assertEqual(result['compatible_policy_count'], 1)
        self.assertFalse(result['csi_qualified'])
        self.assertFalse(result['k3s_installed'])
        value['vcenter_version'] = 'SECRET_ENDPOINT'
        value['hosts'][0]['version'] = 'SECRET_HOST'
        value['datastore_type'] = 'SECRET_DS'
        value['policy_query_code'] = 'SECRET_FAULT'
        self.assertNotIn('SECRET', json.dumps(foundation.summarize(value)))

    def test_private_failure_is_not_printed(self):
        import io
        output = io.StringIO()
        with patch('sys.stdin', io.StringIO('{}')), patch('sys.stdout', output), \
                patch.object(foundation, 'collect', side_effect=ValueError('SECRET_PASSWORD')):
            self.assertEqual(foundation.main(), 2)
        self.assertNotIn('SECRET', output.getvalue())
        self.assertEqual(json.loads(output.getvalue())['safe']['status'], 'blocked')


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        (root/'ssh').mkdir()
        (root/'ssh/key').touch()
        (root/'known_hosts.arcia').touch()
        self.target = {'ssh_public_key_path': str(root/'ssh/key.pub'), 'ssh_user': 'engineer',
                       'addresses': ['10.8.0.11/24', '10.8.0.12/24', '10.8.0.13/24'], 'gateway': '10.8.0.1'}
        self.nodes = [{'address': a.split('/')[0]} for a in self.target['addresses']]
        self.payload = {'operation_id': 'synthetic-operation', 'private_root': str(root),
            'foundation': {'operation_id': 'synthetic-operation',
                'policies': [{'id': 'synthetic-policy', 'compatible': True}]},
            'values': {'api_endpoint': 'api.synthetic.test', 'public_hostname': 'app.synthetic.test',
                'api_ip': '10.8.0.20', 'https_ip': '10.8.0.20', 'method': 'node_vip',
                'addresses_reserved': True, 'cidrs_reviewed': True, 'policy_id': 'synthetic-policy',
                'pod_cidr': '10.42.0.0/16', 'service_cidr': '10.43.0.0/16', 'existing_cidrs': '10.9.0.0/24'}}

    def build(self):
        with patch.object(bootstrap_config, 'verified_nodes', return_value=(self.target, self.nodes)):
            return bootstrap_config.build(self.payload)

    def test_reuses_decisions_and_does_not_qualify_gates(self):
        bundle = self.build()
        self.assertEqual(bundle['config']['github']['repository'], 'ArcIA')
        self.assertEqual(bundle['config']['nodes'][2]['name'], 'arcia-k3s-03')
        self.assertEqual(set(bundle['config']['gates'].values()), {'pending'})
        self.assertFalse(bundle['config']['network']['existing_cidrs_reviewed'])
        self.assertIn('10.8.0.0/24', bundle['config']['network']['existing_cidrs'])
        self.assertRegex(bundle['k3s_token'], r'^[a-f0-9]{64}$')

    def test_rejects_unreserved_addresses(self):
        self.payload['values']['addresses_reserved'] = False
        with self.assertRaises(harness.Invalid): self.build()

    def test_unknown_future_networks_do_not_assert_exhaustiveness(self):
        self.payload['values']['cidrs_reviewed'] = False
        self.payload['values']['existing_cidrs'] = ''
        bundle = self.build()
        self.assertFalse(bundle['endpoint_design']['enterprise_vpn_cidrs_attested'])
        self.assertTrue(bundle['endpoint_design']['future_networks_unknown'])
        self.assertTrue(bundle['endpoint_design']['vpn_activation_requires_route_guard'])
        self.assertEqual(bundle['config']['network']['existing_cidrs'], ['10.8.0.0/24'])
        self.assertEqual(bundle['config']['gates']['network_review'], 'pending')

    def test_rejects_node_gateway_and_public_endpoint_ips(self):
        for address in ('10.8.0.11', '10.8.0.1', '8.8.8.8', '10.8.0.0', '10.8.0.255', '10.9.0.20'):
            with self.subTest(address=address):
                self.payload['values']['api_ip'] = address
                with self.assertRaises(harness.Invalid): self.build()

    def test_rejects_overlap_and_foreign_policy(self):
        self.payload['values']['existing_cidrs'] = '10.0.0.0/8'
        with self.assertRaisesRegex(harness.Invalid, 'CIDR_OVERLAP'): self.build()
        self.payload['values']['existing_cidrs'] = ''
        self.payload['values']['policy_id'] = 'foreign-policy'
        with self.assertRaisesRegex(harness.Invalid, 'COMPATIBLE_POLICY_REQUIRED'): self.build()

    def test_rejects_foreign_foundation_operation(self):
        self.payload['foundation']['operation_id'] = 'foreign-operation'
        with self.assertRaisesRegex(harness.Invalid, 'FOUNDATION_SCOPE'): self.build()

    def test_rejects_numeric_or_short_dns(self):
        for value in ('10.8.0.20', 'api'):
            self.payload['values']['api_endpoint'] = value
            with self.assertRaisesRegex(harness.Invalid, 'ENDPOINT_FQDN_REQUIRED'): self.build()


class NetworkProbeTests(unittest.TestCase):
    def test_cache_flush_is_explicit_and_keeps_dns_exact(self):
        from types import SimpleNamespace
        values = {'nodes': ['192.0.2.11']*3, 'vcenter': 'synthetic.test', 'vcenter_port': 443,
                  'endpoints': {'api': {'name': 'api.synthetic.test', 'ip': '192.0.2.20'}}}
        for flush in (False, True):
            values['flush_dns_cache'] = flush
            results = [SimpleNamespace(stdout=b'[{"ifname":"eth0","mtu":1500}]'),
                       SimpleNamespace(stdout=b'[]'), SimpleNamespace(stdout=b'Link 2 (eth0): 192.0.2.53')]
            if flush: results.insert(0, SimpleNamespace(stdout=b''))
            with patch.object(node_network_probe, 'route', return_value={'dev': 'eth0'}), \
                 patch.object(node_network_probe, 'tcp', return_value=True), \
                 patch.object(node_network_probe, 'tls', return_value=True), \
                 patch.object(node_network_probe.subprocess, 'run', side_effect=results) as run, \
                 patch.object(node_network_probe.socket, 'getaddrinfo', return_value=[(2,1,6,'',('192.0.2.20',0))]), \
                 patch.object(node_network_probe.Path, 'read_text', return_value='nameserver 127.0.0.53\n'):
                result = node_network_probe.probe(values)
            self.assertEqual(result['dns_cache_flushed'], flush)
            self.assertEqual(any(c.args[0][0] == '/usr/bin/sudo' for c in run.call_args_list), flush)
            self.assertTrue(result['endpoints']['api']['dns_matches_reserved_ip'])
            self.assertEqual(result['resolved_dns'], ['192.0.2.53'])

    def test_failed_peer_connection_is_not_qualified(self):
        from types import SimpleNamespace
        links = SimpleNamespace(stdout=b'[{"ifname":"eth0","mtu":1500}]')
        with patch.object(node_network_probe, 'route', return_value={'dev': 'eth0'}), \
             patch.object(node_network_probe, 'tcp', return_value=False), \
             patch.object(node_network_probe, 'tls', return_value=True), \
             patch.object(node_network_probe.subprocess, 'run', side_effect=[links, type(links)(stdout=b'[{"dst":"192.0.2.0/24"}]')]), \
             patch.object(node_network_probe.Path, 'read_text', return_value='nameserver 192.0.2.53\n'):
            result = node_network_probe.probe({'nodes': ['192.0.2.11']*3,
                'vcenter': 'synthetic.test', 'vcenter_port': 443})
        self.assertFalse(result['checks']['node_mesh_ssh_tcp'])
        self.assertEqual(set(result['checks']), set(network_preflight.CHECKS))

    def test_private_error_is_not_emitted(self):
        import io
        output = io.StringIO()
        with patch('sys.stdin', io.StringIO('{}')), patch('sys.stdout', output), \
             patch.object(network_preflight, 'collect', side_effect=ValueError('SECRET_ADDRESS')):
            self.assertEqual(network_preflight.main(), 2)
        self.assertNotIn('SECRET', output.getvalue())


class PermissionTests(unittest.TestCase):
    def test_datacenter_root_folders_are_permission_aliases(self):
        from types import SimpleNamespace as Object
        class Datacenter: pass
        root = Object(_moId='root', parent=None)
        dc = Datacenter(); dc._moId='dc'; dc.parent=root
        dc.vmFolder = Object(_moId='vm-root', parent=dc)
        dc.hostFolder=dc.datastoreFolder=dc.networkFolder=None
        folder = Object(_moId='owned-folder', parent=dc.vmFolder)
        nodes = [Object(_moId='vm'+str(i), parent=folder,
                        runtime=Object(host=Object(_moId='host'+str(i)))) for i in range(3)]
        fake_vim = Object(Datacenter=Datacenter, Datastore=lambda ident, stub:Object(_moId=ident),
                          ClusterComputeResource=lambda ident, stub:Object(_moId=ident))
        result = vmware_service_permissions.permission_entities(Object(rootFolder=root),
            {'datastore_id':'ds','cluster_id':'cluster'}, nodes, Object(_stub=None), fake_vim)
        self.assertNotIn('vm-root', result)
        self.assertIn('dc', result)
        self.assertIn('owned-folder', result)
        self.assertEqual(result['root'][1], 'vcenter_root')
        self.assertEqual(result['vm1'][1], 'three_owned_node_vms')

    def test_principal_spelling_does_not_adopt_another_domain(self):
        compare = vmware_service_permissions.same_principal
        self.assertTrue(compare('SYNTHETIC.TEST\\Service', 'service@synthetic.test'))
        self.assertFalse(compare('OTHER.TEST\\Service', 'service@synthetic.test'))
        self.assertFalse(compare('service', 'service@synthetic.test'))

    def test_permission_conflict_is_never_overwritten(self):
        from types import SimpleNamespace
        checker = vmware_service_permissions.check_existing_permission
        self.assertFalse(checker([], 'synthetic-principal', 7))
        existing = SimpleNamespace(principal='synthetic-principal', group=False, roleId=7, propagate=False)
        self.assertTrue(checker([existing], 'synthetic-principal', 7))
        with self.assertRaisesRegex(ValueError, 'EXISTING_PERMISSION_CONFLICT'):
            checker([existing], 'synthetic-principal', 8)
        existing.propagate = True
        with self.assertRaisesRegex(ValueError, 'EXISTING_PERMISSION_CONFLICT'):
            checker([existing], 'synthetic-principal', 7)

    def test_role_plan_has_no_propagation_or_administrator(self):
        path = Path(__file__).resolve().parents[1]/'infra/vmware/csi-permissions.plan.json'
        plan = json.loads(path.read_text())
        self.assertTrue(all(role['propagate'] is False for role in plan['roles']))
        privileges = {p for role in plan['roles'] for p in role['privileges']}
        self.assertFalse(any(p.startswith(('Authorization.', 'VirtualMachine.Inventory.',
            'VirtualMachine.Interact.', 'GuestOperations.', 'Host.Config.')) for p in privileges))


if __name__ == '__main__': unittest.main()
