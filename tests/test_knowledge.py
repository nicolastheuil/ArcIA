import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'services/knowledge'))
from core import extract,reciprocal_rank,validate_metadata

class KnowledgeBoundaryTests(unittest.TestCase):
    def test_api_keeps_operation_and_response_schema(self):
        api={'openapi':'3.1.0','info':{'version':'1'},'paths':{'/snapshots':{'post':{
            'operationId':'createSnapshot','responses':{'201':{'description':'Created'}}}}}}
        parts,assets=extract(json.dumps(api).encode(),'.json')
        self.assertEqual(parts[0].locator,'operation:POST:/snapshots:0')
        self.assertIn('createSnapshot',parts[0].text)
        self.assertIn('201',parts[0].text)

    def test_external_reference_is_never_fetched(self):
        with self.assertRaisesRegex(ValueError,'EXTERNAL_SCHEMA'):
            extract(b'{"nested":{"$ref":"https://example.invalid/schema"}}','.json')

    def test_editable_diagram_is_preserved_exactly(self):
        source=b'flowchart LR\n A[Source] --> B[Destination]\n'
        parts,assets=extract(source,'.mmd')
        self.assertEqual(assets['editable.mmd'],source)
        self.assertEqual(parts[0].kind,'diagram')

    def test_active_xml_and_entities_are_refused(self):
        for source in (b'<svg><script/></svg>',b'<svg onload="evil()"/>',
                b'<svg><image href="https://example.invalid/track"/></svg>',b'<!DOCTYPE svg><svg/>'):
            with self.subTest(source=source),self.assertRaises(ValueError):extract(source,'.svg')

    def test_unknown_formats_are_not_executed(self):
        with self.assertRaisesRegex(ValueError,'SOURCE_TYPE'):extract(b'echo malicious','.sh')

    def test_rank_fusion_deduplicates_within_branch(self):
        self.assertEqual(reciprocal_rank([[1,1,1,2],[2,1]]),[1,2])
        self.assertEqual(len(reciprocal_rank([list(range(100))],30)),30)

    def test_metadata_is_required_and_bounded(self):
        with self.assertRaisesRegex(ValueError,'METADATA'):validate_metadata({'title':'incomplete'})

if __name__=='__main__':unittest.main()
