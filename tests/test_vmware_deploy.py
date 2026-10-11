import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from xml.etree import ElementTree

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import vmware_deploy as deploy


class DeploymentInputTests(unittest.TestCase):
    def setUp(self):
        self.target={'schema_version':1,'cluster_id':'domain-c1','datastore_id':'datastore-1',
            'network_id':'dvportgroup-1','folder_id':'group-v1','addresses':['10.20.0.11/24','10.20.0.12/24','10.20.0.13/24'],
            'gateway':'10.20.0.1','dns':['10.20.0.1'],'ntp':['ntp.example.invalid'],
            'ssh_user':'synthetic','ssh_public_key_path':'synthetic.pub'}

    def test_valid_input(self):
        deploy.validate_target(self.target)

    def test_duplicate_address_refused(self):
        self.target['addresses'][2]=self.target['addresses'][0]
        with self.assertRaisesRegex(deploy.Invalid,'IP_ADDRESSES_DUPLICATE'):
            deploy.validate_target(self.target)

    def test_wrong_gateway_refused(self):
        self.target['gateway']='10.21.0.1'
        with self.assertRaisesRegex(deploy.Invalid,'GATEWAY_OR_DNS_INVALID'):
            deploy.validate_target(self.target)

    def test_root_identity_refused(self):
        self.target['ssh_user']='root'
        with self.assertRaisesRegex(deploy.Invalid,'PERSONAL_SSH_ACCOUNT_REQUIRED'):
            deploy.validate_target(self.target)

    def test_private_key_reference_refused(self):
        self.target['ssh_public_key_path']='private_key'
        with self.assertRaisesRegex(deploy.Invalid,'PUBLIC_KEY_FILE_REQUIRED'):
            deploy.validate_target(self.target)

    def test_bootstrap_has_unique_metadata_and_no_password_auth(self):
        instance='12345678-1234-1234-1234-123456789abc'
        contents=deploy.seed_contents(self.target,1,'ssh-ed25519 SYNTHETIC',instance,'02:00:00:00:00:01')
        user=json.loads(contents['user-data'].split('\n',1)[1])
        self.assertFalse(user['ssh_pwauth'])
        self.assertTrue(user['ssh_deletekeys'])
        self.assertEqual(user['hostname'],'arcia-k3s-02')
        self.assertEqual(json.loads(contents['meta-data'])['instance-id'],instance)
        self.assertEqual(json.loads(contents['network-config'])['ethernets']['arcia0']['match']['macaddress'],'02:00:00:00:00:01')

    def test_ovf_contains_fixed_resources_and_no_private_config(self):
        root=ElementTree.fromstring(deploy.ovf_descriptor(100,'debian12_64Guest'))
        ns={'rasd':'http://schemas.dmtf.org/wbem/wscim/1/cim-schema/2/CIM_ResourceAllocationSettingData'}
        quantities=[x.text for x in root.findall('.//rasd:VirtualQuantity',ns)]
        self.assertEqual(quantities,['8','32768'])

    @unittest.skipUnless(importlib.util.find_spec('pyVmomi'),'VMware SDK required')
    def test_foreign_placement_rule_is_refused(self):
        from pyVmomi import vim
        class SyntheticVM(vim.VirtualMachine):
            @property
            def name(self): return {'vm-1':deploy.NAMES[0],'vm-2':deploy.NAMES[1],'vm-3':deploy.NAMES[2],'vm-4':'foreign'}[self._moId]
        nodes=[SyntheticVM(f'vm-{i}') for i in (1,2,3)]
        rule=vim.cluster.AntiAffinityRuleSpec(name='arcia-k3s-separate-esxi',enabled=True,vm=[nodes[0],nodes[1],SyntheticVM('vm-4')])
        cluster=SimpleNamespace(configurationEx=SimpleNamespace(rule=[rule]))
        with self.assertRaisesRegex(deploy.Invalid,'EXISTING_PLACEMENT_RULE_REFUSED'):
            deploy.ensure_placement(cluster,nodes,None,None)

    @unittest.skipUnless(importlib.util.find_spec('pycdlib'),'ISO library required')
    def test_nocloud_iso_can_be_read_back(self):
        import io
        import pycdlib
        contents=deploy.seed_contents(self.target,0,'ssh-ed25519 SYNTHETIC','12345678-1234-1234-1234-123456789abc','02:00:00:00:00:01')
        image=deploy.make_seed(contents)
        iso=pycdlib.PyCdlib(); iso.open_fp(io.BytesIO(image))
        try:
            self.assertEqual(iso.pvd.volume_identifier.decode().strip(),'CIDATA')
            for name,value in contents.items():
                output=io.BytesIO(); iso.get_file_from_iso_fp(output,rr_path='/'+name)
                self.assertEqual(output.getvalue().decode(),value)
        finally: iso.close()


if __name__=='__main__': unittest.main()
