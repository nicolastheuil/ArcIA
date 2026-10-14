import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import validate_bootstrap
import kubernetes_apps
import node_kubernetes


class BootstrapTests(unittest.TestCase):
    def test_current_components_are_covered(self):
        self.assertEqual(validate_bootstrap.validate()['code'],'BOOTSTRAP_COVERAGE_VERIFIED')

    def test_personal_transfer_cannot_be_added_to_platform_contracts(self):
        original=Path.read_text
        def read(path,*args,**kwargs):
            text=original(path,*args,**kwargs)
            if path.name=='qualification.json':
                data=json.loads(text);data['configuration_contracts']['portable_state']={};return json.dumps(data)
            return text
        with patch.object(Path,'read_text',read):
            with self.assertRaisesRegex(ValueError,'PERSONAL_TRANSFER_OUT_OF_SCOPE'):validate_bootstrap.validate()

    def test_personal_transfer_cannot_be_added_to_platform_lock(self):
        original=Path.read_text
        def read(path,*args,**kwargs):
            text=original(path,*args,**kwargs)
            if path.name=='versions.lock.yaml':
                data=json.loads(text);data['portable_state']={};return json.dumps(data)
            return text
        with patch.object(Path,'read_text',read):
            with self.assertRaisesRegex(ValueError,'PERSONAL_TRANSFER_OUT_OF_SCOPE'):validate_bootstrap.validate()

    def test_new_runtime_component_cannot_escape_bootstrap(self):
        original=Path.read_text
        def read(path,*args,**kwargs):
            text=original(path,*args,**kwargs)
            if path.name=='versions.lock.yaml':
                data=json.loads(text);data['components']['new_service']={};return json.dumps(data)
            return text
        with patch.object(Path,'read_text',read):
            with self.assertRaisesRegex(ValueError,'BOOTSTRAP_COVERAGE_COMPONENTS'):validate_bootstrap.validate()

    def test_cleanup_cannot_be_added_to_automatic_bootstrap(self):
        original=Path.read_text
        def read(path,*args,**kwargs):
            text=original(path,*args,**kwargs)
            if path.name=='qualification.json':
                data=json.loads(text)
                next(s for s in data['steps'] if s['id']=='plan_personal_cleanup')['arguments']=['-Action','apply_personal_cleanup']
                return json.dumps(data)
            return text
        with patch.object(Path,'read_text',read):
            with self.assertRaisesRegex(ValueError,'AUTOMATIC_DELETE_REFUSED'):validate_bootstrap.validate()

    def test_seed_preserves_existing_instance_without_apply_or_downgrade(self):
        current={'metadata':{'annotations':{'arcia.io/operation-id':'synthetic'}}}
        with patch.object(node_kubernetes,'kubectl',side_effect=[json.dumps(current),'ready']) as call:
            result=node_kubernetes.install_hermes({'operation_id':'synthetic','bootstrap_base':True})
            self.assertTrue(result['existing_hermes_preserved'])
            self.assertEqual(call.call_count,2)
            self.assertEqual(call.call_args.args[0],'rollout')

    def test_seed_refuses_foreign_instance_before_any_mutation(self):
        current={'metadata':{'annotations':{'arcia.io/operation-id':'other'}}}
        with patch.object(node_kubernetes,'kubectl',return_value=json.dumps(current)) as call:
            with self.assertRaisesRegex(ValueError,'FOREIGN_HERMES_DEPLOYMENT'):
                node_kubernetes.install_hermes({'operation_id':'synthetic','bootstrap_base':True})
            self.assertEqual(call.call_count,1)

    def test_base_render_has_no_uncreated_tools_or_knowledge_dependency(self):
        root=validate_bootstrap.ROOT
        lock=json.loads((root/'versions.lock.yaml').read_text());lock=copy.deepcopy(lock)
        lock['hermes_tools']['enabled']=False;lock['knowledge']['enabled']=False;lock['privacy']['enabled']=False
        config=json.loads((root/'examples/synthetic/instance.json').read_text())
        pilot={'password':'synthetic','password_salt':'c3ludGhldGljLXNhbHQxNg==','session_secret':'synthetic','username':'synthetic'}
        docs=kubernetes_apps.hermes(lock,config,pilot)
        deployment=next(d for d in docs if d['kind']=='Deployment')
        volumes=deployment['spec']['template']['spec']['volumes']
        self.assertNotIn('tools',{v['name'] for v in volumes})
        self.assertNotIn('knowledge-token',{v['name'] for v in volumes})


if __name__=='__main__':unittest.main()
