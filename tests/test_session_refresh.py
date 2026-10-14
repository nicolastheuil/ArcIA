import asyncio
from http.cookies import SimpleCookie
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'services/multiuser'))
from dashboard_boundary import SessionRevocation


class SessionRefreshTests(unittest.TestCase):
    def exercise(self,cookies='',bearer='',*,revoked=(),refresh_result='valid',outage=False):
        sent=[];forwarded=[];verified=[];rotated=[]
        session=SimpleNamespace(access_token='new-owned-token',refresh_token='rotated-refresh',
            provider='arcia',expires_at=time.time()+120)
        def verify(token):
            verified.append(token)
            return session if token in ('owned-token','new-owned-token') and refresh_result!='foreign' else None
        def refresh(token):
            rotated.append(token)
            if outage:raise RuntimeError('private-failure-fixture')
            return None if refresh_result=='refused' else session
        async def app(scope,receive,send):
            forwarded.append(scope)
            await send({'type':'http.response.start','status':200,'headers':[]})
            await send({'type':'http.response.body','body':b'ok'})
        async def send(message):sent.append(message)
        middleware=SessionRevocation(app,'unused-fixture-path',verify,refresh)
        middleware.store=SimpleNamespace(contains=lambda token:token in revoked)
        headers=[(b'cookie',cookies.encode())]
        if bearer:headers.append((b'authorization',('Bearer '+bearer).encode()))
        scope={'type':'http','path':'/api/config','method':'GET','headers':headers}
        with patch.dict(os.environ,{'ARCIA_IDENTITY_ISSUER':'https://synthetic.invalid/identity/realms/arcia',
                'HERMES_DASHBOARD_PUBLIC_URL':'https://synthetic.invalid/u/p03'}):
            asyncio.run(middleware(scope,None,send))
        return sent,forwarded,verified,rotated

    def test_expired_and_missing_access_cookie_rotate_once_with_scoped_secure_cookies(self):
        for at in ('__Secure-hermes_session_at=expired-token; ',''):
            sent,forwarded,verified,rotated=self.exercise(at+'__Secure-hermes_session_rt=owned-refresh')
            self.assertEqual(sent[0]['status'],200);self.assertEqual(rotated,['owned-refresh'])
            self.assertIn('new-owned-token',verified)
            cookies=dict(forwarded[0]['headers'])[b'cookie'].decode()
            self.assertIn('__Secure-hermes_session_at=new-owned-token',cookies)
            renewed=SimpleCookie()
            for name,value in sent[0]['headers']:
                if name==b'set-cookie':renewed.load(value.decode())
            self.assertEqual(set(renewed),{'__Secure-hermes_session_at','__Secure-hermes_session_rt','__Secure-hermes_session_provider'})
            for value in renewed.values():
                self.assertEqual(value['path'],'/u/p03');self.assertTrue(value['secure']);self.assertTrue(value['httponly'])
                self.assertEqual(value['samesite'],'Lax')

    def test_explicit_logout_revocation_cannot_be_bypassed_by_refresh_cookie(self):
        sent,forwarded,_,rotated=self.exercise('__Secure-hermes_session_at=revoked-token; __Secure-hermes_session_rt=owned-refresh',revoked=('revoked-token',))
        self.assertEqual(sent[0]['status'],401);self.assertFalse(forwarded);self.assertFalse(rotated)
        sent,forwarded,_,rotated=self.exercise('__Secure-hermes_session_rt=owned-refresh',revoked=('owned-refresh',))
        self.assertEqual(sent[0]['status'],401);self.assertFalse(forwarded);self.assertFalse(rotated)

    def test_logout_revokes_refresh_cookie_for_replay_after_access_cookie_disappears(self):
        sent=[];revoked=set();rotated=[]
        session=SimpleNamespace(access_token='owned-token',refresh_token='',provider='arcia',expires_at=time.time()+120)
        async def app(scope,receive,send):await send({'type':'http.response.start','status':200,'headers':[]})
        async def send(message):sent.append(message)
        async def scenario():
            middleware=SessionRevocation(app,'unused-fixture-path',lambda token:session,lambda token:rotated.append(token))
            middleware.store=SimpleNamespace(contains=lambda token:token in revoked,revoke=lambda token,expiry:revoked.add(token))
            await middleware({'type':'http','path':'/auth/logout','method':'POST','headers':[
                (b'cookie',b'__Secure-hermes_session_at=owned-token; __Secure-hermes_session_rt=owned-refresh')]},None,send)
            self.assertIn('owned-refresh',revoked)
            sent.clear()
            await middleware({'type':'http','path':'/api/config','method':'GET','headers':[
                (b'cookie',b'__Secure-hermes_session_rt=owned-refresh')]},None,send)
        with patch.dict(os.environ,{'ARCIA_IDENTITY_ISSUER':'https://synthetic.invalid/identity/realms/arcia',
                'HERMES_DASHBOARD_PUBLIC_URL':'https://synthetic.invalid/u/p03'}):asyncio.run(scenario())
        self.assertEqual(sent[0]['status'],401);self.assertFalse(rotated)

    def test_bearer_refusal_does_not_fall_back_to_cookie_or_refresh(self):
        sent,forwarded,_,rotated=self.exercise('__Secure-hermes_session_at=owned-token; __Secure-hermes_session_rt=owned-refresh',bearer='foreign-bearer')
        self.assertEqual(sent[0]['status'],401);self.assertFalse(forwarded);self.assertFalse(rotated)

    def test_foreign_inactive_or_revoked_rotated_token_cannot_reach_application(self):
        for result,revoked in (('foreign',()),('refused',()),('valid',('new-owned-token',))):
            sent,forwarded,_,_=self.exercise('__Secure-hermes_session_rt=owned-refresh',refresh_result=result,revoked=revoked)
            self.assertEqual(sent[0]['status'],401);self.assertFalse(forwarded)

    def test_outage_keeps_closed_without_echoing_input_or_rotating_cookies(self):
        sent,forwarded,_,_=self.exercise('__Secure-hermes_session_rt=owned-refresh',outage=True)
        self.assertEqual(sent[0]['status'],503);self.assertFalse(forwarded)
        self.assertNotIn(b'private-failure-fixture',sent[1]['body']);self.assertFalse(sent[0]['headers'] and any(k==b'set-cookie' for k,_ in sent[0]['headers']))

    def test_inherited_root_cookie_does_not_shadow_personal_session_downstream(self):
        sent,forwarded,verified,rotated=self.exercise('__Host-hermes_session_at=root-token; __Host-hermes_session_rt=root-refresh; __Secure-hermes_session_at=owned-token; __Secure-hermes_session_rt=owned-refresh')
        self.assertEqual(sent[0]['status'],200);self.assertEqual(verified,['owned-token']);self.assertFalse(rotated)
        self.assertNotIn(b'__Host-',dict(forwarded[0]['headers'])[b'cookie'])

    def test_expired_cookie_without_refresh_is_refused(self):
        sent,forwarded,_,rotated=self.exercise('__Secure-hermes_session_at=expired-token')
        self.assertEqual(sent[0]['status'],401);self.assertFalse(forwarded);self.assertFalse(rotated)


if __name__=='__main__':unittest.main()
