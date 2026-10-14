"""ArcIA provider self-service on the private OmniRoute origin; OIDC PKCE."""
import base64
import hashlib
import hmac
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import threading
import time
from urllib.parse import parse_qs,urlencode,urlsplit
import uuid
import httpx
import jwt
from native import Native
from policy import AUTO_MODES,PERSONAL_ROLE
from store import Store

PREFIX='/personal/'
COOKIE='__Secure-arcia_routing_session'
PROVIDERS={'openai','anthropic','gemini','openrouter'}


def b64(value):return base64.urlsafe_b64encode(value).rstrip(b'=').decode()
def unb64(value):return base64.urlsafe_b64decode(value+'='*(-len(value)%4))
def owner_id(identity):return hashlib.sha256((identity['iss']+'\0'+identity['sub']).encode()).hexdigest()


class Identity:
    def __init__(self,config,key):
        self.config=config;self.key=key;self.client='arcia-routing';self.role_lookup=None
        self.issuer='https://'+config['hostname']+'/identity/realms/arcia'
        self.internal='http://keycloak.arcia-identity.svc.cluster.local:8080/identity/realms/arcia'
        self.headers={'Host':config['hostname'],'X-Forwarded-Proto':'https'}
        self.jwks=jwt.PyJWKClient(self.internal+'/protocol/openid-connect/certs',headers=self.headers)

    def token(self,value):
        response=httpx.post(self.internal+'/protocol/openid-connect/token',
            data={**value,'client_id':self.client},headers=self.headers,timeout=10,follow_redirects=False)
        if response.status_code!=200:raise PermissionError('LOGIN_REQUIRED')
        return response.json()

    def claims(self,token,id_token=False):
        signing=self.jwks.get_signing_key_from_jwt(token)
        claims=jwt.decode(token,signing.key,algorithms=['RS256'],issuer=self.issuer,audience=self.client,
            options={'require':['iss','sub','aud','iat','exp']},leeway=0)
        if not id_token and claims.get('azp')!=self.client:raise PermissionError('LOGIN_REQUIRED')
        return claims

    def authenticate(self,token):
        claims=self.claims(token)
        response=httpx.get(self.internal+'/protocol/openid-connect/userinfo',
            headers={**self.headers,'Authorization':'Bearer '+token},timeout=5,follow_redirects=False)
        if response.status_code!=200:raise PermissionError('LOGIN_REQUIRED')
        current=response.json()
        if current.get('sub')!=claims['sub'] or 'ArcIA.User' not in current.get('arcia_roles',[]):
            raise PermissionError('ARCIA_USER_REQUIRED')
        if self.config.get('online_role_authority'):
            if self.role_lookup is None:raise RuntimeError('IDENTITY_ROLE_AUTHORITY_UNAVAILABLE')
            return self.role_lookup(claims['sub'])
        # Roles are read online; stale access-token roles cannot retain BYOK.
        return {'iss':self.issuer,'sub':claims['sub'],'arcia_roles':current['arcia_roles']}

    def sign(self,value):
        body=b64(json.dumps(value,separators=(',',':')).encode())
        return body+'.'+b64(hmac.digest(self.key,body.encode(),'sha256'))

    def pending(self,value):
        body,mac=value.split('.')
        if not hmac.compare_digest(mac,b64(hmac.digest(self.key,body.encode(),'sha256'))):raise PermissionError('LOGIN_REQUIRED')
        data=json.loads(unb64(body))
        if not 0<=time.time()-data['created']<=300:raise PermissionError('LOGIN_REQUIRED')
        return data


class Control:
    def __init__(self,store,native,admin_users_url='/admin/users'):
        self.store=store;self.native=native;self.admin_users_url=admin_users_url;self.lock=threading.RLock()

    def authorize(self,identity,admin=False):
        if not identity.get('iss') or not identity.get('sub') or 'ArcIA.User' not in identity.get('arcia_roles',[]):
            raise PermissionError('ARCIA_USER_REQUIRED')
        if admin and 'ArcIA.Admin' not in identity['arcia_roles']:raise PermissionError('ADMIN_REQUIRED')
        return identity

    def personal(self,identity):
        self.authorize(identity)
        if PERSONAL_ROLE not in identity['arcia_roles'] or not self.store.settings()['personal_providers_enabled']:
            raise PermissionError('PERSONAL_PROVIDER_ROLE_REQUIRED')

    def reconcile(self):
        # Resolve uncertain creations by unique server-owned name; never replay
        # an external write after timeout/restart or adopt another owner's row.
        native=self.native.connections()
        for row in self.store.connections():
            matches=[c for c in native if c['name']==row['native_name'] and c['provider']==row['provider']]
            if len(matches)>1:raise RuntimeError('PERSONAL_CONNECTION_AMBIGUOUS')
            if matches and not row['native_id']:self.store.update(row['id'],matches[0]['id'],'ready')
            if not matches and row['phase']=='deleting':self.store.remove(row['id'])
        return native

    def state(self,identity):
        self.authorize(identity);settings=self.store.settings()
        permitted=PERSONAL_ROLE in identity['arcia_roles'] and settings['personal_providers_enabled']
        if permitted:
            with self.lock:self.reconcile()
        rows=self.store.connections(identity['iss'],identity['sub']) if permitted else []
        return {'personal_allowed':permitted,'admin':'ArcIA.Admin' in identity['arcia_roles'],
            'admin_users_url':self.admin_users_url if 'ArcIA.Admin' in identity['arcia_roles'] else None,
            'personal_enabled':permitted and self.store.preference(owner_id(identity)),
            'mode':settings['automatic_mode'],'providers':settings['personal_providers'] if permitted else [],
            'connections':[{k:r[k] for k in ('id','provider','label','phase')} for r in rows]}

    def create(self,identity,value):
        self.personal(identity)
        if not isinstance(value,dict) or set(value)!={'provider','label','api_key'}:raise ValueError('CONNECTION_FIELDS')
        provider=value['provider'];label=value['label'];key=value['api_key']
        if provider not in self.store.settings()['personal_providers']:raise PermissionError('PROVIDER_NOT_ALLOWED')
        if not isinstance(label,str) or not 1<=len(label)<=80 or any(ord(c)<32 for c in label):raise ValueError('LABEL_REQUIRED')
        if not isinstance(key,str) or not 1<=len(key)<=16384 or any(c in key for c in ('\r','\n','\x00')):raise ValueError('API_KEY_REQUIRED')
        with self.lock:
            if len(self.store.connections(identity['iss'],identity['sub']))>=10:raise PermissionError('PERSONAL_CONNECTION_LIMIT')
            identifier=str(uuid.uuid4())
            name='arcia-personal-'+owner_id(identity)[:16]+'-'+identifier
            self.store.reserve({'id':identifier,'issuer':identity['iss'],'subject':identity['sub'],
                'provider':provider,'label':label,'native_name':name})
            native_id=self.native.create(provider,name,key)
            self.store.update(identifier,native_id,'ready')
        return self.state(identity)

    def delete(self,identity,identifier):
        self.personal(identity)
        with self.lock:
            row=next((r for r in self.store.connections(identity['iss'],identity['sub']) if r['id']==identifier),None)
            if not row:raise PermissionError('PROVIDER_OWNER_REQUIRED')
            self.reconcile()
            row=next((r for r in self.store.connections(identity['iss'],identity['sub']) if r['id']==identifier),None)
            if not row:return self.state(identity)
            # Retain the ownership record if the native operation is uncertain.
            self.store.update(identifier,row['native_id'],'deleting')
            if row['native_id']:self.native.delete(row['native_id'])
            self.store.remove(identifier)
        return self.state(identity)

    def admin_state(self,identity):
        self.authorize(identity,True)
        with self.lock:
            native=self.reconcile();owned={r['native_id'] for r in self.store.connections()}
        return {'settings':self.store.settings(),'enterprise_candidates':[
            {k:c[k] for k in ('id','provider','name','isActive')} for c in native
            if c['id'] not in owned and not str(c['name']).startswith('arcia-personal-')]}

    def configure(self,identity,value):
        self.authorize(identity,True)
        required={'personal_providers_enabled','automatic_mode','enterprise_connections','allowed_models','personal_providers'}
        if not isinstance(value,dict) or set(value)!=required:raise ValueError('SETTINGS_FIELDS')
        if not isinstance(value['personal_providers_enabled'],bool) or value['automatic_mode'] not in AUTO_MODES:raise ValueError('ADMIN_AUTO_MODE_REQUIRED')
        for field,limit in [('enterprise_connections',100),('allowed_models',1000),('personal_providers',4)]:
            if not isinstance(value[field],list) or len(value[field])>limit or len(set(value[field]))!=len(value[field]):raise ValueError('SETTINGS_LIST_REQUIRED')
        if not set(value['personal_providers'])<=PROVIDERS:raise ValueError('PROVIDER_NOT_ALLOWED')
        if any(not isinstance(m,str) or not re.fullmatch(r'[a-zA-Z0-9_./:@+-]{1,200}',m) for m in value['allowed_models']):raise ValueError('MODEL_REQUIRED')
        with self.lock:
            candidates={c['id'] for c in self.admin_state(identity)['enterprise_candidates']}
            if not set(value['enterprise_connections'])<=candidates:raise PermissionError('ENTERPRISE_CONNECTION_SCOPE_REQUIRED')
            self.store.save_settings(value)
        return self.admin_state(identity)

    def preference(self,identity,value):
        self.personal(identity)
        if not isinstance(value,dict) or set(value)!={'enabled'} or not isinstance(value['enabled'],bool):raise ValueError('PREFERENCE_FIELDS')
        self.store.preference(owner_id(identity),value['enabled'])
        return self.state(identity)

    def profile(self,identity):
        """Called only after online server verification, never by a browser/model."""
        self.authorize(identity);self.native.private();settings=self.store.settings();owner=owner_id(identity)
        personal=(PERSONAL_ROLE in identity['arcia_roles'] and settings['personal_providers_enabled']
            and self.store.preference(owner))
        with self.lock:
            native=self.reconcile();active={c['id'] for c in native if c.get('isActive') is True}
            owned={r['native_id'] for r in self.store.connections()}
            ids=([r['native_id'] for r in self.store.connections(identity['iss'],identity['sub'])
                if r['phase']=='ready' and r['provider'] in settings['personal_providers']] if personal
                else [c for c in settings['enterprise_connections'] if c not in owned])
            ids=sorted(set(ids)&active)
            if not ids or not settings['allowed_models']:raise PermissionError('ADMIN_ROUTING_CONFIGURATION_REQUIRED')
            models=sorted(set([settings['automatic_mode'],*settings['allowed_models']]))
            fingerprint=hashlib.sha256(json.dumps({'connections':ids,'models':models},sort_keys=True).encode()).hexdigest()
            credential=self.store.credential(owner)
            if credential and credential.get('phase')=='pending':
                matches=[k for k in self.native.keys() if k['name']==credential['native_name']]
                if len(matches)>1:raise RuntimeError('ROUTING_KEY_RECONCILIATION_REQUIRED')
                for row in matches:self.native.revoke_key(row['id'])
                self.store.forget_credential(owner)
                # Reconcile, then require a new request; never replay the write.
                raise RuntimeError('ROUTING_KEY_RECOVERED_RETRY_REQUIRED')
            if not credential or credential.get('fingerprint')!=fingerprint:
                if credential:self.native.revoke_key(credential['id']);self.store.forget_credential(owner)
                name='arcia-route-'+owner[:16]+'-'+str(uuid.uuid4())
                self.store.credential(owner,{'id':None,'phase':'pending','native_name':name})
                credential=self.native.scoped_key(name,ids,models)
                credential.update(fingerprint=fingerprint,phase='ready')
                self.store.credential(owner,credential)
        return {'model':settings['automatic_mode'],'api_key':credential['key'],'route_class':'cloud',
            'connections':ids,'personal':personal}


class Handler(BaseHTTPRequestHandler):
    server_version='ArcIA';sys_version=''
    def log_message(self,*args):pass
    def respond(self,status,value=None,headers=(),body=None):
        if body is None:body=json.dumps(value or {}).encode();headers=[('Content-Type','application/json'),*headers]
        self.send_response(status)
        for name,value in headers:self.send_header(name,value)
        self.send_header('Cache-Control','no-store');self.send_header('Referrer-Policy','no-referrer')
        self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Length',str(len(body)))
        self.end_headers();self.wfile.write(body)
    def cookie(self,name,value,age=28800):
        cookie=SimpleCookie();cookie[name]=value
        for key,setting in [('path',PREFIX),('secure',True),('httponly',True),('samesite','Lax'),('max-age',age)]:cookie[name][key]=setting
        return ('Set-Cookie',cookie[name].OutputString())
    def redirect(self,path,headers=()):return self.respond(303,headers=[('Location',path),*headers])
    def do_GET(self):self.handle_request('GET')
    def do_POST(self):self.handle_request('POST')
    def handle_request(self,method):
        self.connection.settimeout(15);self.close_connection=True
        app=self.server.app;identity=app['identity'];store=app['store'];control=app['control']
        url=urlsplit(self.path);path=url.path
        if path==PREFIX+'health' and method=='GET':return self.respond(200,{'ready':True})
        origin='https://'+self.headers.get('Host','')
        if origin not in app['origins']:return self.respond(403,{'code':'HOST_REFUSED'})
        cookies=SimpleCookie();cookies.load(self.headers.get('Cookie',''))
        try:
            if path==PREFIX+'login' and method=='GET':
                pending={'verifier':secrets.token_urlsafe(48),'state':secrets.token_urlsafe(32),'nonce':secrets.token_urlsafe(32),
                    'created':time.time(),'origin':origin}
                query=urlencode({'client_id':identity.client,'response_type':'code','scope':'openid profile',
                    'redirect_uri':origin+PREFIX+'callback','state':pending['state'],'nonce':pending['nonce'],
                    'code_challenge':b64(hashlib.sha256(pending['verifier'].encode()).digest()),'code_challenge_method':'S256'})
                return self.redirect(identity.issuer+'/protocol/openid-connect/auth?'+query,
                    [self.cookie('__Secure-arcia_routing_pkce',identity.sign(pending),300)])
            if path==PREFIX+'callback' and method=='GET':
                pending=identity.pending(cookies['__Secure-arcia_routing_pkce'].value);query=parse_qs(url.query)
                if pending['origin']!=origin or not hmac.compare_digest(pending['state'],query.get('state',[''])[0]):raise PermissionError('LOGIN_REQUIRED')
                payload=identity.token({'grant_type':'authorization_code','code':query['code'][0],
                    'redirect_uri':origin+PREFIX+'callback','code_verifier':pending['verifier']})
                claims=identity.authenticate(payload['access_token']);id_claims=identity.claims(payload['id_token'],True)
                if id_claims.get('nonce')!=pending['nonce'] or id_claims['sub']!=claims['sub']:raise PermissionError('LOGIN_REQUIRED')
                session=secrets.token_urlsafe(48);store.session(session,{**payload,'created':time.time(),'csrf':secrets.token_urlsafe(32)})
                return self.redirect(PREFIX,[self.cookie(COOKIE,session),self.cookie('__Secure-arcia_routing_pkce','',0)])
            session=cookies[COOKIE].value
            with app['session_lock']:
                payload=store.session(session)
                try:claims=identity.authenticate(payload['access_token'])
                except jwt.ExpiredSignatureError:
                    refreshed=identity.token({'grant_type':'refresh_token','refresh_token':payload['refresh_token']})
                    payload.update(refreshed);claims=identity.authenticate(payload['access_token'])
                store.session(session,payload)
            if method=='POST':
                if self.headers.get('Origin')!=origin or not hmac.compare_digest(self.headers.get('X-ArcIA-CSRF',''),payload['csrf']):
                    return self.respond(403,{'code':'CSRF_REFUSED'})
                lengths=self.headers.get_all('Content-Length',[])
                if len(lengths)!=1 or not lengths[0].isdigit() or self.headers.get('Transfer-Encoding') or self.headers.get_content_type()!='application/json':raise ValueError('BOUNDED_JSON_REQUIRED')
                length=int(lengths[0])
                if not 0<length<=32768:raise ValueError('BOUNDED_JSON_REQUIRED')
                value=json.loads(self.rfile.read(length))
                if path==PREFIX+'api/connections':result=control.create(claims,value)
                elif path==PREFIX+'api/delete':
                    if set(value)!={'id'}:raise ValueError('CONNECTION_FIELDS')
                    result=control.delete(claims,str(uuid.UUID(value['id'])))
                elif path==PREFIX+'api/admin':result=control.configure(claims,value)
                elif path==PREFIX+'api/preference':result=control.preference(claims,value)
                elif path==PREFIX+'api/logout':
                    if value!={}:raise ValueError('EMPTY_REQUEST_REQUIRED')
                    store.logout(session);return self.respond(200,{},[self.cookie(COOKIE,'',0)])
                else:return self.respond(404,{'code':'NOT_FOUND'})
                return self.respond(200,result)
            if path==PREFIX+'api/state':return self.respond(200,{**control.state(claims),'csrf':payload['csrf']})
            if path==PREFIX+'api/admin':return self.respond(200,control.admin_state(claims))
            if path!=PREFIX:return self.respond(404,{'code':'NOT_FOUND'})
            nonce=secrets.token_urlsafe(24)
            html=Path(__file__).with_name('personal.html').read_text(encoding='utf-8').replace('__NONCE__',nonce)
            return self.respond(200,headers=[('Content-Type','text/html; charset=utf-8'),
                ('Content-Security-Policy',"default-src 'none'; style-src 'unsafe-inline'; script-src 'nonce-"+nonce+"'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")],body=html.encode())
        except (httpx.RequestError,jwt.PyJWKClientConnectionError):return self.respond(503,{'code':'IDENTITY_UNAVAILABLE'})
        except PermissionError as exc:
            codes={'ARCIA_USER_REQUIRED','PERSONAL_PROVIDER_ROLE_REQUIRED','PROVIDER_OWNER_REQUIRED','ADMIN_REQUIRED','PROVIDER_NOT_ALLOWED','PERSONAL_CONNECTION_LIMIT','PRIVATE_AUTHENTICATED_ROUTER_REQUIRED','ENTERPRISE_CONNECTION_SCOPE_REQUIRED'}
            code=str(exc) if str(exc) in codes else 'LOGIN_REQUIRED'
            if code=='LOGIN_REQUIRED' and path==PREFIX and method=='GET':return self.redirect(PREFIX+'login')
            return self.respond(403 if code!='LOGIN_REQUIRED' else 401,{'code':code})
        except (ValueError,TypeError):return self.respond(400,{'code':'REQUEST_REFUSED'})
        except (KeyError,jwt.InvalidTokenError):
            if path==PREFIX and method=='GET':return self.redirect(PREFIX+'login')
            return self.respond(401,{'code':'LOGIN_REQUIRED'})
        except Exception:return self.respond(503,{'code':'ROUTING_CONTROL_UNAVAILABLE'})


def main():
    config=json.loads(Path('/personal-code/config.json').read_text())
    key=os.environ['STORAGE_ENCRYPTION_KEY'].encode()
    store=Store('/data/arcia-self-service/state.db',key)
    identity=Identity(config,key)
    control=Control(store,Native(os.environ['JWT_SECRET']),'https://'+config['hostname']+'/admin/users')
    from gateway import start
    gateway=start(control,config)
    if gateway is not None:identity.role_lookup=gateway.gateway.identity.live_roles
    server=ThreadingHTTPServer(('0.0.0.0',20130),Handler)
    server.app={'identity':identity,'store':store,'control':control,
        'origins':config['origins'],'session_lock':threading.RLock()}
    server.serve_forever()


if __name__=='__main__':main()
