"""Private Presidio boundary; text-only OpenAI API and attested free cloud route."""
import hmac
from http.server import BaseHTTPRequestHandler,HTTPServer
import json
import os
from pathlib import Path
import re
import urllib.request
import urllib.error
from wire import encode

os.environ.update(SPACY_WARNING_IGNORE='W008',TOKENIZERS_PARALLELISM='false')
from presidio_analyzer import AnalyzerEngine
from presidio_analyzer.nlp_engine import SpacyNlpEngine
from presidio_analyzer.predefined_recognizers import SpacyRecognizer
from presidio_anonymizer import AnonymizerEngine
from core import Sanitizer,Blocked

NLP=SpacyNlpEngine(models=[{'lang_code':'en','model_name':'en_core_web_sm'},{'lang_code':'fr','model_name':'fr_core_news_sm'}])
NLP.load()
ANALYZER=AnalyzerEngine(nlp_engine=NLP,supported_languages=['en','fr'],log_decision_process=False)
for language in ('en','fr'):
    ANALYZER.registry.add_recognizer(SpacyRecognizer(supported_language=language,supported_entities=['PERSON','LOCATION','ORGANIZATION']))
ANONYMIZER=AnonymizerEngine()
POLICY=json.loads(Path('/credentials/policy.json').read_text())
if not isinstance(POLICY.get('tokens'),dict):raise RuntimeError('PRIVACY_TOKEN_POLICY_REQUIRED')
PROVIDER={'data_collection':'deny','zdr':True,'require_parameters':True,'allow_fallbacks':False,
          'max_price':{'prompt':0,'completion':0,'request':0,'image':0}}

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def reply(self,status,value):
        data=json.dumps(value,ensure_ascii=False).encode()
        self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(data)
    def do_GET(self):
        if self.path=='/health':self.reply(200,{'ready':True,'cloud_enabled':POLICY.get('cloud_enabled') is True,'legacy_paid_enabled':False,'price_policy_owner':'instance','languages':['fr','en']})
        elif self.path=='/v1/models':self.reply(200,{'object':'list','data':[{'id':'openrouter/free','object':'model','owned_by':'arcia-policy'}]})
        else:self.reply(404,{'error':'NOT_FOUND'})
    def do_POST(self):
        self.connection.settimeout(15)
        if self.path not in ('/v1/sanitize','/v1/sanitize-completion','/v1/chat/completions'):self.reply(403,{'error':'UNAPPROVED_ENDPOINT'});self.close_connection=True;return
        headers=self.headers.get_all('Authorization',[])
        token=headers[0].removeprefix('Bearer ') if len(headers)==1 and headers[0].startswith('Bearer ') else ''
        identity=next((v for k,v in POLICY['tokens'].items() if hmac.compare_digest(token,k)),None)
        if not identity:self.reply(401,{'error':'UNAUTHORIZED'});self.close_connection=True;return
        try:
            lengths=self.headers.get_all('Content-Length',[])
            if len(lengths)!=1 or self.headers.get('Transfer-Encoding') or not lengths[0].isdigit():raise Blocked('BOUNDED_JSON_REQUIRED')
            length=int(lengths[0])
            if not 0<length<=512000:raise Blocked('BOUNDED_JSON_REQUIRED')
            if self.headers.get_content_type()!='application/json':raise Blocked('JSON_REQUIRED')
            value=json.loads(self.rfile.read(length))
            sanitizer=Sanitizer(ANALYZER,bytes.fromhex(POLICY['hmac_key']),identity['scope'],identity.get('identifiers',[]))
            if self.path=='/v1/sanitize':self.reply(200,sanitizer.payload(value))
            elif self.path=='/v1/sanitize-completion':
                if POLICY.get('cloud_enabled') is not True:raise Blocked('CLOUD_POLICY_DISABLED')
                if identity.get('classification') not in ('synthetic','public'):raise Blocked('CLASSIFICATION_NOT_CLOUD_APPROVED')
                body,counts=sanitizer.completion(value)
                self.reply(200,{'body':body,'detections':counts,'cloud_authorized':False})
            else:
                if POLICY.get('cloud_enabled') is not True or POLICY.get('paid_enabled') is not False:raise Blocked('LEGACY_FREE_ONLY_POLICY_REQUIRED')
                if identity.get('classification') not in ('synthetic','public'):raise Blocked('CLASSIFICATION_NOT_CLOUD_APPROVED')
                if value.get('model')!='openrouter/free':raise Blocked('MODEL_NOT_APPROVED')
                body,counts=sanitizer.completion(value)
                streaming=body.get('stream',False)
                body.pop('stream_options',None);body.pop('max_completion_tokens',None)
                body.update(model='openrouter/free',provider=PROVIDER,stream=False,
                    max_tokens=min(2048,max(1,int(value.get('max_tokens',value.get('max_completion_tokens',1024))))))
                raw,signature=encode(body,bytes.fromhex(POLICY['attestation_key']))
                request=urllib.request.Request('http://cloud-egress.arcia-privacy.svc.cluster.local:8092/attested-completion',
                    data=raw,headers={'Content-Type':'application/json','X-ArcIA-Attestation':signature})
                try:
                    with urllib.request.urlopen(request,timeout=135) as response:
                        data=response.read(2097153)
                        if len(data)>2097152:raise Blocked('RESPONSE_TOO_LARGE')
                        result=json.loads(data)
                except urllib.error.HTTPError as exc:
                    self.reply(exc.code,json.loads(exc.read(4096)));return
                if streaming:
                    self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Cache-Control','no-store')
                    self.send_header('Connection','close');self.end_headers()
                    def event(chunk):self.wfile.write(('data: '+json.dumps(chunk,ensure_ascii=False)+'\n\n').encode())
                    common={k:result[k] for k in ('id','created','model') if k in result};common['object']='chat.completion.chunk'
                    for choice in result['choices']:
                        delta=dict(choice['message'])
                        if 'tool_calls' in delta:delta['tool_calls']=[dict(call,index=i) for i,call in enumerate(delta['tool_calls'])]
                        event({**common,'choices':[{'index':choice.get('index',0),'delta':delta,'finish_reason':None}]})
                        event({**common,'choices':[{'index':choice.get('index',0),'delta':{},'finish_reason':choice.get('finish_reason','stop')}]})
                    event({**common,'choices':[],'usage':result.get('usage',{})});self.wfile.write(b'data: [DONE]\n\n');self.wfile.flush()
                else:self.reply(200,result)
        except (Blocked,ValueError,TypeError,KeyError,UnicodeError):self.reply(422,{'error':'PAYLOAD_BLOCKED'})
        except Exception:self.reply(503,{'error':'SANITIZER_UNAVAILABLE'})
        self.close_connection=True

if __name__=='__main__':HTTPServer(('0.0.0.0',8091),Handler).serve_forever()
