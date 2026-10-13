import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'services/skills'))
from result_compression import Originals,transform


class ResultCompressionTests(unittest.TestCase):
    def fixture(self):
        rows=[{'id':i,'state':'ok','text':'repeated synthetic event'} for i in range(300)]
        rows[67]={'id':67,'state':'FATAL','text':'critical marker'}
        content=json.dumps(rows,indent=2)
        numbered='\n'.join(str(i+1)+'|'+line for i,line in enumerate(content.splitlines()))
        return json.dumps({'success':True,'content':numbered})

    def test_automatic_overview_and_exact_original_are_available(self):
        original=self.fixture();cache=Originals()
        reduced=transform('read_file',original,{'read_file'},lambda text:json.dumps([{'id':67,'state':'FATAL','text':'critical marker'}]),cache)
        view=json.loads(reduced)
        self.assertTrue(view['arcia_compressed_overview'])
        self.assertIn('critical marker',view['preview'])
        self.assertEqual(cache.get(view['original_reference'])['content'],original)
        self.assertLess(len(reduced),len(original))

    def test_other_user_cache_cannot_restore_reference(self):
        a,b=Originals(),Originals();reference=a.put('synthetic private A')
        with self.assertRaises(ValueError):b.get(reference)

    def test_expiry_eviction_and_pagination_are_bounded(self):
        now=[1.0];cache=Originals(clock=lambda:now[0],ttl=5,max_items=1)
        first=cache.put('first');second=cache.put('x'*50000)
        with self.assertRaises(ValueError):cache.get(first)
        self.assertEqual(cache.get(second)['next_offset'],48000)
        self.assertEqual(len(cache.get(second,48000)['content']),2000)
        now[0]=7
        with self.assertRaises(ValueError):cache.get(second)

    def test_unknown_write_knowledge_skills_prose_and_errors_stay_unchanged(self):
        for tool,result in [('write_file',self.fixture()),('knowledge_search',self.fixture()),('catalog_load',self.fixture()),('read_file',json.dumps({'success':False,'error':'failure','content':'x'*10000})),('read_file',json.dumps({'content':'prose '*3000}))]:
            self.assertIsNone(transform(tool,result,{'read_file','knowledge_search','catalog_load'},lambda text:'short',Originals()))

    def test_nonbeneficial_or_failed_compression_keeps_original(self):
        for compressor in (lambda text:text,lambda text:1,lambda text:(_ for _ in ()).throw(ValueError())):
            self.assertIsNone(transform('read_file',self.fixture(),{'read_file'},compressor,Originals()))

    def test_oversized_and_invalid_restore_requests_are_refused(self):
        cache=Originals(max_bytes=10)
        with self.assertRaises(ValueError):cache.put('x'*11)
        for reference,offset in [('unknown',0),('unknown',-1),(None,0)]:
            with self.assertRaises(ValueError):cache.get(reference,offset)
