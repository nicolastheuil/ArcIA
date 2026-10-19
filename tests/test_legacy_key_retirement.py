"""Retrait ciblé de l'ancienne clé statique, sans toucher aux clés nominatives."""
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import deploy


class LegacyKeyRetirementTests(unittest.TestCase):
    def load_service(self):
        spec = importlib.util.spec_from_file_location('legacy_key', ROOT / 'services/litellm/retire_legacy_key.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_manifest_does_not_recreate_static_key(self):
        manifest = (ROOT / 'deploy/manifests/05-litellm.yaml').read_text(encoding='utf-8')
        self.assertNotIn('/key/generate', manifest)
        self.assertNotIn('postStart:', manifest)

    def test_only_known_legacy_identity_is_deleted_and_reapplication_is_safe(self):
        service = self.load_service()
        calls = []
        records = [{'token': service.LEGACY_KEY_HASH, 'key_alias': service.LEGACY_KEY_ALIAS}]

        def request(path, payload=None):
            calls.append((path, payload))
            if path == '/key/delete':
                records.clear()
                return {'deleted_keys': [service.LEGACY_KEY_HASH]}
            return {'keys': list(records), 'total_count': len(records)}

        self.assertTrue(service.retire(request)['retired'])
        self.assertFalse(service.retire(request)['retired'])
        self.assertEqual([c for c in calls if c[1]], [('/key/delete', {'keys': [service.LEGACY_KEY_HASH]})])

    def test_same_alias_with_another_token_is_preserved(self):
        service = self.load_service()
        calls = []
        def request(path, payload=None):
            calls.append((path, payload))
            return {'keys': [{'token': 'synthetic-other-hash', 'key_alias': service.LEGACY_KEY_ALIAS}]}
        self.assertFalse(service.retire(request)['retired'])
        self.assertEqual(len(calls), 1)

    def test_delete_must_be_verified(self):
        service = self.load_service()
        record = {'token': service.LEGACY_KEY_HASH, 'key_alias': service.LEGACY_KEY_ALIAS}
        with self.assertRaises(RuntimeError):
            service.retire(lambda path, payload=None: {'keys': [record]})

    def test_consumer_guard_requires_environment_config_and_no_legacy_key(self):
        service = self.load_service()
        env = {'ENABLE_PERSISTENT_CONFIG': 'false', 'LITELLM_MASTER_KEY': 'sk-synthetic',
               'OPENAI_API_KEYS': 'sk-synthetic;synthetic-hermes'}
        self.assertTrue(service.consumer_safe(env))
        self.assertFalse(service.consumer_safe({**env, 'ENABLE_PERSISTENT_CONFIG': 'true'}))
        self.assertFalse(service.consumer_safe({**env, 'OPENAI_API_KEYS': 'unrecognized;synthetic-hermes'}))

    def test_orchestrator_does_not_delete_when_consumer_check_fails(self):
        class Runner:
            calls = []
            def run(self, args, stdin_input=None, timeout=None):
                self.calls.append(args)
                return 0, 'ARCIA_LEGACY_CONSUMER_SAFE=false\n', ''
        runner = Runner()
        result = deploy.retire_legacy_webui_key(runner, 'arcia', str(ROOT))
        self.assertFalse(result['retired'])
        self.assertEqual(len(runner.calls), 1)

    def test_orchestrator_runs_actual_service_after_safe_consumer_check(self):
        class Runner:
            calls = []
            def run(self, args, stdin_input=None, timeout=None):
                self.calls.append((args, stdin_input))
                if len(self.calls) == 1:
                    return 0, 'ARCIA_LEGACY_CONSUMER_SAFE=true\n', ''
                return 0, 'ARCIA_LEGACY_KEY_RESULT={"retired": true, "verified_absent": true}\n', ''
        runner = Runner()
        result = deploy.retire_legacy_webui_key(runner, 'arcia', str(ROOT))
        self.assertTrue(result['verified_absent'])
        self.assertIn('deployment/litellm-proxy', runner.calls[1][0])
        self.assertIn('def retire(', runner.calls[1][1])


if __name__ == '__main__':
    unittest.main()
