"""Local HTTPS qualification. Private stdin; only fixed boolean checks on stdout."""
import http.client
import hashlib
from http.cookies import SimpleCookie
import json
import socket
import ssl
import sys
import re


def verify(payload):
    pilot=payload['pilot'];host=pilot['hostname'];address=payload['address']
    context=ssl.create_default_context(cadata=pilot['tls_certificate'])
    leaf=re.search(r'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----',pilot['tls_certificate'],re.S).group()
    expected_certificate=hashlib.sha256(ssl.PEM_cert_to_DER_cert(leaf)).digest()
    cookies=SimpleCookie()
    def request(method,path,body=None,authenticated=False):
        connection=http.client.HTTPSConnection(host,443,context=context,timeout=15)
        connection._create_connection=lambda destination,timeout,source_address=None: socket.create_connection((address,443),timeout)
        headers={'Origin':'https://'+host,'Content-Type':'application/json'}
        if authenticated: headers['Cookie']='; '.join(key+'='+value.value for key,value in cookies.items())
        try:
            connection.connect()
            if hashlib.sha256(connection.sock.getpeercert(binary_form=True)).digest()!=expected_certificate:
                raise ValueError('PILOT_CERTIFICATE_PIN_MISMATCH')
            connection.request(method,path,body=json.dumps(body) if body is not None else None,headers=headers)
            response=connection.getresponse();content=response.read()
            for name,value in response.getheaders():
                if name.lower()=='set-cookie': cookies.load(value)
            return response.status,content
        finally: connection.close()
    checks={}
    if payload.get('public_acme'):
        public_context=ssl.create_default_context()
        with socket.create_connection((address,443),timeout=15) as raw:
            with public_context.wrap_socket(raw,server_hostname=host) as tls:
                checks['public_ca_chain_and_hostname']=bool(tls.getpeercert())
    checks['tls_hostname_and_pinned_certificate']=request('GET','/api/health')[0]==200
    checks['anonymous_config_denied']=request('GET','/api/config')[0] in (401,403)
    checks['wrong_password_denied']=request('POST','/auth/password-login',
        {'provider':'basic','username':pilot['username'],'password':'synthetic-invalid-password'})[0] in (401,403)
    checks['local_password_login']=request('POST','/auth/password-login',
        {'provider':'basic','username':pilot['username'],'password':pilot['password']})[0]==200
    checks['secure_httponly_session_cookie']=bool(cookies) and all(
        bool(value['secure']) and bool(value['httponly']) for value in cookies.values())
    checks['authenticated_config_access']=request('GET','/api/config',authenticated=True)[0]==200
    return {'status':'verified' if all(checks.values()) else 'blocked',
        'code':'PILOT_HTTPS_AUTH_VERIFIED' if all(checks.values()) else 'PILOT_HTTPS_AUTH_FAILED','checks':checks,
        'cookie_attributes':[{'name':key if key in ('hermes_session','hermes_session_refresh','hermes_session_provider','hermes_session_access') else 'other',
            'secure':bool(value['secure']),'httponly':bool(value['httponly'])} for key,value in cookies.items()]}


if __name__=='__main__':
    try: result=verify(json.load(sys.stdin))
    except Exception: result={'status':'blocked','code':'PILOT_HTTPS_CONNECTION_OR_AUTH_FAILED'}
    print(json.dumps(result))
    sys.exit(0 if result['status']=='verified' else 2)
