"""Fixed OpenRouter free-only relay. Attested sanitized input; no payload logs."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import threading
import urllib.request
import urllib.error
from wire import decode

POLICY=json.loads(Path('/credentials/egress.json').read_text())
SEEN={};LOCK=threading.Lock()
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None
OPENER=urllib.request.build_opener(NoRedirect())
PROVIDER={'data_collection':'deny','zdr':True,'require_parameters':True,'allow_fallbacks':False,
          'max_price':{'prompt':0,'completion':0,'request':0,'image':0}}

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def reply(self,status,value):
        raw=json.dumps(value).encode();self.send_response(status);self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        self.reply(200,{'ready':True,'paid_enabled':False}) if self.path=='/health' else self.reply(404,{'error':'NOT_FOUND'})
    def do_POST(self):
        self.connection.settimeout(150);self.close_connection=True
        if self.path!='/attested-completion':self.reply(403,{'error':'ROUTE_DENIED'});return
        try:
            lengths=self.headers.get_all('Content-Length',[])
            if len(lengths)!=1 or not lengths[0].isdigit() or not 0<int(lengths[0])<=1024000 or self.headers.get('Transfer-Encoding'):raise ValueError('SIZE')
            with LOCK:body=decode(self.rfile.read(int(lengths[0])),self.headers.get('X-ArcIA-Attestation',''),bytes.fromhex(POLICY['attestation_key']),SEEN)
            if body.get('model')!='openrouter/free' or body.get('provider')!=PROVIDER or body.get('stream') is not False:raise ValueError('POLICY')
            if not 1<=body.get('max_tokens',0)<=2048:raise ValueError('TOKENS')
            req=urllib.request.Request('https://openrouter.ai/api/v1/chat/completions',
                data=json.dumps(body,ensure_ascii=False).encode(),headers={'Authorization':'Bearer '+POLICY['api_key'],
                    'Content-Type':'application/json','X-Title':'ArcIA qualification'})
            try:
                with OPENER.open(req,timeout=120) as response:
                    raw=response.read(2097153)
                    if len(raw)>2097152:raise ValueError('RESPONSE_LIMIT')
                    result=json.loads(raw)
                # Defensive cost check: price ceiling is enforced upstream before generation.
                if float(result.get('usage',{}).get('cost',0) or 0)>0:
                    self.reply(502,{'error':{'message':'UNEXPECTED_NONZERO_COST','type':'policy_error'}});return
                self.reply(200,result)
            except urllib.error.HTTPError as exc:
                # Never relay provider text: it can contain submitted context or credentials.
                self.reply(exc.code if exc.code in (400,401,402,403,404,408,429,503) else 502,
                    {'error':{'message':'NO_COMPLIANT_FREE_ROUTE' if exc.code in (404,403) else 'CLOUD_UPSTREAM_REJECTED',
                              'type':'upstream_error','upstream_status':exc.code}})
        except (ValueError,TypeError,KeyError):self.reply(403,{'error':{'message':'ATTESTATION_OR_POLICY_REJECTED','type':'policy_error'}})
        except Exception:self.reply(503,{'error':{'message':'CLOUD_UPSTREAM_UNAVAILABLE','type':'upstream_error'}})

if __name__=='__main__':ThreadingHTTPServer(('0.0.0.0',8092),Handler).serve_forever()
