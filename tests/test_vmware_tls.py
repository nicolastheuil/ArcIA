import hashlib
import importlib.util
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('vmware_tls', ROOT / 'scripts/vmware_inventory.py')
vmware = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vmware)


@unittest.skipUnless(shutil.which('openssl'), 'openssl required for synthetic local TLS integration')
class PinningTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.fingerprints = []
        for index in (0, 1):
            key, cert = self.root / f'{index}.key', self.root / f'{index}.crt'
            subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                            '-keyout', str(key), '-out', str(cert), '-days', '1',
                            '-subj', '/CN=localhost'], check=True, capture_output=True)
            der = ssl.PEM_cert_to_DER_cert(cert.read_text())
            self.fingerprints.append(hashlib.sha256(der).hexdigest())

    def tearDown(self):
        self.temporary.cleanup()

    def round_trip(self, client_context, certificate_index, expected):
        server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_context.load_cert_chain(self.root / f'{certificate_index}.crt',
                                       self.root / f'{certificate_index}.key')
        received, failures = [], []
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            listener.listen()
            listener.settimeout(5)

            def serve():
                try:
                    connection, _ = listener.accept()
                    with server_context.wrap_socket(connection, server_side=True) as channel:
                        channel.settimeout(5)
                        received.append(channel.recv(1024))
                except Exception as exc:
                    failures.append(type(exc).__name__)

            worker = threading.Thread(target=serve, daemon=True)
            worker.start()
            with socket.create_connection(listener.getsockname(), timeout=5) as tcp:
                if expected:
                    with client_context.wrap_socket(tcp, server_hostname='localhost') as channel:
                        channel.sendall(b'SYNTHETIC_AUTH_CANARY')
                else:
                    with self.assertRaisesRegex(vmware.Invalid, 'TLS_FINGERPRINT_CHANGED'):
                        with client_context.wrap_socket(tcp, server_hostname='localhost') as channel:
                            channel.sendall(b'SYNTHETIC_AUTH_CANARY')
            worker.join(timeout=6)
            self.assertFalse(worker.is_alive())
        if expected:
            self.assertEqual(failures, [])
            self.assertEqual(received, [b'SYNTHETIC_AUTH_CANARY'])
        else:
            # TLS 1.3 can see the immediate close while sending session tickets.
            self.assertTrue(all(item in ('BrokenPipeError', 'ConnectionResetError') for item in failures))
            self.assertNotIn(b'SYNTHETIC_AUTH_CANARY', received)
            self.assertTrue(all(item == b'' for item in received))

    def test_accepted_self_signed_certificate_connects(self):
        self.round_trip(vmware.PinnedTLSContext(self.fingerprints[0]), 0, True)

    def test_reused_context_blocks_changed_certificate_before_authentication(self):
        context = vmware.PinnedTLSContext(self.fingerprints[0])
        self.round_trip(context, 0, True)
        self.round_trip(context, 1, False)


if __name__ == '__main__':
    unittest.main()
