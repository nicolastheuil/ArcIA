import copy
import json
from pathlib import Path
import sys
import unittest
import yaml

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import kubernetes_apps
import privacy_deploy
import routing_bindings


class RoutingBindingTests(unittest.TestCase):
    def documents(self):
        lock=json.loads((ROOT/'versions.lock.yaml').read_text())
        config=json.loads((ROOT/'examples/synthetic/instance.json').read_text())
        pilot={'username':'synthetic','password':'SYNTHETIC_PASSWORD','password_salt':'c3ludGhldGljLXNhbHQxNg==','session_secret':'SYNTHETIC_SIGNING_SECRET'}
        return kubernetes_apps.hermes(lock,config,pilot)

    def test_canonical_render_and_repeat_augmentation_preserve_auto_binding(self):
        docs=self.documents()
        privacy_deploy.augment(docs);privacy_deploy.augment(docs)
        config=next(d for d in docs if d['kind']=='ConfigMap' and d['metadata']['name']=='hermes-pilot-config')
        settings=yaml.safe_load(config['data']['config.yaml'])
        self.assertEqual(settings['model']['base_url'],routing_bindings.BASE)
        self.assertEqual(settings['model']['default'],'auto/smart')
        self.assertNotIn('paid_llm_enabled',settings['platform'])
        deployment=next(d for d in docs if d['kind']=='Deployment')
        env=deployment['spec']['template']['spec']['containers'][0]['env']
        for name in ('OPENAI_API_KEY','OPENAI_BASE_URL'):
            self.assertEqual(sum(e['name']==name for e in env),1)

    def test_live_migration_preserves_identity_volumes_scale_and_optimistic_lock(self):
        docs=self.documents()
        deployment=next(d for d in docs if d['kind']=='Deployment')
        deployment['metadata'].update(uid='synthetic-uid',resourceVersion='123',annotations={'arcia.io/operation-id':'synthetic-operation'})
        deployment['spec']['replicas']=0
        before=copy.deepcopy(deployment)
        config=next(d for d in docs if d['kind']=='ConfigMap' and d['metadata']['name']=='hermes-pilot-config')
        rendered=routing_bindings.render({'arcia-hermes':{'deployment':deployment,'config':config}})
        migrated=rendered[1]
        self.assertEqual(migrated['metadata'],before['metadata'])
        self.assertEqual(migrated['spec']['replicas'],0)
        for field in ('envFrom','volumeMounts'):
            self.assertEqual(migrated['spec']['template']['spec']['containers'][0].get(field),before['spec']['template']['spec']['containers'][0].get(field))
        self.assertEqual([v for v in migrated['spec']['template']['spec']['volumes'] if 'persistentVolumeClaim' in v],[v for v in before['spec']['template']['spec']['volumes'] if 'persistentVolumeClaim' in v])
        self.assertEqual(deployment,before)


if __name__=='__main__':unittest.main()
