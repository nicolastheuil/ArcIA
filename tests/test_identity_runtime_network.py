import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import identity_deploy
import node_identity


class RuntimeNetworkTests(unittest.TestCase):
    def setUp(self):
        self.config=json.loads((ROOT/'examples/synthetic/instance.json').read_text())
        self.namespaces=['arcia-hermes','arcia-hermes-qualification-b','arcia-user-p01']
        self.documents=[identity_deploy.runtime_policy(self.config,'192.0.2.3',ns) for ns in self.namespaces]
        self.values={'operation_id':'synthetic','documents':self.documents}

    def owned(self,kind,name,namespace,operation):
        if kind=='ConfigMap':return {'data':{'portal.json':json.dumps({'slots':[{'namespace':'arcia-user-p01'}]})}}
        if kind=='NetworkPolicy':return copy.deepcopy(next(d for d in self.documents if d['metadata']['namespace']==namespace))
        return {}

    def test_local_dnat_is_limited_to_exact_ingress_pods_and_tls_port(self):
        for doc in self.documents:
            spec=doc['spec'];self.assertEqual(spec['podSelector'],{'matchLabels':{'app':'hermes-pilot'}})
            external,internal=spec['egress']
            self.assertEqual({p['ipBlock']['cidr'] for p in external['to']},
                {'192.0.2.3/32'}|{n['address']+'/32' for n in self.config['nodes']})
            self.assertEqual(external['ports'],[{'port':443,'protocol':'TCP'}])
            self.assertEqual(internal,{'to':[{'namespaceSelector':{'matchLabels':{'kubernetes.io/metadata.name':'arcia-ingress'}},
                'podSelector':{'matchLabels':{'app':'pilot-https'}}}], 'ports':[{'port':8443,'protocol':'TCP'}]})

    def test_pool_drift_or_foreign_resource_prevents_every_write(self):
        with patch.object(node_identity,'owned',side_effect=self.owned),patch.object(node_identity,'apply') as apply:
            with self.assertRaisesRegex(ValueError,'POOL_DRIFT'):
                node_identity.reconcile_runtime_network({**self.values,'documents':self.documents[:-1]})
            apply.assert_not_called()
        def foreign(kind,name,namespace,operation):
            if kind=='Deployment' and namespace=='arcia-user-p01':raise ValueError('IDENTITY_FOREIGN_RESOURCE')
            return self.owned(kind,name,namespace,operation)
        with patch.object(node_identity,'owned',side_effect=foreign),patch.object(node_identity,'apply') as apply:
            with self.assertRaisesRegex(ValueError,'FOREIGN_RESOURCE'):node_identity.reconcile_runtime_network(self.values)
            apply.assert_not_called()

    def test_reconciliation_writes_only_policies_and_rechecks_all(self):
        with patch.object(node_identity,'owned',side_effect=self.owned),patch.object(node_identity,'apply') as apply:
            result=node_identity.reconcile_runtime_network(self.values)
            apply.assert_called_once_with(self.documents,'synthetic')
            self.assertTrue(result['passed']);self.assertEqual(result['policies_rechecked'],3)
            self.assertFalse(result['runtime_restart_triggered']);self.assertFalse(result['volumes_modified'])

    def test_runtime_probe_reports_failure_without_private_diagnostics(self):
        with patch.object(node_identity,'kube',return_value=json.dumps({'exception_type':'ConnectError','passed':False})) as kube:
            result=node_identity.runtime_oidc_probe('arcia-user-p01',{'metadata':{'name':'synthetic-pod'}})
            self.assertFalse(result['passed']);self.assertEqual(result['exception_type'],'ConnectError')
            source=kube.call_args.args[-1]
            self.assertNotIn('str(e)',source);self.assertIn("r.get('login_start_status')==302",source)


if __name__=='__main__':unittest.main()
