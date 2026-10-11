import importlib.util
import json
from pathlib import Path
import subprocess
import socket
import ssl
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('vmware_inventory', ROOT / 'scripts/vmware_inventory.py')
vmware = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vmware)


class ConnectionTests(unittest.TestCase):
    def setUp(self):
        self.config = dict(server='vc.example.invalid', port=443, username='synthetic',
                           password='SYNTHETIC_ONLY', ca_file='')

    def test_schema(self):
        self.assertIs(vmware.validate_connection(self.config), self.config)

    def test_url_credentials_refused(self):
        self.config['server'] = 'https://user:CANARY_SECRET@vc.example.invalid'
        with self.assertRaisesRegex(vmware.Invalid, 'SERVER_HOSTNAME_REQUIRED'):
            vmware.validate_connection(self.config)

    def test_no_tls_bypass(self):
        self.config['insecure'] = True
        with self.assertRaisesRegex(vmware.Invalid, 'CONNECTION_FIELDS'):
            vmware.validate_connection(self.config)

    def test_port_bool_refused(self):
        self.config['port'] = True
        with self.assertRaisesRegex(vmware.Invalid, 'PORT_INVALID'):
            vmware.validate_connection(self.config)

    def test_failures_never_echo_credentials(self):
        self.config['server'] = 'https://CANARY_SECRET@example.invalid'
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/vmware_inventory.py')],
                                input=json.dumps(self.config), text=True, capture_output=True)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn('CANARY_SECRET', result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)['code'], 'SERVER_HOSTNAME_REQUIRED')

    def test_safe_error_codes_do_not_include_fault_text(self):
        for exception, code in (
            (ssl.SSLCertVerificationError(1, 'CANARY_SECRET'), 'TLS_TRUST_FAILED'),
            (socket.gaierror('CANARY_SECRET'), 'VCENTER_DNS_FAILED'),
            (TimeoutError('CANARY_SECRET'), 'VCENTER_TIMEOUT'),
            (ConnectionRefusedError('CANARY_SECRET'), 'VCENTER_NETWORK_FAILED'),
            (RuntimeError('CANARY_SECRET'), 'VCENTER_CONNECTION_OR_INVENTORY_FAILED'),
        ):
            self.assertEqual(vmware.safe_error_code(exception), code)


if __name__ == '__main__':
    unittest.main()
