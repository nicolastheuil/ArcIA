"""Preuves de qualification : aucun succès de transport ne vaut activation."""
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))


class NativeQualificationTests(unittest.TestCase):
    def test_namespace_ownership_is_checked_before_deployment(self):
        from qualify_gateway_stack import require_owned_namespace
        with self.assertRaises(ValueError):
            require_owned_namespace(None, 'arcia', 'a' * 32)

        class Runner:
            def run(self, *args, **kwargs):
                return 0, '{"metadata":{"annotations":{"arcia.io/qualification":"different"}}}', ''

        with self.assertRaises(ValueError):
            require_owned_namespace(Runner(), 'arcia-qual-gateway-' + 'a' * 12, 'a' * 32)

    def test_claims_and_default_deny_are_required_in_native_configuration(self):
        from qualify_gateway_stack import jwt_qualification_config
        config = jwt_qualification_config()
        policies = config['binds'][0]['listeners'][0]['routes'][0]['policies']
        jwt_config = policies['jwtAuth']
        self.assertEqual(jwt_config['mode'], 'strict')
        self.assertEqual(jwt_config['audiences'], ['arcia-qualification'])
        self.assertEqual(set(jwt_config['jwtValidationOptions']['requiredClaims']), {'iss', 'sub', 'exp', 'aud'})
        self.assertIn('require', policies['authorization']['rules'][0])

    def test_native_authentication_does_not_qualify_llm_dlp_or_a2a(self):
        from qualify_gateway_stack import build_capability_report
        result = build_capability_report({'valid_a': True, 'valid_b': True, 'wrong_tenant': True,
            'wrong_user': True, 'missing_grant': True, 'anonymous': True, 'forged_headers': True,
            'invalid_signature': True, 'expired': True, 'wrong_audience': True, 'wrong_issuer': True,
            'missing_exp': True, 'missing_sub': True}, bootstrap_closed=True)
        self.assertTrue(result['capabilities']['jwt_cel']['qualified'])
        self.assertFalse(result['capabilities']['presidio']['qualified'])
        self.assertFalse(result['capabilities']['chat_a2a']['qualified'])
        self.assertFalse(result['activation_allowed'])


if __name__ == '__main__':
    unittest.main()
