import copy
import json
from pathlib import Path
import sys
import unittest
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import personal_cleanup as cleanup


class PersonalCleanupTests(unittest.TestCase):
    def setUp(self):
        self.missing = True
        self.error = 404
        self.writes = []
        self.ns = 'arcia-user-p01'
        self.settings = {'hostname': 'synthetic.example.invalid', 'slots': [{'id': 'p01', 'namespace': self.ns}]}
        self.binding = {'issuer': 'https://synthetic.example.invalid/identity/realms/arcia', 'subject': 'synthetic-subject'}
        self.claims = [{'metadata': {'name': name, 'uid': name+'-uid', 'annotations': {'arcia.io/operation-id': 'synthetic'}},
                        'spec': {'volumeName': name+'-pv'}} for name in ('hermes-pilot-state', 'hermes-tools')]
        self.pvs = {c['spec']['volumeName']: {'metadata': {'uid': c['metadata']['name']+'-pv-uid', 'resourceVersion':'5'},
                    'spec': {'persistentVolumeReclaimPolicy': 'Delete', 'csi': {'driver': 'csi.vsphere.vmware.com'},
                             'claimRef': {'namespace': self.ns, 'name': c['metadata']['name'], 'uid': c['metadata']['uid']}}}
                    for c in self.claims}
        self.version = '1'

    def resource(self, path=''):
        if not path:
            return {'id': 'synthetic-realm', 'attributes': {'arcia.operation-id': 'synthetic'}}
        if self.missing:
            raise HTTPError('https://synthetic.invalid', self.error, 'synthetic', {}, None)
        return {'enabled': False}

    def owned(self, kind, name, namespace, operation):
        doc = {'metadata': {'uid': kind+'-uid', 'resourceVersion': self.version,
                            'labels': {'arcia.io/personal-pool': 'true'}}}
        if name == 'portal-config': doc['data'] = {'portal.json': json.dumps(self.settings)}
        if name == 'slot-binding': doc['data'] = {'binding.json': json.dumps(self.binding)}
        return doc

    def kube(self, *args, **kwargs):
        if args[:2] == ('get', 'pvc'): return json.dumps({'items': self.claims})
        if args[:2] == ('get', 'pv'): return json.dumps(self.pvs[args[2]])
        self.writes.append((args, kwargs))
        return ''

    def plan(self):
        return cleanup.plan(self, self.owned, self.kube, 'synthetic', now=1000)

    def apply(self, proposed, **kwargs):
        return cleanup.apply(self, self.owned, self.kube, 'synthetic', proposed,
                             proposed['plan_sha256'], 'operator_exception_for_named_personal_cleanup', now=kwargs.get('now',1001))

    def test_only_missing_users_are_candidates_not_disabled_users_or_free_slots(self):
        self.assertEqual(len(self.plan()['candidates']), 1)
        self.missing = False
        self.assertEqual(self.plan()['candidates'], [])
        self.binding = {}
        self.assertEqual(self.plan()['candidates'], [])
        self.assertFalse(self.writes)

    def test_read_failure_cannot_be_interpreted_as_deleted_user(self):
        for code in (401,403,500):
            self.error = code
            with self.assertRaises(HTTPError): self.plan()
        self.assertFalse(self.writes)

    def test_foreign_binding_claim_or_retained_volume_refused(self):
        self.binding['issuer'] = 'https://other.invalid'
        with self.assertRaisesRegex(ValueError, 'FOREIGN_ISSUER'): self.plan()
        self.setUp();self.claims[0]['metadata']['annotations']['arcia.io/operation-id'] = 'other'
        with self.assertRaisesRegex(ValueError, 'FOREIGN_CLAIM'): self.plan()
        self.setUp();self.pvs['hermes-tools-pv']['spec']['persistentVolumeReclaimPolicy'] = 'Unknown'
        with self.assertRaisesRegex(ValueError, 'VOLUME_SCOPE'): self.plan()
        self.assertFalse(self.writes)

    def test_expiry_tamper_recreated_user_or_binding_drift_cannot_mutate(self):
        p = self.plan()
        with self.assertRaisesRegex(ValueError, 'STALE_OR_CHANGED'): self.apply(p, now=1600)
        changed = copy.deepcopy(p);changed['candidates'][0]['namespace'] = 'arcia-identity'
        with self.assertRaisesRegex(ValueError, 'STALE_OR_CHANGED'): self.apply(changed)
        self.version = '2'
        with self.assertRaisesRegex(ValueError, 'STALE_OR_CHANGED'): self.apply(p)
        self.version = '1';self.missing = False
        with self.assertRaisesRegex(ValueError, 'STALE_OR_CHANGED'): self.apply(p)
        self.assertFalse(self.writes)

    def test_apply_requires_explicit_exception(self):
        p = self.plan()
        with self.assertRaisesRegex(ValueError, 'EXPLICIT_EXCEPTION'):
            cleanup.apply(self,self.owned,self.kube,'synthetic',p,p['plan_sha256'],'teams',now=1001)
        self.assertFalse(self.writes)

    def test_delete_has_uid_and_version_preconditions_and_waits_for_csi_pvs(self):
        result = self.apply(self.plan())
        deletes = [w for w in self.writes if w[0][0] == 'delete']
        self.assertEqual(len(deletes), 1)
        self.assertEqual(deletes[0][0], ('delete','--raw','/api/v1/namespaces/'+self.ns,'-f','-'))
        self.assertEqual(deletes[0][1]['document']['preconditions'], {'uid':'Namespace-uid','resourceVersion':'1'})
        self.assertFalse(any('--force' in args for args,kw in self.writes))
        self.assertEqual(sum(args[:1] == ('wait',) for args,kw in self.writes),4)
        self.assertEqual(result['deleted_pvs'],2)
        self.assertFalse(result['disabled_users_deleted'])

    def test_retained_volumes_are_changed_only_with_exact_uid_and_version_before_deletion(self):
        self.pvs['hermes-tools-pv']['spec']['persistentVolumeReclaimPolicy']='Retain'
        self.apply(self.plan())
        patches=[w for w in self.writes if w[0][0]=='patch']
        self.assertEqual(len(patches),1)
        self.assertEqual(patches[0][0][:3],('patch','pv','hermes-tools-pv'))
        patch=json.loads(patches[0][0][-1])
        self.assertEqual(patch['metadata'],{'uid':'hermes-tools-pv-uid','resourceVersion':'5'})
        self.assertEqual(patch['spec'],{'persistentVolumeReclaimPolicy':'Delete'})
        self.assertLess(self.writes.index(patches[0]),next(i for i,w in enumerate(self.writes) if w[0][0]=='delete'))


if __name__ == '__main__': unittest.main()
