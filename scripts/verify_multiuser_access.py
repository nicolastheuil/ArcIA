"""Two actual local identities through pinned public TLS; never returns bodies."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import http.client
from http.cookies import SimpleCookie
import json
import copy
import re
import socket
import ssl

def verify(payload):
    main=payload['pilot'];second=payload['second_pilot'];host=main['hostname']
    context=ssl.create_default_context(cadata=main['tls_certificate'])
    leaf=re.search(r'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----',main['tls_certificate'],re.S).group()
    fingerprint=hashlib.sha256(ssl.PEM_cert_to_DER_cert(leaf)).digest()
    address=payload['instance']['endpoint_design']['https_ip'];cookies={who:SimpleCookie() for who in ('A','B')};checks={}
    def request(who,method,path,body=None,send_cookie=True,route=None,extra=None,remember=True):
        route=route or who;prefix='/qualification-b' if route=='B' else ''
        connection=http.client.HTTPSConnection(host,443,context=context,timeout=30)
        connection._create_connection=lambda dest,timeout,source_address=None:socket.create_connection((address,443),timeout)
        headers={'Origin':'https://'+host,'Content-Type':'application/json'}
        if send_cookie:headers['Cookie']='; '.join(k+'='+v.value for k,v in cookies[who].items())
        if extra:headers.update(extra)
        try:
            connection.connect()
            if hashlib.sha256(connection.sock.getpeercert(binary_form=True)).digest()!=fingerprint:raise ValueError('TLS_PIN_MISMATCH')
            connection.request(method,prefix+path,body=None if body is None else json.dumps(body),headers=headers)
            response=connection.getresponse();content=response.read()
            for key,value in response.getheaders():
                if key.lower()=='set-cookie' and remember:cookies[who].load(value)
            return response.status,content
        finally:connection.close()
    for who,identity in [('A',main),('B',second)]:
        checks[who+'_anonymous_denied']=request(who,'GET','/api/config',send_cookie=False)[0]==401
        other=second if who=='A' else main
        checks[who+'_other_password_denied']=request(who,'POST','/auth/password-login',{'provider':'basic','username':other['username'],'password':other['password']},False)[0] in (401,403)
        checks[who+'_login']=request(who,'POST','/auth/password-login',{'provider':'basic','username':identity['username'],'password':identity['password']},False)[0]==200
        checks[who+'_secure_httponly_cookie']=bool(cookies[who]) and all(v['secure'] and v['httponly'] for v in cookies[who].values())
        checks[who+'_own_config']=request(who,'GET','/api/config')[0]==200
        own='arcia-multiuser-qualification-'+who.lower();other_id='arcia-multiuser-qualification-'+('b' if who=='A' else 'a')
        checks[who+'_own_session_visible']=request(who,'GET','/api/sessions/'+own)[0]==200
        checks[who+'_other_session_denied']=request(who,'GET','/api/sessions/'+other_id)[0]==404
        checks[who+'_other_messages_denied']=request(who,'GET','/api/sessions/'+other_id+'/messages')[0]==404
        checks[who+'_other_export_denied']=request(who,'GET','/api/sessions/'+other_id+'/export')[0]==404
        checks[who+'_other_session_update_denied']=request(who,'PATCH','/api/sessions/'+other_id,{'title':'synthetic forbidden rename'})[0]==404
        checks[who+'_cookie_other_runtime_denied']=request(who,'GET','/api/config',route='B' if who=='A' else 'A',remember=False)[0]==401
        checks[who+'_identity_header_spoof_no_session_access']=request(who,'GET','/api/sessions/'+other_id,extra={'X-User-Id':other['username'],'X-Forwarded-Prefix':'/qualification-b' if who=='A' else '/','X-ArcIA-Scope':'qualification-'+('b' if who=='A' else 'a')})[0]==404
        status,html=request(who,'GET','/')
        checks[who+'_dashboard_html']=status==200 and b'<html' in html.lower()
        # Follow the actual SPA asset paths to verify trusted-prefix handling.
        assets=re.findall(rb'(?:src|href)="([^"?#]+\.(?:js|css))',html)
        checks[who+'_dashboard_assets']=bool(assets)
        for asset in assets[:4]:
            path=asset.decode();prefix='/qualification-b' if who=='B' else ''
            if prefix and path.startswith(prefix+'/'):path=path[len(prefix):]
            if not path.startswith('/'):path='/'+path
            checks[who+'_dashboard_assets'] &= request(who,'GET',path)[0]==200
    with ThreadPoolExecutor(max_workers=2) as pool:
        result=list(pool.map(lambda who:request(who,'GET','/api/sessions/arcia-multiuser-qualification-'+who.lower())[0],('A','B')))
    checks['simultaneous_identity_sessions']=result==[200,200]
    # Native logout must invalidate the session token, including replay.
    for who in ('A','B'):
        old=copy.deepcopy(cookies[who]);checks[who+'_logout']=request(who,'POST','/auth/logout',{})[0] in (200,302)
        cookies[who]=old;checks[who+'_logout_cookie_replay_denied']=request(who,'GET','/api/config')[0]==401
        token=next((v.value for k,v in old.items() if k.endswith('hermes_session_at')),'')
        checks[who+'_logout_bearer_replay_denied']=bool(token) and request(who,'GET','/api/config',send_cookie=False,extra={'Authorization':'Bearer '+token})[0]==401
    return {'passed':all(checks.values()),'checks':checks}
