import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import node_vip


class VipGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        for name in ('OWNER','CONF','HEALTH'):
            context=patch.object(node_vip,name,self.root/name);context.start();self.addCleanup(context.stop)
        context=patch.object(node_vip,'run',return_value='[{"dev":"ens192"}]');context.start();self.addCleanup(context.stop)
        self.values={'operation_id':'9645701a-17fb-49bf-966b-c345c5c6076a','nodes':['192.0.2.11','192.0.2.12','192.0.2.13'],
            'node':1,'subnet':'192.0.2.0/24','gateway':'192.0.2.1','vips':['192.0.2.20','192.0.2.21'],
            'vrid':42,'password':'abcDEF12','health_source':'# fixed health\n','packages':{}}

    def test_foreign_configuration_refused_before_any_mutation(self):
        node_vip.CONF.write_text('foreign')
        with self.assertRaisesRegex(ValueError,'FOREIGN_VIP_CONFIGURATION'): node_vip.install(self.values)
        self.assertFalse(node_vip.OWNER.exists())

    def test_reserved_addresses_cannot_overlap_nodes_gateway_or_broadcast(self):
        for address in ('192.0.2.11','192.0.2.1','192.0.2.255','198.51.100.1'):
            with self.subTest(address=address),self.assertRaisesRegex(ValueError,'VIP_SCOPE_INVALID'):
                node_vip.design({**self.values,'vips':[address]})

    def test_exact_owner_does_not_allow_manual_file_drift(self):
        marker,content,_,_=node_vip.design(self.values)
        node_vip.OWNER.write_text(json.dumps(marker));node_vip.CONF.write_text(content+'# altered')
        with self.assertRaisesRegex(ValueError,'VIP_MANUAL_DRIFT'): node_vip.design(self.values)

    def test_existing_owner_cannot_be_adopted_by_different_operation(self):
        marker,_,_,_=node_vip.design(self.values);node_vip.OWNER.write_text(json.dumps(marker))
        with self.assertRaisesRegex(ValueError,'VIP_OWNER_OR_PLAN_CONFLICT'):
            node_vip.design({**self.values,'operation_id':'11111111-1111-1111-1111-111111111111'})

    def test_same_endpoint_address_is_only_advertised_once(self):
        _,content,_,vips=node_vip.design({**self.values,'vips':['192.0.2.20']*2})
        self.assertEqual(vips,['192.0.2.20']);self.assertEqual(content.count('192.0.2.20/24'),1)
        self.assertNotIn('use_vmac',content);self.assertIn('init_fail',content);self.assertIn('nopreempt',content)


if __name__=='__main__': unittest.main()
