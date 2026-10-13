import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import identity_egress as egress
import node_identity


class IdentityEgressTests(unittest.TestCase):
    def setUp(self):
        self.operation = '00000000-0000-4000-8000-000000000001'
        self.addresses = {egress.HOSTS[0]: ['20.190.128.1'], egress.HOSTS[1]: ['20.190.128.2']}
        self.deployment = {'kind': 'Deployment', 'metadata': {
            'name': 'keycloak', 'namespace': egress.NS, 'uid': 'synthetic-deployment',
            'resourceVersion': '1', 'annotations': {'arcia.io/operation-id': self.operation}},
            'spec': {'selector': {'matchLabels': {'app': 'keycloak'}},
                     'template': {'metadata': {'labels': {'app': 'keycloak'}}}}}

    def test_policy_scopes_exact_ipv4_addresses_and_only_keycloak_tcp443(self):
        policy = egress.policy(self.addresses, self.operation)
        self.assertEqual(policy['spec']['podSelector'], {'matchLabels': {'app': 'keycloak'}})
        self.assertEqual(policy['spec']['policyTypes'], ['Egress'])
        rule = policy['spec']['egress'][0]
        self.assertEqual(rule['ports'], [{'port': 443, 'protocol': 'TCP'}])
        self.assertEqual(rule['to'], [{'ipBlock': {'cidr': '20.190.128.1/32'}},
                                      {'ipBlock': {'cidr': '20.190.128.2/32'}}])
        self.assertNotIn('ingress', policy['spec'])

    def test_private_reserved_multicast_ipv6_and_cidrs_refused(self):
        for ip in ('10.1.2.3', '127.0.0.1', '169.254.169.254', '192.0.2.1', '0.0.0.0',
                   '224.0.0.1', '255.255.255.255', '::1', '2603:1000::1', '20.190.128.0/24'):
            with self.subTest(ip=ip):
                values = copy.deepcopy(self.addresses); values[egress.HOSTS[0]] = [ip]
                with self.assertRaisesRegex(ValueError, 'PUBLIC_IPV4_REQUIRED'):
                    egress.policy(values, self.operation)

    def test_extra_host_empty_and_unbounded_address_lists_refused(self):
        for values in ({**self.addresses, 'example.com': ['1.1.1.1']},
                       {**self.addresses, egress.HOSTS[0]: []},
                       {**self.addresses, egress.HOSTS[0]: ['20.190.128.1'] * 65}):
            with self.assertRaises(ValueError): egress.policy(values, self.operation)

    def test_foreign_resource_and_wrong_deployment_refused(self):
        for path, value in (('owner', 'other'), ('name', 'other'), ('label', 'other')):
            d = copy.deepcopy(self.deployment)
            if path == 'owner': d['metadata']['annotations']['arcia.io/operation-id'] = value
            elif path == 'name': d['metadata']['name'] = value
            else: d['spec']['template']['metadata']['labels']['app'] = value
            with self.assertRaises(ValueError): egress.plan(self.addresses, self.operation, d)

    def test_plan_tamper_expiry_future_and_target_drift_refused(self):
        value = egress.plan(self.addresses, self.operation, self.deployment, now=1000)
        self.assertEqual(egress.validate_plan(value, self.operation, self.deployment, now=1000), value)
        for now in (999, 1600):
            with self.assertRaisesRegex(ValueError, 'STALE_OR_MODIFIED'):
                egress.validate_plan(value, self.operation, self.deployment, now=now)
        changed = copy.deepcopy(value); changed['document']['spec']['egress'][0]['ports'][0]['port'] = 80
        with self.assertRaises(ValueError): egress.validate_plan(changed, self.operation, self.deployment, now=1001)
        d = copy.deepcopy(self.deployment); d['metadata']['resourceVersion'] = '2'
        with self.assertRaises(ValueError): egress.validate_plan(value, self.operation, d, now=1001)

    def test_existing_policy_version_is_bound_to_plan_and_foreign_policy_refused(self):
        policy = egress.policy(self.addresses, self.operation)
        policy['metadata']['resourceVersion'] = '4'
        value = egress.plan(self.addresses, self.operation, self.deployment, policy, now=1000)
        policy['metadata']['resourceVersion'] = '5'
        with self.assertRaises(ValueError): egress.validate_plan(value, self.operation, self.deployment, policy, now=1001)
        policy['metadata']['annotations']['arcia.io/operation-id'] = 'other'
        with self.assertRaisesRegex(ValueError, 'FOREIGN_RESOURCE'):
            egress.plan(self.addresses, self.operation, self.deployment, policy)

    def test_node_plan_never_applies_resources(self):
        source = (Path(egress.__file__)).read_text(encoding='utf-8')
        with patch.object(node_identity, 'owned', side_effect=[self.deployment, None]), \
                patch('socket.getaddrinfo', side_effect=[[(2, 1, 6, '', ('20.190.128.1', 443))],
                                                        [(2, 1, 6, '', ('20.190.128.2', 443))]]), \
                patch.object(node_identity, 'apply') as apply:
            result = node_identity.plan_microsoft_egress({'operation_id': self.operation, 'egress_source': source})
            self.assertEqual(result['address_count'], 2)
            self.assertEqual(result['plan']['approval_required'], 'server_verified_teams')
            apply.assert_not_called()

    def test_dns_failure_cannot_create_partial_policy(self):
        with patch('socket.getaddrinfo', side_effect=OSError('synthetic-resolver-failure')):
            with self.assertRaises(OSError): egress.resolve()

    def repair_values(self):
        plan = egress.plan(self.addresses, self.operation, self.deployment)
        return {'operation_id': self.operation, 'repair_plan': plan,
                'authorized_plan_sha256': plan['plan_sha256'],
                'approval_mode': 'operator_exception_for_named_repair',
                'egress_source': Path(egress.__file__).read_text(encoding='utf-8')}

    def test_repair_without_explicit_named_exception_cannot_mutate(self):
        for mode in (None, 'teams', True):
            values = self.repair_values(); values['approval_mode'] = mode
            with patch.object(node_identity, 'kube') as kube:
                with self.assertRaisesRegex(ValueError, 'EXPLICIT_EXCEPTION_REQUIRED'):
                    node_identity.apply_microsoft_egress_repair(values)
                kube.assert_not_called()

    def test_repair_creates_only_exact_policy_without_pod_rollout(self):
        values = self.repair_values()
        installed = copy.deepcopy(values['repair_plan']['document'])
        installed['metadata']['uid'] = 'synthetic-policy'
        with patch.object(node_identity, 'owned', side_effect=[self.deployment, None, installed]), \
                patch('socket.getaddrinfo', side_effect=[[(2, 1, 6, '', ('20.190.128.1', 443))],
                                                        [(2, 1, 6, '', ('20.190.128.2', 443))]]), \
                patch.object(node_identity, 'kube') as kube:
            result = node_identity.apply_microsoft_egress_repair(values)
            self.assertTrue(result['installed'])
            self.assertFalse(result['teams_approval_verified'])
            self.assertFalse(result['keycloak_rollout_triggered'])
            kube.assert_called_once_with('create', '-f', '-', document=values['repair_plan']['document'])

    def test_dns_drift_requires_new_plan_before_mutation(self):
        values = self.repair_values()
        with patch.object(node_identity, 'owned', side_effect=[self.deployment, None]), \
                patch('socket.getaddrinfo', side_effect=[[(2, 1, 6, '', ('20.190.128.3', 443))],
                                                        [(2, 1, 6, '', ('20.190.128.2', 443))]]), \
                patch.object(node_identity, 'kube') as kube:
            with self.assertRaisesRegex(ValueError, 'DNS_CHANGED_REPLAN_REQUIRED'):
                node_identity.apply_microsoft_egress_repair(values)
            kube.assert_not_called()

    def test_inspection_detects_stale_or_widened_policy_without_apply(self):
        policy = egress.policy(self.addresses, self.operation)
        with patch.object(node_identity, 'owned', side_effect=[self.deployment, policy]), \
                patch('socket.getaddrinfo', side_effect=[[(2, 1, 6, '', ('20.190.128.3', 443))],
                                                        [(2, 1, 6, '', ('20.190.128.2', 443))]]), \
                patch.object(node_identity, 'apply') as apply:
            result = node_identity.inspect_microsoft_egress({'operation_id': self.operation,
                'egress_source': Path(egress.__file__).read_text(encoding='utf-8')})
            self.assertTrue(result['bounded_rule'])
            self.assertFalse(result['current_dns_covered'])
            self.assertEqual(result['missing_address_count'], 1)
            apply.assert_not_called()
        policy['spec']['egress'][0]['to'] = [{'ipBlock': {'cidr': '0.0.0.0/0'}}]
        with patch.object(node_identity, 'owned', side_effect=[self.deployment, policy]), \
                patch('socket.getaddrinfo', side_effect=[[(2, 1, 6, '', ('20.190.128.1', 443))],
                                                        [(2, 1, 6, '', ('20.190.128.2', 443))]]):
            result = node_identity.inspect_microsoft_egress({'operation_id': self.operation,
                'egress_source': Path(egress.__file__).read_text(encoding='utf-8')})
            self.assertFalse(result['bounded_rule'])

    def test_snapshots_union_all_nodes_but_preserve_per_host_address_bounds(self):
        other = copy.deepcopy(self.addresses); other[egress.HOSTS[0]] = ['20.190.128.3']
        combined = egress.merge_resolutions([self.addresses, other])
        self.assertEqual(combined[egress.HOSTS[0]], ['20.190.128.1', '20.190.128.3'])


if __name__ == '__main__':
    unittest.main()
