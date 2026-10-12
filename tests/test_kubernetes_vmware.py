import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import kubernetes_vmware as vmware
import node_kubernetes as node
import ssh_transport


class VMwareRenderTests(unittest.TestCase):
    def setUp(self):
        self.lock=json.loads((vmware.ROOT/'versions.lock.yaml').read_text())
        self.operation='9645701a-17fb-49bf-966b-c345c5c6076a'

    def render(self):
        return vmware.render(self.lock,self.operation,
            {'server':'vc.synthetic.test','port':443,'certificate_pem':'SYNTHETIC_CERT'},
            {'operation_id':self.operation,'status':'created_verified','username':'synthetic@local',
                'password':'SYNTHETIC_SECRET'},['synthetic-dc'],'synthetic-policy')

    def test_secret_only_in_secrets_and_no_nodeport_or_cluster_admin(self):
        documents=self.render()
        for doc in documents:
            if doc['kind']!='Secret': self.assertNotIn('SYNTHETIC_SECRET',json.dumps(doc))
            self.assertNotIn('cluster-admin',json.dumps(doc))
            if doc['kind']=='Service': self.assertNotEqual(doc['spec'].get('type'),'NodePort')
        secrets=[d for d in documents if d['kind']=='Secret']
        self.assertEqual(len(secrets),2)
        self.assertTrue(all('ca.crt' in d['stringData'] for d in secrets))
        self.assertTrue(all(d['metadata']['annotations']['arcia.io/operation-id']==self.operation for d in documents))

    def test_version_skew_blocks_render(self):
        self.lock['components']['vsphere_cpi']['version']='v1.35.1'
        with self.assertRaisesRegex(ValueError,'CPI_KUBERNETES_MINOR_MISMATCH'): self.render()

    def test_foreign_resource_blocks_all_mutation(self):
        documents=self.render()
        foreign={'metadata':{'annotations':{'arcia.io/operation-id':'foreign'}}}
        with patch.object(node,'kubectl',return_value=json.dumps(foreign)) as call:
            with self.assertRaisesRegex(ValueError,'FOREIGN_KUBERNETES_RESOURCE'):
                node.install_vmware({'operation_id':self.operation,'documents':documents})
            self.assertEqual(call.call_count,1)
            self.assertEqual(call.call_args.args[0],'get')

    def test_modified_vendor_source_refused(self):
        self.lock['vmware_foundation']['sources']['cpi-daemonset.yaml']['rendered_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'VMWARE_SOURCE_HASH_MISMATCH'): self.render()


if __name__=='__main__': unittest.main()
