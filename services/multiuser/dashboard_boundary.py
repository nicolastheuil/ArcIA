"""ArcIA local-session revocation around the pinned, unmodified Hermes app."""
import asyncio
from contextlib import contextmanager
import hashlib
from http.cookies import SimpleCookie
import json
import logging
import os
from pathlib import Path
import sqlite3
import sys
import time
from urllib.parse import urlsplit

PUBLIC=('/login','/auth/','/assets/','/static/','/api/auth/providers','/api/health','/favicon')

def native_session(token):
    from hermes_cli.dashboard_auth import list_session_providers
    for provider in list_session_providers():
        session=provider.verify_session(access_token=token)
        if session is not None:return session
    return None


def native_refresh(token):
    # Use Hermes' single-flight rotation: simultaneous requests must not reuse a RT.
    from hermes_cli.dashboard_auth.refresh_singleflight import refresh_session_coalesced
    result=refresh_session_coalesced(token,'arcia',phase='arcia-boundary',log=logging.getLogger(__name__))
    return result[0] if result else None


def session_cookie_shape(scope=None):
    url=urlsplit(os.environ.get('HERMES_DASHBOARD_PUBLIC_URL',''))
    path=url.path.rstrip('/') or '/'
    if path=='/' and scope:
        # The legacy A route has a fixed ingress prefix while its public URL is root.
        forwarded=dict(scope.get('headers',[])).get(b'x-forwarded-prefix',b'').decode()
        if forwarded in ('/qualification-a','/qualification-b'):path=forwarded
    variant='__Secure-' if path!='/' else '__Host-'
    return (variant if url.scheme=='https' else ''),path,url.scheme=='https'


def renewed_cookie_headers(session,scope):
    variant,path,secure=session_cookie_shape(scope)
    ttl=int(session.expires_at-time.time())
    if ttl<=0:raise ValueError('VERIFIED_SESSION_EXPIRY_REQUIRED')
    result=[]
    for name,value,age in (('hermes_session_at',session.access_token,ttl),
            ('hermes_session_rt',session.refresh_token,30*24*60*60),
            ('hermes_session_provider',session.provider,30*24*60*60)):
        if not value:continue
        cookie=SimpleCookie();cookie[variant+name]=value
        morsel=cookie[variant+name];morsel['path']=path;morsel['httponly']=True
        morsel['samesite']='Lax';morsel['max-age']=age
        if secure:morsel['secure']=True
        result.append((b'set-cookie',morsel.OutputString().encode('latin-1')))
    return result

class Revocations:
    def __init__(self,path):self.path=path
    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=5)
        try:
            os.chmod(self.path,0o600)
            db.execute('CREATE TABLE IF NOT EXISTS revocations(digest TEXT PRIMARY KEY,expires REAL NOT NULL)')
            with db:yield db
        finally:db.close()
    def digest(self,token):return hashlib.sha256(token.encode()).hexdigest()
    def contains(self,token):
        with self.connect() as db:
            row=db.execute('SELECT expires FROM revocations WHERE digest=?',(self.digest(token),)).fetchone()
        return row is not None and row[0]>time.time()
    def revoke(self,token,expires):
        now=time.time()
        if not isinstance(expires,(float,int)) or expires<=now:raise ValueError('VERIFIED_SESSION_EXPIRY_REQUIRED')
        with self.connect() as db:
            db.execute('DELETE FROM revocations WHERE expires<=?',(now,))
            if db.execute('SELECT count(*) FROM revocations').fetchone()[0]>=10000:raise ValueError('REVOCATION_CAPACITY')
            db.execute('INSERT OR REPLACE INTO revocations(digest,expires) VALUES(?,?)',(self.digest(token),expires))

class SessionRevocation:
    def __init__(self,app,path=None,verifier=native_session,refresher=native_refresh):
        self.app=app;self.verifier=verifier;self.refresher=refresher
        self.store=Revocations(path or str(Path(os.environ['HERMES_HOME'])/'dashboard-revocations.sqlite'))
    async def deny(self,scope,send,status):
        if scope['type']=='websocket':return await send({'type':'websocket.close','code':4401})
        body=json.dumps({'error':'SESSION_REVOKED' if status==401 else 'SESSION_POLICY_UNAVAILABLE'}).encode()
        await send({'type':'http.response.start','status':status,'headers':[(b'content-type',b'application/json'),(b'cache-control',b'no-store'),(b'content-length',str(len(body)).encode())]})
        await send({'type':'http.response.body','body':body})
    async def __call__(self,scope,receive,send):
        if scope['type'] not in ('http','websocket'):return await self.app(scope,receive,send)
        path=scope.get('path','');headers={k.decode().lower():v.decode() for k,v in scope.get('headers',[])}
        try:
            cookie=SimpleCookie();cookie.load(headers.get('cookie',''))
            bound=bool(os.environ.get('ARCIA_IDENTITY_ISSUER'))
            if bound:
                # An inherited root cookie must not shadow this runtime's scoped session.
                variant,_,_=session_cookie_shape(scope)
                names=('hermes_session_at','hermes_session_rt','hermes_session_provider')
                for name in tuple(cookie):
                    if any(name==v+n for n in names for v in ('__Host-','__Secure-','')) and not name.startswith(variant):
                        del cookie[name]
                headers['cookie']='; '.join(k+'='+v.coded_value for k,v in cookie.items())
                scope={**scope,'headers':[(k,v) for k,v in scope.get('headers',[]) if k.lower()!=b'cookie']+
                    [(b'cookie',headers['cookie'].encode('latin-1'))]}
            tokens=[v.value for k,v in cookie.items() if k in ('hermes_session_at','__Host-hermes_session_at','__Secure-hermes_session_at')]
            bearer=headers.get('authorization','')
            if bearer.startswith('Bearer '):tokens=[bearer[7:]]
            tokens=list(dict.fromkeys(t for t in tokens if 0<len(t)<=8192))
            if not any(path.startswith(p) for p in PUBLIC):
                for token in tokens:
                    if await asyncio.to_thread(self.store.contains,token):return await self.deny(scope,send,401)
                if bound:
                    refresh=cookie.get(variant+'hermes_session_rt')
                    if not bearer and refresh and await asyncio.to_thread(self.store.contains,refresh.value):
                        return await self.deny(scope,send,401)
                    sessions=[await asyncio.to_thread(self.verifier,token) for token in tokens]
                    if (not any(session is not None for session in sessions) and scope['type']=='http' and
                            not bearer and refresh and 0<len(refresh.value)<=8192):
                        session=await asyncio.to_thread(self.refresher,refresh.value)
                        if session is not None:
                            # The refresher never substitutes for owner/audience/online validation.
                            verified=await asyncio.to_thread(self.verifier,session.access_token)
                            if verified is None:return await self.deny(scope,send,401)
                            if await asyncio.to_thread(self.store.contains,session.access_token):return await self.deny(scope,send,401)
                            tokens=[session.access_token];sessions=[verified]
                            cookie[variant+'hermes_session_at']=session.access_token
                            if session.refresh_token:cookie[variant+'hermes_session_rt']=session.refresh_token
                            cookie[variant+'hermes_session_provider']=session.provider
                            scope={**scope,'headers':[(k,v) for k,v in scope.get('headers',[]) if k.lower()!=b'cookie']+
                                [(b'cookie','; '.join(k+'='+v.coded_value for k,v in cookie.items()).encode('latin-1'))]}
                            rotated_headers=renewed_cookie_headers(session,scope)
                            original_send=send
                            async def send_rotated(message):
                                if message['type']=='http.response.start':
                                    message={**message,'headers':list(message.get('headers',[]))+rotated_headers}
                                await original_send(message)
                            send=send_rotated
                    if not tokens and not refresh and scope['type']=='http' and scope.get('method')=='GET' and path=='/':
                        url=os.environ['HERMES_DASHBOARD_PUBLIC_URL'].rstrip('/')+'/auth/login?provider=arcia'
                        await send({'type':'http.response.start','status':303,'headers':[(b'location',url.encode()),(b'cache-control',b'no-store')]})
                        return await send({'type':'http.response.body','body':b''})
                    if not tokens:return await self.deny(scope,send,401)
                    if not any(session is not None for session in sessions):return await self.deny(scope,send,401)
            if scope['type']=='http' and path=='/auth/logout' and scope.get('method')=='POST':
                logout_session=None
                for token in tokens:
                    session=await asyncio.to_thread(self.verifier,token)
                    if session is not None:
                        logout_session=session
                        await asyncio.to_thread(self.store.revoke,token,session.expires_at)
                if bound:
                    refresh=cookie.get(variant+'hermes_session_rt')
                    if refresh and 0<len(refresh.value)<=8192:
                        if logout_session is None:
                            logout_session=await asyncio.to_thread(self.refresher,refresh.value)
                            if logout_session is not None:
                                verified=await asyncio.to_thread(self.verifier,logout_session.access_token)
                                if verified is None:logout_session=None
                        if logout_session is not None:
                            # A disappearing AT must not make the logged-out RT replayable.
                            expiry=time.time()+30*24*60*60
                            await asyncio.to_thread(self.store.revoke,refresh.value,expiry)
                            if logout_session.refresh_token:
                                await asyncio.to_thread(self.store.revoke,logout_session.refresh_token,expiry)
        except Exception:return await self.deny(scope,send,503)
        if os.environ.get('ARCIA_IDENTITY_ISSUER') and (
                scope['type']=='websocket' or (scope['type']=='http' and 'text/event-stream' in headers.get('accept',''))):
            # Long connections recheck the parent session; a disabled account cannot
            # keep a previously authenticated WebSocket/SSE alive indefinitely.
            if not tokens:return await self.deny(scope,send,401)
            task=asyncio.create_task(self.app(scope,receive,send))
            try:
                while not task.done():
                    done,_=await asyncio.wait({task},timeout=5)
                    if done:break
                    try:
                        valid=any([not await asyncio.to_thread(self.store.contains,token) and
                            await asyncio.to_thread(self.verifier,token) is not None for token in tokens])
                    except Exception:valid=False
                    if not valid:
                        task.cancel()
                        if scope['type']=='websocket':await send({'type':'websocket.close','code':4401})
                        else:await send({'type':'http.response.body','body':b'','more_body':False})
                        return
                await task
            finally:
                if not task.done():task.cancel()
                await asyncio.gather(task,return_exceptions=True)
            return
        await self.app(scope,receive,send)

def main():
    sys.path.insert(0,'/opt/hermes')
    if os.environ.get('ARCIA_IDENTITY_ISSUER'):
        if not all(os.environ.get(name) for name in ('ARCIA_IDENTITY_CLIENT_ID','ARCIA_IDENTITY_OWNER_SUBJECT')):
            raise SystemExit('ARCIA_PERSONAL_BINDING_REQUIRED')
        # A centrally disabled user cannot bypass the IdP with the historical
        # qualification password. Its hash remains preserved for explicit rollback.
        for name in tuple(os.environ):
            if name.startswith('HERMES_DASHBOARD_BASIC_AUTH_'):del os.environ[name]
    Path('/tmp/hermes-runtime').mkdir(mode=0o700,exist_ok=True)
    from hermes_cli.web_server import app
    app.add_middleware(SessionRevocation)
    from hermes_cli.main import main as hermes_main
    sys.argv=['hermes','dashboard','--host','0.0.0.0','--port','9119','--no-open']
    hermes_main()

if __name__=='__main__':main()
