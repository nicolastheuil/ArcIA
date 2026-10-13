import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import yaml

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import cluster_foundation
import node_hermes_tools


class ToolMigrationTests(unittest.TestCase):
    def test_configuration_can_be_prepared_when_owner_is_stopped(self):
        config={'metadata':{'annotations':{'arcia.io/operation-id':'synthetic'}},'data':{'config.yaml':'memory: {}\n'}}
        with patch.object(node_hermes_tools,'workload',return_value=({},None)) as owner, patch.object(node_hermes_tools,'kube',return_value=json.dumps(config)) as call:
            self.assertEqual(node_hermes_tools.configuration({'operation_id':'synthetic'})['config'],'memory: {}\n')
            self.assertTrue(owner.call_args.kwargs['allow_stopped'])
            self.assertEqual(call.call_count,1)

    def test_config_drift_refuses_mutation(self):
        deployment={'spec':{'template':{'metadata':{'annotations':{'arcia.io/tools-sha256':'old'}}}}}
        config={'metadata':{'annotations':{'arcia.io/operation-id':'synthetic'}},'data':{'config.yaml':'memory: {}\n'}}
        with patch.object(node_hermes_tools,'workload',return_value=(deployment,None)), patch.object(node_hermes_tools,'kube',return_value=json.dumps(config)) as call:
            with self.assertRaisesRegex(ValueError,'CHANGED_DURING_PREPARATION'):
                node_hermes_tools.install({'operation_id':'synthetic','catalog_sha256':'new','original_config_sha256':'bad'})
            self.assertEqual(call.call_count,1)

    def test_controller_merge_preserves_existing_mcp_and_does_not_need_live_pod(self):
        operation='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
        original='mcp_servers:\n  knowledge:\n    command: synthetic-reader\nmemory: {}\n'
        desired={'mcp_servers':{'arcia_skills':{'command':'synthetic-catalog'}},'memory':{'memory_enabled':True}}
        with patch.object(cluster_foundation,'transport',return_value=({},[{}],[])), patch.object(cluster_foundation,'guest',side_effect=[{'config':original},{'passed':True,'checks':{'synthetic':True}}]) as call, patch('hermes_tools.payload',return_value={'settings':desired}):
            result=cluster_foundation.collect({'operation_id':operation,'action':'install_hermes_tools','instance':{'operation_id':operation,'config':{}}})
            self.assertEqual(result['safe']['status'],'verified')
            sent=call.call_args_list[1].args[4]
            merged=yaml.safe_load(sent['merged_config'])
            self.assertEqual(merged['mcp_servers']['knowledge']['command'],'synthetic-reader')
            self.assertIn('arcia_skills',merged['mcp_servers'])
            self.assertEqual(sent['original_config_sha256'],hashlib.sha256(original.encode()).hexdigest())
