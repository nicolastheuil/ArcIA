import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import node_identity
import kubernetes_apps


class BoundaryDeployTests(unittest.TestCase):
    def setUp(self):
        self.template={'metadata':{'annotations':{'keep':'unchanged'}},'spec':{
            'automountServiceAccountToken':False,
            'containers':[{'command':['/opt/hermes/.venv/bin/python','/opt/arcia-dashboard/boundary.py'],
                'envFrom':[{'secretRef':{'name':'arcia-oidc-runtime'}}]}],
            'volumes':[{'name':'dashboard-boundary','configMap':{'name':'old-code'}},
                {'name':'state','persistentVolumeClaim':{'claimName':'hermes-pilot-state'}}]}}
        self.deployment={'metadata':{'resourceVersion':'2'},'spec':{'replicas':1,'strategy':{'type':'Recreate'},'template':self.template}}
        self.values={'operation_id':'synthetic','boundary_source':'new-code','slot':'p01'}
        self.source='old-code'
    def owned(self,kind,name,namespace,operation):
        if name=='portal-config':return {'data':{'portal.json':json.dumps({'slots':[{'namespace':'arcia-user-p01'}]})}}
        if kind=='Deployment':return copy.deepcopy(self.deployment)
        if kind=='ConfigMap':return {'data':{'boundary.py':self.source}}
        return {'metadata':{'uid':'synthetic-'+name},'spec':{'volumeName':'synthetic-volume-'+name}}

    def test_reapplication_with_current_code_does_not_roll_runtime(self):
        self.source='new-code'
        with patch.object(node_identity,'owned',side_effect=self.owned),patch.object(node_identity,'kube') as kube,patch.object(node_identity,'apply') as apply:
            result=node_identity.reconcile_session_boundary(self.values)
            self.assertEqual(result['active_rollouts'],0);kube.assert_not_called();apply.assert_not_called()

    def test_fresh_renderer_mounts_the_same_generic_boundary_source(self):
        root=Path(__file__).resolve().parents[1]
        lock=json.loads((root/'versions.lock.yaml').read_text())
        config=json.loads((root/'examples/synthetic/instance.json').read_text())
        import base64
        pilot={'username':'synthetic','password':'synthetic-fixture','password_salt':base64.b64encode(b'synthetic-salt16').decode(),
               'session_secret':'synthetic-fixture'}
        docs=kubernetes_apps.hermes(lock,config,pilot)
        boundary=next(d for d in docs if d['kind']=='ConfigMap' and d['metadata']['name']=='dashboard-session-boundary')
        self.assertEqual(boundary['data']['boundary.py'],(root/'services/multiuser/dashboard_boundary.py').read_text())
        deployment=next(d for d in docs if d['kind']=='Deployment')
        self.assertIn('/opt/arcia-dashboard/boundary.py',deployment['spec']['template']['spec']['containers'][0]['command'])

    def test_rollout_preserves_secret_refs_volume_mounts_and_pvc_identity(self):
        with patch.object(node_identity,'owned',side_effect=self.owned),patch.object(node_identity,'kube') as kube,patch.object(node_identity,'apply') as apply:
            result=node_identity.reconcile_session_boundary(self.values)
            self.assertTrue(result['existing_pvcs_preserved']);self.assertFalse(result['credentials_modified'])
            doc=apply.call_args.args[0][0];self.assertTrue(doc['immutable'])
            patch_doc=json.loads(kube.call_args_list[0].args[-1])
            self.assertEqual(patch_doc['metadata']['resourceVersion'],'2')
            template=patch_doc['spec']['template']
            self.assertEqual(template['spec']['containers'],self.template['spec']['containers'])
            self.assertEqual(template['spec']['volumes'][1],self.template['spec']['volumes'][1])
            self.assertEqual(result['active_rollouts'],1)

    def test_foreign_resource_multiple_owners_or_wrong_slot_prevents_every_write(self):
        for change in ('foreign','multiple','slot'):
            self.deployment['spec']['replicas']=2 if change=='multiple' else 1
            def owned(kind,name,namespace,operation):
                if change=='foreign' and kind=='Deployment':raise ValueError('IDENTITY_FOREIGN_RESOURCE')
                return self.owned(kind,name,namespace,operation)
            values={**self.values,'slot':'p02'} if change=='slot' else self.values
            with patch.object(node_identity,'owned',side_effect=owned),patch.object(node_identity,'kube') as kube,patch.object(node_identity,'apply') as apply:
                with self.assertRaises(ValueError):node_identity.reconcile_session_boundary(values)
                kube.assert_not_called();apply.assert_not_called()


if __name__=='__main__':unittest.main()
