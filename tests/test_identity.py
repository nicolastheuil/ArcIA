import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import identity_deploy
import node_identity

spec = importlib.util.spec_from_file_location('identity_realm', ROOT / 'services/identity/realm.py')
realm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(realm)


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.lock = json.loads((ROOT / 'versions.lock.yaml').read_text(encoding='utf-8'))
        self.config = json.loads((ROOT / 'examples/synthetic/instance.json').read_text())
        self.credentials = {'db_password': 'db-fixture', 'bootstrap_username': 'bootstrap-fixture',
                            'bootstrap_password': 'bootstrap-password-fixture'}
        self.pilot = {'tls_certificate': 'certificate-fixture', 'tls_private_key': 'key-fixture'}

    def test_secrets_are_confined_to_secret_objects_and_no_cluster_identity(self):
        values = identity_deploy.payload(self.lock, self.config, self.credentials, self.pilot)
        docs = values['documents']
        rendered = json.dumps([d for d in docs if d['kind'] != 'Secret'])
        self.assertNotIn('db-fixture', rendered)
        self.assertNotIn('bootstrap-password-fixture', rendered)
        self.assertFalse(any(d['kind'] in ('ClusterRoleBinding', 'ClusterRole') for d in docs))
        deployment = next(d for d in docs if d['kind'] == 'Deployment')
        pod = deployment['spec']['template']['spec']
        self.assertFalse(pod['automountServiceAccountToken'])
        self.assertTrue(pod['securityContext']['runAsNonRoot'])
        self.assertEqual(pod['containers'][0]['args'], ['start'])
        self.assertIn('@sha256:', pod['containers'][0]['image'])
        self.assertEqual(deployment['spec']['strategy']['type'], 'Recreate')
        env = {x['name']: x.get('value') for x in pod['containers'][0]['env']}
        self.assertIn('sslmode=verify-full', env['KC_DB_URL'])

    def test_portal_master_and_management_are_bounded(self):
        docs = identity_deploy.payload(self.lock, self.config, self.credentials, self.pilot)['ingress']
        conf = next(d for d in docs if d['kind'] == 'ConfigMap')['data']['nginx.conf']
        self.assertIn('location = /admin/users', conf)
        self.assertIn('location ^~ /identity/realms/master/ { return 404; }', conf)
        self.assertNotIn('keycloak.arcia-identity.svc.cluster.local:9000', conf)
        self.assertIn('proxy_set_header X-Forwarded-Proto https;', conf)

    def test_realm_is_local_by_default_without_self_registration_or_sso(self):
        definition = realm.realm_definition('synthetic-operation')
        self.assertFalse(definition['registrationAllowed'])
        self.assertFalse(definition['loginWithEmailAllowed'])
        self.assertTrue(definition['bruteForceProtected'])
        self.assertTrue(definition['revokeRefreshToken'])
        self.assertNotIn('identityProviders', definition)
        self.assertNotIn('users', definition)
        self.assertFalse(definition['adminEventsDetailsEnabled'])

    def test_runtime_client_prevents_password_and_service_grants_and_wildcards(self):
        client = realm.runtime_client('runtime-id', 'https://example.invalid/auth/callback', 'fixture')
        self.assertFalse(client['directAccessGrantsEnabled'])
        self.assertFalse(client['serviceAccountsEnabled'])
        self.assertFalse(client['implicitFlowEnabled'])
        self.assertTrue(client['publicClient'])
        self.assertNotIn('secret',client)
        self.assertEqual(client['redirectUris'], ['https://example.invalid/auth/callback'])
        self.assertEqual(client['attributes']['pkce.code.challenge.method'], 'S256')

    def test_foreign_resource_refused_before_apply(self):
        doc = {'kind': 'Namespace', 'metadata': {'name': identity_deploy.NS}}
        with patch.object(node_identity, 'kube', return_value=json.dumps({'metadata': {'annotations': {'arcia.io/operation-id': 'other'}}})) as call:
            with self.assertRaisesRegex(ValueError, 'IDENTITY_FOREIGN_RESOURCE'):
                node_identity.apply([doc], 'synthetic')
            self.assertEqual(call.call_count, 1)

    def test_database_password_drift_prevents_any_reapplication(self):
        with patch.object(node_identity, 'owned', return_value={'data': {'password': 'b3RoZXI='}}), patch.object(node_identity, 'apply') as apply:
            with self.assertRaisesRegex(ValueError, 'IDENTITY_DATABASE_CREDENTIAL_DRIFT'):
                node_identity.install({'operation_id': 'synthetic', 'credentials': {'db_password': 'changed'}})
            apply.assert_not_called()

    def test_bootstrap_credentials_are_removed_from_durable_pod(self):
        docs = identity_deploy.payload(self.lock, self.config, self.credentials, self.pilot)['documents']
        node_identity.remove_bootstrap(docs)
        env = next(d for d in docs if d['kind'] == 'Deployment')['spec']['template']['spec']['containers'][0]['env']
        self.assertFalse(any(e['name'].startswith('KC_BOOTSTRAP_ADMIN_') for e in env))
        self.assertTrue(any(e['name'] == 'KC_DB_PASSWORD' for e in env))

    def test_floating_image_refused(self):
        self.lock['components']['keycloak']['image'] = 'quay.io/keycloak/keycloak:latest'
        with self.assertRaisesRegex(ValueError, 'IDENTITY_IMAGE_NOT_PINNED'):
            identity_deploy.payload(self.lock, self.config, self.credentials, self.pilot)


if __name__ == '__main__':
    unittest.main()
