import base64
import contextlib
import io
import importlib.util
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import ssh_vmware_preflight as access


class HostTrustTests(unittest.TestCase):
    def setUp(self):
        self.target = {'schema_version': 1, 'cluster_id': 'domain-c1', 'datastore_id': 'datastore-1',
                       'network_id': 'network-1', 'folder_id': 'group-v1',
                       'addresses': ['10.20.0.11/24', '10.20.0.12/24', '10.20.0.13/24'],
                       'gateway': '10.20.0.1', 'dns': ['10.20.0.1'], 'ntp': ['ntp.example.invalid'],
                       'ssh_user': 'synthetic', 'ssh_public_key_path': 'synthetic.pub'}
        self.nodes = []
        for i, name in enumerate(access.NAMES):
            address = self.target['addresses'][i].split('/')[0]
            blob = b'\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20' + bytes([i])*32
            key = base64.b64encode(blob).decode()
            self.nodes.append(dict(node=name, address=address, verified=True,
                                   verification_method='vcenter_console_ocr',
                                   **access.parse_keyscan(address+' ssh-ed25519 '+key, address)))
        self.payload = {'target': self.target, 'operation_id': 'synthetic-operation',
                        'trust': {'operation_id': 'synthetic-operation', 'nodes': self.nodes}}

    def test_three_console_verified_unique_keys_accepted(self):
        self.assertEqual(len(access.verified_nodes(self.payload)[1]), 3)

    def test_unverified_network_scan_blocks_before_authentication(self):
        self.nodes[0]['verified'] = False
        with patch.object(access.subprocess, 'run') as command:
            with self.assertRaisesRegex(access.Invalid, 'SSH_TRUST_REQUIRED'):
                access.preflight(self.payload)
            command.assert_not_called()

    def test_network_only_acceptance_is_not_verification(self):
        self.nodes[0]['verification_method'] = 'keyscan_tofu'
        with self.assertRaisesRegex(access.Invalid, 'SSH_TRUST_REQUIRED'):
            access.verified_nodes(self.payload)

    def test_trust_cannot_be_reused_for_another_deployment(self):
        self.payload['operation_id'] = 'other-operation'
        with self.assertRaisesRegex(access.Invalid, 'SSH_TRUST_SCOPE_INVALID'):
            access.verified_nodes(self.payload)

    def test_trust_cannot_be_reused_for_another_address(self):
        self.nodes[0]['address'] = '10.20.0.99'
        with self.assertRaisesRegex(access.Invalid, 'SSH_TRUST_REQUIRED'):
            access.verified_nodes(self.payload)

    def test_changed_fingerprint_is_refused(self):
        self.nodes[0]['fingerprint'] = self.nodes[1]['fingerprint']
        with self.assertRaisesRegex(access.Invalid, 'SSH_TRUST_INTEGRITY_INVALID'):
            access.verified_nodes(self.payload)

    def test_duplicated_keys_are_refused(self):
        self.nodes[2].update(key=self.nodes[0]['key'], fingerprint=self.nodes[0]['fingerprint'])
        with self.assertRaisesRegex(access.Invalid, 'DUPLICATED_HOST_KEYS'):
            access.verified_nodes(self.payload)

    def test_guestinfo_wrong_challenge_cannot_establish_trust(self):
        from types import SimpleNamespace
        vm = SimpleNamespace(config=SimpleNamespace(extraConfig=[SimpleNamespace(
            key='guestinfo.arcia.ssh-key-proof', value=json.dumps({'challenge':'stale',
                'public_key':'ssh-ed25519 '+self.nodes[0]['key']}))]))
        self.assertIsNone(access.read_guest_proof(vm, 'fresh', self.nodes[0]['address']))
        self.assertEqual(access.read_guest_proof(vm, 'stale', self.nodes[0]['address'])['key'], self.nodes[0]['key'])

    def test_verification_seed_preserves_keys_and_does_not_install_packages(self):
        import io
        try:
            import pycdlib
        except ImportError:
            self.skipTest('pycdlib required')
        with tempfile.TemporaryDirectory() as directory:
            public = Path(directory)/'key.pub'; public.write_text('ssh-ed25519 SYNTHETIC')
            self.target['ssh_public_key_path'] = str(public)
            seed = access.verification_seed(self.target, 0, '12345678-1234-1234-1234-123456789abc', '02:00:00:00:00:01')
            iso = pycdlib.PyCdlib(); iso.open_fp(io.BytesIO(seed))
            try:
                output = io.BytesIO(); iso.get_file_from_iso_fp(output, rr_path='/user-data')
                user = json.loads(output.getvalue().decode().split('\n', 1)[1])
            finally: iso.close()
        self.assertFalse(user['ssh_deletekeys'])
        self.assertFalse(user['package_update'])
        self.assertNotIn('packages', user)
        self.assertNotIn('growpart', user)
        self.assertEqual(len(user['runcmd']), 1)
        self.assertIn('ssh_host_ed25519_key.pub', user['runcmd'][0][2])
        self.assertNotIn('ssh_host_ed25519_key\'', user['runcmd'][0][2])

    @unittest.skipUnless(importlib.util.find_spec('pyVmomi'), 'VMware SDK required')
    def test_client_cd_is_replaced_and_backing_confirmed_before_reboot(self):
        from types import SimpleNamespace
        from pyVmomi import vim
        old = vim.vm.device.VirtualCdrom(key=3000, controllerKey=200, unitNumber=0,
            backing=vim.vm.device.VirtualCdrom.RemoteAtapiBackingInfo(deviceName='synthetic-client', useAutoDetect=True))
        class VM:
            config = SimpleNamespace(hardware=SimpleNamespace(device=[old]))
            def ReconfigVM_Task(self, spec):
                self.spec = spec
                self.config = SimpleNamespace(hardware=SimpleNamespace(device=[spec.deviceChange[0].device]))
                return SimpleNamespace(info=SimpleNamespace(state='success', result=None))
        vm = VM()
        access.configure_proof_cd(vm, old, '[synthetic] node/proof.iso', 'challenge')
        self.assertIsInstance(vm.spec.deviceChange[0].device.backing, vim.vm.device.VirtualCdrom.IsoBackingInfo)
        self.assertEqual(old.backing.deviceName, 'synthetic-client')
        self.assertEqual(vm.spec.extraConfig[0].value, 'pending:challenge')

    @unittest.skipUnless(importlib.util.find_spec('pyVmomi'), 'VMware SDK required')
    def test_unapplied_cd_edit_blocks_before_reboot(self):
        from types import SimpleNamespace
        from pyVmomi import vim
        old = vim.vm.device.VirtualCdrom(key=3000, controllerKey=200, unitNumber=0,
            backing=vim.vm.device.VirtualCdrom.RemoteAtapiBackingInfo())
        vm = SimpleNamespace(config=SimpleNamespace(hardware=SimpleNamespace(device=[old])),
            ReconfigVM_Task=lambda spec: SimpleNamespace(info=SimpleNamespace(state='success', result=None)))
        with self.assertRaisesRegex(access.Invalid, 'VERIFICATION_ISO_NOT_CONNECTED_NO_REBOOT'):
            access.configure_proof_cd(vm, old, '[synthetic] node/proof.iso', 'challenge')

    def test_wrong_scanned_host_is_refused(self):
        with self.assertRaisesRegex(access.Invalid, 'HOST_KEY_SCAN_INVALID'):
            access.parse_keyscan('10.20.0.99 ssh-ed25519 '+self.nodes[0]['key'], '10.20.0.11')

    def test_worker_never_echoes_private_exception(self):
        output = io.StringIO()
        with patch.object(access.sys, 'argv', ['worker', '--discover']), \
             patch.object(access.sys, 'stdin', io.StringIO('{}')), \
             patch.object(access, 'discover', side_effect=RuntimeError('SYNTHETIC_SECRET_CANARY')), \
             contextlib.redirect_stdout(output):
            self.assertEqual(access.main(), 2)
        self.assertNotIn('CANARY', output.getvalue())
        self.assertEqual(json.loads(output.getvalue())['code'], 'SSH_VALIDATION_WORKER_FAILED')

    def test_strict_probe_sanitizes_facts_and_detects_cloned_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root/'ssh').mkdir()
            key = root/'ssh'/'personal'
            key.write_text('SYNTHETIC_PRIVATE_KEY')
            public = key.with_suffix('.pub'); public.write_text('ssh-ed25519 SYNTHETIC_PUBLIC_KEY')
            self.target['ssh_public_key_path'] = str(public)
            self.payload['private_root'] = str(root)
            def completed(command, **kwargs):
                if command[0] == 'ssh-keygen':
                    return subprocess.CompletedProcess(command, 0, 'ssh-ed25519 SYNTHETIC_PUBLIC_KEY', '')
                raw = {'checks': {name: True for name in access.CHECKS},
                       'machine_id': 'a'*32, 'product_uuid': 'b'*32}
                return subprocess.CompletedProcess(command, 0, json.dumps(raw).encode(), b'PRIVATE_CANARY')
            with patch.object(access.subprocess, 'run', side_effect=completed) as run:
                result = access.preflight(self.payload)
            self.assertFalse(result['passed'])
            self.assertFalse(result['machine_id_and_uuid_unique'])
            serialized = json.dumps(result)
            self.assertNotIn('a'*32, serialized)
            self.assertNotIn('PRIVATE_CANARY', serialized)
            self.assertNotIn('10.20.', serialized)
            command = run.call_args.args[0]
            for option in ('StrictHostKeyChecking=yes', 'BatchMode=yes', 'IdentityAgent=none',
                           'HostKeyAlgorithms=ssh-ed25519', 'PasswordAuthentication=no'):
                self.assertIn(option, command)


if __name__ == '__main__': unittest.main()
