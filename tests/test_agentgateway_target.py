"""La nouvelle cible ne doit jamais déclencher un déploiement LiteLLM implicite."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import deploy


class AgentgatewayTargetTests(unittest.TestCase):
    def test_wizard_fresh_defaults_select_target_without_migrating_old_config(self):
        import wizard
        with patch.object(deploy, 'find_harness_ssh', return_value=(None, None)), \
                patch.object(wizard, 'detect_current_context', return_value=''):
            fresh = wizard.get_default_config_dict()
            self.assertEqual(fresh['gateway'], {'implementation': 'agentgateway', 'mode': 'qualification_only'})
            fresh.pop('gateway')
            legacy = wizard.ensure_config_defaults(fresh)
            self.assertNotIn('gateway', legacy)

    def test_historical_instance_is_recognized_without_silent_migration(self):
        from services.agentgateway.configuration import deployment_profile
        self.assertEqual(deployment_profile({'llm_gateway': {}}), 'legacy')

    def test_explicit_target_never_falls_through_to_legacy_deployer(self):
        cfg = {'gateway': {'implementation': 'agentgateway', 'mode': 'qualification_only'}}
        with patch.object(deploy, 'K8sRunner') as runner:
            with self.assertRaisesRegex(ValueError, 'agentgateway.*qualification'):
                deploy.deploy_arcia(cfg, str(ROOT))
        runner.assert_not_called()

    def test_unknown_target_and_unqualified_activation_are_rejected(self):
        from services.agentgateway.configuration import deployment_profile
        for target in ({'implementation': 'other'}, {'implementation': 'agentgateway', 'mode': 'active'},
                       {'implementation': 'agentgateway'}, 'agentgateway',
                       {'implementation': 'agentgateway', 'mode': 'qualification_only', 'skip_auth': True}):
            with self.subTest(target=target), self.assertRaises(ValueError):
                deployment_profile({'gateway': target})

    def test_bootstrap_is_closed_and_contains_no_vendor_credentials(self):
        config = yaml.safe_load((ROOT / 'deploy/agentgateway/config.yaml').read_text(encoding='utf-8'))
        routes = config['binds'][0]['listeners'][0]['routes']
        self.assertEqual(config['binds'][0]['port'], 3000)
        self.assertTrue(routes)
        for route in routes:
            self.assertEqual(route['policies']['authorization']['rules'], [{'require': 'false'}])
        self.assertNotIn('apiKey', json.dumps(config))

    def test_manifest_has_no_cluster_identity_or_public_ingress(self):
        docs = list(yaml.safe_load_all((ROOT / 'deploy/manifests/05-agentgateway.yaml').read_text(encoding='utf-8')))
        self.assertEqual({d['kind'] for d in docs}, {'Deployment', 'Service', 'NetworkPolicy'})
        pod = next(d for d in docs if d['kind'] == 'Deployment')['spec']['template']['spec']
        self.assertFalse(pod['automountServiceAccountToken'])
        self.assertNotIn('hostNetwork', pod)
        self.assertTrue(pod['containers'][0]['securityContext']['readOnlyRootFilesystem'])

    def test_registry_distinguishes_new_target_from_legacy_dependencies(self):
        registry = json.loads((ROOT / 'deploy/versions.json').read_text(encoding='utf-8'))
        component = registry['components']['agentgateway']
        self.assertEqual(component['version'], 'v1.6.0')
        self.assertIn('@sha256:', component['image'])
        self.assertEqual(component['qualification'], 'partial_http_jwt_cel')
        self.assertFalse(component['business_activation_allowed'])
        for name in ('litellm-proxy', 'litellm-db'):
            self.assertEqual(registry['components'][name]['scope'], 'legacy_migration_only')


if __name__ == '__main__':
    unittest.main()
