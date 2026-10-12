"""Adversarial tests of the export boundary; no Presidio installation on host."""
import importlib.util
import json
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
def module(name,file):
    spec=importlib.util.spec_from_file_location(name,ROOT/'services/privacy'/file)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value
core=module('privacy_core','core.py');wire=module('privacy_wire','wire.py');dns=module('privacy_dns','private_dns.py')
class Analyzer:
    def analyze(self,**kwargs):return []

class PrivacyTests(unittest.TestCase):
    def sanitizer(self,scope='synthetic-a'):return core.Sanitizer(Analyzer(),b'x'*32,scope,['Fictif Conseil'])
    def request(self,**extra):return {'model':'openrouter/free','messages':[{'role':'user','content':'synthetic public text'}],**extra}
    def test_every_preview_channel_is_filtered_and_no_raw_mapping_retained(self):
        fixture='Fictif Conseil alice@example.invalid 10.2.3.4 password=secret-fixture-123'
        value=self.sanitizer().payload({'messages':[{'role':'system','content':fixture}],
            'documents':[fixture],'tool_results':[fixture],'metadata':{'filename':fixture,'title':fixture}})
        raw=json.dumps(value)
        for token in ('Fictif Conseil','alice@example.invalid','10.2.3.4','secret-fixture-123'):self.assertNotIn(token,raw)
        self.assertFalse(value['raw_mapping_stored']);self.assertFalse(value['cloud_authorized'])
    def test_pseudonyms_are_stable_within_scope_and_distinct_between_scopes(self):
        a=self.sanitizer().text('alice@example.invalid')[0]
        self.assertEqual(a,self.sanitizer().text('alice@example.invalid')[0])
        self.assertNotEqual(a,self.sanitizer('other').text('alice@example.invalid')[0])
    def test_unicode_formatting_cannot_hide_private_identifier(self):
        self.assertNotIn('Conseil',self.sanitizer().text('Fictif Con\u200bseil')[0])
    def test_cloud_overrides_and_image_payloads_fail_closed(self):
        for extra in ({'provider':{'zdr':False}},{'user':'alice@example.invalid'},
                      {'messages':[{'role':'user','content':[{'type':'image_url','image_url':{'url':'https://example.invalid'}}]}]}):
            with self.subTest(extra=extra),self.assertRaises(core.Blocked):self.sanitizer().completion(self.request(**extra))
    def test_tool_arguments_and_schema_descriptions_are_filtered(self):
        value=self.request(messages=[{'role':'assistant','content':None,'tool_calls':[{'id':'call_demo','type':'function',
            'function':{'name':'lookup','arguments':json.dumps({'query':'alice@example.invalid'})}}]},
            {'role':'tool','tool_call_id':'call_demo','content':'10.2.3.4'}],tools=[{'type':'function','function':{'name':'lookup',
                'description':'Fictif Conseil','parameters':{'type':'object','properties':{'query':{'type':'string'}}}}}])
        result,_=self.sanitizer().completion(value);raw=json.dumps(result)
        for token in ('alice@example.invalid','10.2.3.4','Fictif Conseil'):self.assertNotIn(token,raw)
        self.assertEqual(result['messages'][0]['tool_calls'][0]['function']['name'],'lookup')
    def test_sensitive_schema_key_blocks_instead_of_exporting_or_renaming(self):
        with self.assertRaises(core.Blocked):self.sanitizer().completion(self.request(response_format={'json_schema':{'alice@example.invalid':{}}}))
    def test_encoded_content_and_huge_input_are_blocked(self):
        for text in ('A'*120,'data:application/pdf;base64,AAAA','z'*100001):
            with self.subTest(size=len(text)),self.assertRaises(core.Blocked):self.sanitizer().text(text)
    def test_attestation_rejects_tampering_and_replay(self):
        key=b'k'*32;raw,signature=wire.encode({'synthetic':'ok'},key);seen={}
        self.assertEqual(wire.decode(raw,signature,key,seen),{'synthetic':'ok'})
        with self.assertRaisesRegex(ValueError,'REPLAY'):wire.decode(raw,signature,key,seen)
        with self.assertRaisesRegex(ValueError,'BAD_ATTESTATION'):wire.decode(raw+b' ',signature,key,{})
    def test_expired_attestation_cannot_be_replayed_after_restart(self):
        with patch.object(wire.time,'time',return_value=10):raw,signature=wire.encode({},b'x'*32)
        with patch.object(wire.time,'time',return_value=1000),self.assertRaisesRegex(ValueError,'EXPIRED'):wire.decode(raw,signature,b'x'*32,{})
    def test_private_dns_never_forwards_unknown_names(self):
        def packet(name):return struct.pack('!6H',1,0x100,1,0,0,0)+b''.join(bytes([len(s)])+s.encode() for s in name.split('.'))+b'\0'+struct.pack('!HH',1,1)
        allowed=dns.answer(packet('knowledge.internal'),{'knowledge.internal':'192.0.2.1'})
        refused=dns.answer(packet('secret.exfil.invalid'),{'knowledge.internal':'192.0.2.1'})
        self.assertEqual(struct.unpack('!6H',allowed[:12])[3],1)
        self.assertEqual(struct.unpack('!6H',refused[:12])[1]&15,5)
    def test_private_dns_rejects_compressed_or_truncated_questions(self):
        malformed=struct.pack('!6H',1,0,1,0,0,0)+b'\xc0\x0c'
        self.assertEqual(struct.unpack('!6H',dns.answer(malformed,{})[:12])[1]&15,1)
    def test_deployment_separates_raw_payloads_from_provider_credentials(self):
        import privacy_deploy
        value=privacy_deploy.payload();deployment=value['deployment']['spec']['template']['spec']
        self.assertFalse(deployment['automountServiceAccountToken'])
        self.assertNotIn('cloud-provider',json.dumps(deployment))
        policy=next(d for d in value['documents'] if d['kind']=='NetworkPolicy' and d['metadata']['name']=='local-sanitizer-only')
        self.assertNotIn('ipBlock',json.dumps(policy))
        self.assertIn('privacy',str(privacy_deploy.hermes_policy()))

if __name__=='__main__':unittest.main()
