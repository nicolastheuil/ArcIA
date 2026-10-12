import base64
import hashlib
import json
from pathlib import Path
import sys
import unittest
import jsonschema

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import kubernetes_apps as apps


class ApplicationSecurityTests(unittest.TestCase):
    def setUp(self):
        self.lock=json.loads((apps.ROOT/'versions.lock.yaml').read_text())
        self.config=json.loads((apps.ROOT/'examples/synthetic/instance.json').read_text())
        self.pilot={'username':'synthetic','password':'SYNTHETIC_PRIVATE_PASSWORD',
            'password_salt':base64.b64encode(b'synthetic-salt16').decode(),
            'session_secret':'SYNTHETIC_SIGNING_SECRET','tls_certificate':'PUBLIC_CERT',
            'tls_private_key':'SYNTHETIC_PRIVATE_KEY'}

    def test_database_matches_pinned_operator_schema_and_has_three_nodes(self):
        documents=apps.operator(self.lock)
        schema=next(d for d in documents if d['kind']=='CustomResourceDefinition' and
            d['metadata']['name']=='clusters.postgresql.cnpg.io')['spec']['versions'][0]['schema']['openAPIV3Schema']
        cluster=apps.postgres(self.lock,self.config)[-1]
        jsonschema.Draft7Validator(schema).validate(cluster)
        self.assertEqual(cluster['spec']['instances'],3)
        self.assertEqual(cluster['spec']['affinity']['podAntiAffinityType'],'required')
        self.assertEqual(cluster['spec']['postgresql']['synchronous']['dataDurability'],'required')
        self.assertIn('@sha256:',cluster['spec']['imageName'])

    def test_hermes_has_one_owner_no_cloud_credentials_or_egress(self):
        documents=apps.hermes(self.lock,self.config,self.pilot)
        deploy=next(d for d in documents if d['kind']=='Deployment')
        self.assertEqual(deploy['spec']['replicas'],1)
        self.assertEqual(deploy['spec']['strategy']['type'],'Recreate')
        self.assertFalse(deploy['spec']['template']['spec']['automountServiceAccountToken'])
        claim=next(d for d in documents if d['kind']=='PersistentVolumeClaim')
        self.assertEqual(claim['spec']['accessModes'],['ReadWriteOncePod'])
        for doc in documents:
            self.assertNotIn(self.pilot['password'],json.dumps(doc))
            if doc['kind']!='Secret': self.assertNotIn(self.pilot['session_secret'],json.dumps(doc))
            if doc['kind']=='NetworkPolicy': self.assertFalse(doc['spec'].get('egress'))
        encoded=next(d for d in documents if d['kind']=='Secret')['stringData']['HERMES_DASHBOARD_BASIC_AUTH_PASSWORD_HASH']
        scheme,n,r,p,salt,derived=encoded.split('$')
        self.assertEqual(scheme,'scrypt')
        self.assertEqual(base64.b64decode(derived),hashlib.scrypt(self.pilot['password'].encode(),
            salt=base64.b64decode(salt),n=int(n),r=int(r),p=int(p),dklen=32))

    def test_private_tls_key_only_in_secret_rootless_proxy(self):
        documents=apps.ingress(self.lock,self.config,self.pilot)
        for doc in documents:
            if doc['kind']!='Secret': self.assertNotIn(self.pilot['tls_private_key'],json.dumps(doc))
        pod=next(d for d in documents if d['kind']=='DaemonSet')['spec']['template']['spec']
        self.assertFalse(pod['automountServiceAccountToken'])
        self.assertTrue(pod['securityContext']['runAsNonRoot'])
        self.assertFalse(pod.get('hostNetwork',False))
        self.assertTrue(pod['containers'][0]['securityContext']['readOnlyRootFilesystem'])

    def test_vendor_drift_and_tagless_pg_image_refused(self):
        self.lock['cnpg_source']['rendered_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'CNPG_SOURCE_HASH_MISMATCH'): apps.operator(self.lock)
        self.lock['components']['postgres_pgvector']['image']='ghcr.io/cloudnative-pg/postgresql@sha256:'+'0'*64
        with self.assertRaisesRegex(ValueError,'POSTGRES_VERSION_TAG_AND_DIGEST_REQUIRED'): apps.postgres(self.lock,self.config)


if __name__=='__main__': unittest.main()
