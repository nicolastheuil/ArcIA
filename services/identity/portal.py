"""Public PKCE login plus a fixed personal runtime allocator. No admin IdP secret."""
import base64
import hashlib
import hmac
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import secrets
import time
from pathlib import Path
from urllib.parse import urlencode,urlsplit,parse_qs
import urllib.request
import urllib.error
import ssl
import httpx
import jwt
from slots import Slots,CapacityError,BindingError

CONFIG=json.loads(Path('/config/portal.json').read_text()) if Path('/config/portal.json').is_file() else {}


def b64(value):return base64.urlsafe_b64encode(value).rstrip(b'=').decode()
def unb64(value):return base64.urlsafe_b64decode(value+'='*(-len(value)%4))


class Portal:
    def __init__(self,config,key,api):
        self.config=config;self.key=key;self.origin='https://'+config['hostname']
        self.issuer=self.origin+'/identity/realms/arcia';self.internal=config['identity_internal']
        self.client='arcia-portal';self.callback=self.origin+'/portal/callback'
        self.headers={'Host':config['hostname'],'X-Forwarded-Proto':'https'}
        self.jwks=jwt.PyJWKClient(self.internal+'/protocol/openid-connect/certs',headers=self.headers)
        self.slots=Slots(api,config['slots'],self.issuer,config['operation_id'])

    def sign(self,value):
        body=b64(json.dumps(value,sort_keys=True,separators=(',',':')).encode())
        return body+'.'+b64(hmac.digest(self.key,body.encode(),'sha256'))

    def verify_state(self,value):
        body,mac=value.split('.')
        if not hmac.compare_digest(b64(hmac.digest(self.key,body.encode(),'sha256')),mac):raise ValueError('STATE_REFUSED')
        data=json.loads(unb64(body))
        if not 0<=time.time()-data['created']<=300:raise ValueError('STATE_EXPIRED')
        return data

    def token(self,data):
        response=httpx.post(self.internal+'/protocol/openid-connect/token',data={**data,'client_id':self.client},
            headers=self.headers,timeout=10,follow_redirects=False)
        if response.status_code!=200:raise ValueError('LOGIN_REFUSED')
        return response.json()

    def claims(self,token):
        signing=self.jwks.get_signing_key_from_jwt(token)
        return jwt.decode(token,signing.key,algorithms=['RS256'],issuer=self.issuer,audience=self.client,
            options={'require':['iss','aud','sub','exp','iat']},leeway=0)

    def authenticate(self,token):
        claims=self.claims(token)
        if claims.get('azp')!=self.client:raise ValueError('CLIENT_REFUSED')
        response=httpx.get(self.internal+'/protocol/openid-connect/userinfo',headers={**self.headers,'Authorization':'Bearer '+token},
            timeout=5,follow_redirects=False)
        if response.status_code!=200 or response.json().get('sub')!=claims['sub']:raise ValueError('SESSION_INACTIVE')
        if 'ArcIA.User' not in claims.get('arcia_roles',[]):raise PermissionError('ARCIA_USER_ROLE_REQUIRED')
        return claims

    def csrf(self,subject):return b64(hmac.digest(self.key,(self.issuer+'\0'+subject).encode(),'sha256'))


class Handler(BaseHTTPRequestHandler):
    server_version='ArcIA';sys_version=''
    def log_message(self,*args):pass
    def cookie(self,name,value,age=28800):
        cookie=SimpleCookie();cookie[name]=value;cookie[name]['path']='/portal/'
        cookie[name]['secure']=True;cookie[name]['httponly']=True;cookie[name]['samesite']='Lax';cookie[name]['max-age']=age
        return ('Set-Cookie',cookie[name].OutputString())
    def respond(self,status,body=b'',headers=()):
        self.send_response(status)
        for key,value in headers:self.send_header(key,value)
        self.send_header('Cache-Control','no-store');self.send_header('Referrer-Policy','no-referrer')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def redirect(self,path,cookies=()):return self.respond(303,headers=[('Location',path),*cookies])
    def json(self,status,value,cookies=()):
        self.respond(status,json.dumps(value).encode(),[('Content-Type','application/json'),*cookies])
    def session(self,cookies):
        changes=[]
        token=cookies.get('__Secure-arcia_portal_at')
        token=token.value if token else ''
        try:claims=self.server.portal.authenticate(token)
        except jwt.ExpiredSignatureError:
            refresh=cookies.get('__Secure-arcia_portal_rt')
            if not refresh:raise ValueError('SESSION_EXPIRED')
            payload=self.server.portal.token({'grant_type':'refresh_token','refresh_token':refresh.value})
            token=payload['access_token'];claims=self.server.portal.authenticate(token)
            changes=[self.cookie('__Secure-arcia_portal_at',token),self.cookie('__Secure-arcia_portal_rt',payload['refresh_token'])]
        return claims,changes
    def do_GET(self):self.handle_request('GET')
    def do_POST(self):self.handle_request('POST')
    def handle_request(self,method):
        portal=self.server.portal;url=urlsplit(self.path);path=url.path
        phase='REQUEST';changes=[]
        if path=='/portal/health' and method=='GET':return self.json(200,{'status':'ready'})
        if self.headers.get('Host')!=portal.config['hostname']:return self.json(403,{'code':'HOST_REFUSED'})
        cookies=SimpleCookie()
        try:
            cookies.load(self.headers.get('Cookie',''))
            if path=='/portal/login' and method=='GET':
                verifier=secrets.token_urlsafe(48);state=secrets.token_urlsafe(32);nonce=secrets.token_urlsafe(32)
                pending=portal.sign({'verifier':verifier,'state':state,'nonce':nonce,'created':time.time()})
                query=urlencode({'client_id':portal.client,'response_type':'code','scope':'openid profile',
                    'redirect_uri':portal.callback,'state':state,'nonce':nonce,
                    'code_challenge':b64(hashlib.sha256(verifier.encode()).digest()),'code_challenge_method':'S256'})
                if parse_qs(url.query).get('reauth')==['1']:query+='&prompt=login'
                return self.redirect(portal.issuer+'/protocol/openid-connect/auth?'+query,
                    [self.cookie('__Secure-arcia_portal_pkce',pending,300)])
            if path=='/portal/callback' and method=='GET':
                pending=portal.verify_state(cookies['__Secure-arcia_portal_pkce'].value)
                query=parse_qs(url.query)
                if not hmac.compare_digest(pending['state'],query.get('state',[''])[0]):raise ValueError('STATE_REFUSED')
                payload=portal.token({'grant_type':'authorization_code','code':query['code'][0],
                    'redirect_uri':portal.callback,'code_verifier':pending['verifier']})
                identity=portal.claims(payload['id_token']);claims=portal.authenticate(payload['access_token'])
                if identity.get('nonce')!=pending['nonce'] or identity['sub']!=claims['sub']:raise ValueError('NONCE_REFUSED')
                return self.redirect('/portal/',[self.cookie('__Secure-arcia_portal_at',payload['access_token']),
                    self.cookie('__Secure-arcia_portal_rt',payload['refresh_token']),self.cookie('__Secure-arcia_portal_pkce','',0)])
            if path not in ('/portal/','/portal/provision'):return self.json(404,{'code':'NOT_FOUND'})
            phase='SESSION';claims,changes=self.session(cookies)
            if path=='/portal/provision':
                if method!='POST' or self.headers.get('Origin')!=portal.origin or not hmac.compare_digest(
                    self.headers.get('X-ArcIA-CSRF',''),portal.csrf(claims['sub'])):
                    return self.json(403,{'code':'CSRF_REFUSED'})
                if int(self.headers.get('Content-Length','0'))!=0:return self.json(400,{'code':'EMPTY_REQUEST_REQUIRED'})
                phase='PROVISION';result=portal.slots.progress(claims['sub'])
                if result['phase']=='starting':
                    try:
                        response=httpx.get('http://hermes-pilot.'+result['namespace']+'.svc.cluster.local:9119/api/health',timeout=2)
                        if response.status_code==200:result['phase']='ready'
                    except httpx.RequestError:pass
                return self.json(200,{k:v for k,v in result.items() if k!='namespace'},changes)
            if method!='GET':return self.json(405,{'code':'METHOD_REFUSED'})
            nonce=secrets.token_urlsafe(24)
            html='''<!doctype html><html lang="fr"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>ArcIA — espace personnel</title>
<style>body{font:17px system-ui;max-width:680px;margin:12vh auto;padding:24px;color:#15354a;background:#f6f9fb}main{background:white;border-radius:16px;padding:32px;border:1px solid #dce6ed}h1{font-size:28px}a{color:#155c92}</style>
<main><h1>Votre espace ArcIA</h1><p id="status">Préparation de votre espace personnel…</p><p>Vos conversations et fichiers restent propres à votre compte.</p><p><a href="/account">Mon compte</a> · <a href="/admin/users">Administration des utilisateurs</a></p></main>
<script nonce="'''+nonce+'''">const csrf='''+json.dumps(portal.csrf(claims['sub']))+''';let busy=false;
async function poll(){if(busy)return;busy=true;try{const r=await fetch('/portal/provision',{method:'POST',headers:{'X-ArcIA-CSRF':csrf}});const x=await r.json();
if(x.phase==='ready'){location.replace(x.prefix+'/');return;}const msg={installing:'Installation des outils de votre espace. Cette première préparation peut prendre plusieurs minutes.',starting:'Démarrage de votre espace personnel…',blocked:'La préparation est interrompue. Contactez votre administrateur.'};
document.getElementById('status').textContent=msg[x.phase]||x.message||'Connexion expirée ou capacité atteinte. Reconnectez-vous ou contactez votre administrateur.';
if(r.ok&&x.phase!=='blocked')setTimeout(poll,4000);}catch(e){document.getElementById('status').textContent='Service momentanément indisponible. Réessayez cette page.';}finally{busy=false;}}poll();</script></html>'''
            return self.respond(200,html.encode(),[('Content-Type','text/html; charset=utf-8'),
                ('Content-Security-Policy',"default-src 'none'; script-src 'nonce-"+nonce+"'; style-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"),*changes])
        except PermissionError:
            if method=='GET':
                body='''<!doctype html><html lang="fr"><meta charset="utf-8"><title>ArcIA — habilitation requise</title>
<main style="font:18px system-ui;max-width:680px;margin:12vh auto;padding:24px"><h1>Habilitation ArcIA requise</h1>
<p>Votre connexion Keycloak a réussi. Votre administrateur doit attribuer le rôle de realm <strong>ArcIA.User</strong> à ce compte dans « Role mapping ».</p>
<p><a href="/portal/login?reauth=1">Se reconnecter avec un autre compte</a> · <a href="/admin/users">Administration des utilisateurs</a></p></main></html>'''
                return self.respond(403,body.encode(),[('Content-Type','text/html; charset=utf-8')])
            return self.json(403,{'code':'ARCIA_USER_ROLE_REQUIRED','message':"Votre administrateur doit attribuer le rôle ArcIA.User à ce compte dans Keycloak."})
        except CapacityError:
            return self.json(503,{'code':'PERSONAL_RUNTIME_CAPACITY_REACHED','message':"Tous les espaces disponibles sont attribués. Contactez votre administrateur."})
        except BindingError:
            return self.json(503,{'code':'PERSONAL_RUNTIME_BINDING_REFUSED'})
        except (httpx.RequestError,jwt.PyJWKClientConnectionError):
            return self.json(503,{'code':'IDENTITY_UNAVAILABLE'})
        except urllib.error.HTTPError as exc:
            print('ARCIA_PORTAL_'+phase+'_HTTP_'+str(exc.code if exc.code in (400,401,403,404,409,429,500,503) else 0),flush=True)
            return self.json(503,{'code':'PERSONAL_RUNTIME_CONTROL_UNAVAILABLE'},changes)
        except Exception as exc:
            kind=type(exc).__name__
            allowed=('ValueError','KeyError','InvalidTokenError','ExpiredSignatureError','PyJWKClientError','URLError','SSLError')
            print('ARCIA_PORTAL_'+phase+'_'+(kind.upper() if kind in allowed else 'OTHER')+'_REFUSED',flush=True)
            if method=='GET' and path=='/portal/':return self.redirect('/portal/login')
            return self.json(401,{'code':'LOGIN_REFUSED','message':"Recommencez la connexion depuis la page d'accueil ArcIA."})


def kube_api(method,path,document=None):
    root=Path('/var/run/secrets/kubernetes.io/serviceaccount')
    request=urllib.request.Request('https://kubernetes.default.svc'+path,method=method,
        data=json.dumps(document).encode() if document is not None else None,
        headers={'Authorization':'Bearer '+(root/'token').read_text(),
                 'Content-Type':'application/merge-patch+json' if method=='PATCH' else 'application/json'})
    with urllib.request.urlopen(request,context=ssl.create_default_context(cafile=str(root/'ca.crt')),timeout=15) as response:
        return json.load(response)


if __name__=='__main__':
    server=ThreadingHTTPServer(('0.0.0.0',8080),Handler)
    server.portal=Portal(CONFIG,Path('/credentials/hmac').read_bytes(),kube_api)
    server.serve_forever()
