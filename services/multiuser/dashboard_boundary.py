"""ArcIA local-session revocation around the pinned, unmodified Hermes app."""
import asyncio
from contextlib import contextmanager
import hashlib
from http.cookies import SimpleCookie
import json
import os
from pathlib import Path
import sqlite3
import sys
import time

PUBLIC=('/login','/auth/','/assets/','/static/','/api/auth/providers','/api/health','/favicon')

def native_session(token):
    from hermes_cli.dashboard_auth import list_session_providers
    for provider in list_session_providers():
        session=provider.verify_session(access_token=token)
        if session is not None:return session
    return None

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
    def __init__(self,app,path=None,verifier=native_session):
        self.app=app;self.verifier=verifier
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
            tokens=[v.value for k,v in cookie.items() if k in ('hermes_session_at','__Host-hermes_session_at','__Secure-hermes_session_at')]
            bearer=headers.get('authorization','')
            if bearer.startswith('Bearer '):tokens.append(bearer[7:])
            tokens=list(dict.fromkeys(t for t in tokens if 0<len(t)<=8192))
            if not any(path.startswith(p) for p in PUBLIC):
                for token in tokens:
                    if await asyncio.to_thread(self.store.contains,token):return await self.deny(scope,send,401)
            if scope['type']=='http' and path=='/auth/logout' and scope.get('method')=='POST':
                for token in tokens:
                    session=await asyncio.to_thread(self.verifier,token)
                    if session is not None:await asyncio.to_thread(self.store.revoke,token,session.expires_at)
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
                        valid=any([await asyncio.to_thread(self.verifier,token) is not None for token in tokens])
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
