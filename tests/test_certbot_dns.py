import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import certbot_dns_hook as hook


class AcmeBoundaryTests(unittest.TestCase):
    def test_foreign_domain_cannot_create_challenge(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'request.json').write_text(json.dumps({'domains':['owned.synthetic.test']}))
            (root/'challenges').mkdir()
            with patch.dict(os.environ,{'ARCIA_ACME_ROOT':directory,'CERTBOT_DOMAIN':'foreign.synthetic.test',
                                        'CERTBOT_VALIDATION':'A'*43},clear=True):
                with self.assertRaisesRegex(ValueError,'ACME_CHALLENGE_SCOPE'): hook.main()
            self.assertEqual(list((root/'challenges').iterdir()),[])

    def test_only_exact_txt_value_satisfies_validation(self):
        record={'name':'_acme-challenge.owned.synthetic.test','value':'A'*43}
        for response,expected in [({'Answer':[{'type':16,'data':'"'+('A'*43)+'"'}]},True),
                                   ({'Answer':[{'type':16,'data':'"different-value"'}]},False),
                                   ({'Answer':[{'type':5,'data':'"'+('A'*43)+'"'}]},False)]:
            with self.subTest(expected=expected,response=response):
                with patch.object(hook.urllib.request,'urlopen',side_effect=lambda *a,**k:io.BytesIO(json.dumps(response).encode())):
                    self.assertEqual(hook.published(record),expected)


if __name__=='__main__': unittest.main()
