"""Owner-bound inference. Route policy first, Presidio before every cloud call."""
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import ssl
import threading
import time
import urllib.request
import urllib.error
from urllib.parse import quote,urlencode


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


OPENER=urllib.request.build_opener(NoRedirect())


def http_json(url,method='GET',value=None,headers=None,timeout=15,form=False,context=None):
    raw=(urlencode(value).encode() if form else json.dumps(value).encode()) if value is not None else None
    req=urllib.request.Request(url,method=method,data=raw,headers=headers or {})
    if context is not None:
        opener=urllib.request.build_opener(NoRedirect(),urllib.request.HTTPSHandler(context=context))
    else:opener=OPENER
    try:
        with opener.open(req,timeout=timeout) as response:
            raw=response.read(2097153)
            if len(raw)>2097152:raise RuntimeError('RESPONSE_LIMIT')
            return json.loads(raw)
    except Exception:raise RuntimeError('ROUTING_DEPENDENCY_UNAVAILABLE') from None


class RuntimeIdentity:
    def __init__(self,config,credentials,clients,kube_root='/routing-account'):
        self.config=config;self.credentials=credentials;self.clients=clients;self.root=Path(kube_root)
        self.internal='http://keycloak.arcia-identity.svc.cluster.local:8080/identity'
        self.issuer='https://'+config['hostname']+'/identity/realms/arcia'
        self.headers={'Host':config['hostname'],'X-Forwarded-Proto':'https'}

    def authenticate(self,token):
        scope=next((v for k,v in self.clients['tokens'].items() if hmac.compare_digest(k,token)),None)
        if not scope:raise PermissionError('RUNTIME_TOKEN_REQUIRED')
        if scope.startswith('personal-p'):
            suffix=scope.removeprefix('personal-');namespace=self.config['slots'].get(suffix)
            if not namespace:raise PermissionError('RUNTIME_BINDING_REQUIRED')
            path='/api/v1/namespaces/'+namespace+'/configmaps/slot-binding'
            binding=http_json('https://kubernetes.default.svc'+path,headers={
                'Authorization':'Bearer '+(self.root/'token').read_text()},
                context=ssl.create_default_context(cafile=str(self.root/'ca.crt')))
            if binding['metadata'].get('annotations',{}).get('arcia.io/operation-id')!=self.config['operation_id']:
                raise PermissionError('RUNTIME_BINDING_REQUIRED')
            owner=json.loads(binding['data']['binding.json'])
        else:owner=self.clients['legacy_bindings'].get(scope,{})
        if owner.get('issuer')!=self.issuer or not owner.get('subject'):raise PermissionError('RUNTIME_BINDING_REQUIRED')
        return self.live_roles(owner['subject'])

    def live_roles(self,subject):
        access=http_json(self.internal+'/realms/arcia/protocol/openid-connect/token','POST',
            {'grant_type':'client_credentials','client_id':'arcia-routing-checker',
             'client_secret':self.credentials['client_secret']},
            headers={**self.headers,'Content-Type':'application/x-www-form-urlencoded'},form=True)
        headers={**self.headers,'Authorization':'Bearer '+access['access_token']}
        user_path=self.internal+'/admin/realms/arcia/users/'+quote(subject,safe='')
        user=http_json(user_path,headers=headers)
        if user.get('id')!=subject or user.get('enabled') is not True:raise PermissionError('RUNTIME_USER_INACTIVE')
        roles=http_json(user_path+'/role-mappings/realm/composite',headers=headers)
        return {'iss':self.issuer,'sub':subject,'arcia_roles':[r['name'] for r in roles]}


class Gateway:
    def __init__(self,control,identity):self.control=control;self.identity=identity

    def complete(self,token,value):
        identity=self.identity.authenticate(token)
        profile=self.control.profile(identity)
        # An agent cannot switch model, endpoint, credential or connection pool.
        if not isinstance(value,dict) or value.get('model') not in ('auto','auto/smart',profile['model']):
            raise PermissionError('ADMIN_AUTO_MODE_REQUIRED')
        if profile['route_class']!='cloud':raise PermissionError('QUALIFIED_CLOUD_ROUTE_REQUIRED')
        payload={**value,'model':profile['model']}
        sanitized=http_json('http://privacy.arcia-privacy.svc.cluster.local:8091/v1/sanitize-completion','POST',payload,
            headers={'Content-Type':'application/json','Authorization':'Bearer '+token},timeout=30)
        body=sanitized['body']
        if body.get('model')!=profile['model']:raise PermissionError('SANITIZED_ROUTE_REQUIRED')
        body={**body,'stream':False};body.pop('stream_options',None)
        return http_json('http://127.0.0.1:20128/v1/chat/completions','POST',body,
            headers={'Content-Type':'application/json','Authorization':'Bearer '+profile['api_key']},timeout=120)


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def reply(self,status,value):
        body=json.dumps(value).encode();self.send_response(status);self.send_header('Content-Type','application/json')
        self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(body)))
        self.end_headers();self.wfile.write(body)
    def do_GET(self):
        if self.path=='/health':return self.reply(200,{'ready':True})
        headers=self.headers.get_all('Authorization',[])
        token=headers[0][7:] if len(headers)==1 and headers[0].startswith('Bearer ') else ''
        try:
            identity=self.server.gateway.identity.authenticate(token)
            self.server.gateway.control.authorize(identity)
            if self.path!='/v1/models':return self.reply(404,{'error':'NOT_FOUND'})
            mode=self.server.gateway.control.store.settings()['automatic_mode']
            self.reply(200,{'object':'list','data':[{'id':mode,'object':'model','owned_by':'arcia-admin'}]})
        except PermissionError:self.reply(403,{'error':'RUNTIME_ACCESS_REFUSED'})
        except Exception:self.reply(503,{'error':'ROUTING_UNAVAILABLE'})
    def do_POST(self):
        self.connection.settimeout(15);self.close_connection=True
        if self.path!='/v1/chat/completions':return self.reply(403,{'error':'ENDPOINT_REFUSED'})
        headers=self.headers.get_all('Authorization',[])
        token=headers[0][7:] if len(headers)==1 and headers[0].startswith('Bearer ') else ''
        try:
            lengths=self.headers.get_all('Content-Length',[])
            if (len(lengths)!=1 or not lengths[0].isdigit() or self.headers.get('Transfer-Encoding')
                or self.headers.get_content_type()!='application/json'):raise ValueError()
            length=int(lengths[0])
            if not 0<length<=512000:raise ValueError()
            value=json.loads(self.rfile.read(length))
            result=self.server.gateway.complete(token,value)
            if value.get('stream') is True:
                self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Cache-Control','no-store')
                self.send_header('Connection','close');self.end_headers()
                common={k:result[k] for k in ('id','created','model') if k in result};common['object']='chat.completion.chunk'
                def event(value):self.wfile.write(('data: '+json.dumps(value)+'\n\n').encode())
                for choice in result['choices']:
                    delta=dict(choice['message'])
                    if 'tool_calls' in delta:delta['tool_calls']=[dict(call,index=i) for i,call in enumerate(delta['tool_calls'])]
                    event({**common,'choices':[{'index':choice.get('index',0),'delta':delta,'finish_reason':None}]})
                    event({**common,'choices':[{'index':choice.get('index',0),'delta':{},'finish_reason':choice.get('finish_reason','stop')}]})
                event({**common,'choices':[],'usage':result.get('usage',{})});self.wfile.write(b'data: [DONE]\n\n')
            else:self.reply(200,result)
        except PermissionError:self.reply(403,{'error':'ROUTING_POLICY_REFUSED'})
        except (ValueError,TypeError,KeyError):self.reply(422,{'error':'PAYLOAD_REFUSED'})
        except Exception:self.reply(503,{'error':'ROUTING_UNAVAILABLE'})


def start(control,config):
    credentials=Path('/routing-identity/checker.json');clients=Path('/routing-clients/clients.json')
    if not credentials.is_file() or not clients.is_file():return None
    identity=RuntimeIdentity(config,json.loads(credentials.read_text()),json.loads(clients.read_text()))
    server=ThreadingHTTPServer(('0.0.0.0',20131),Handler);server.gateway=Gateway(control,identity)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    return server
