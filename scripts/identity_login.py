"""Synthetic browser-style PKCE login over the pinned designated HTTPS endpoint.

Private credentials/cookies stay inside the calling protected controller.
"""
import hashlib
import http.client
from http.cookies import SimpleCookie
from html.parser import HTMLParser
import re
import socket
import ssl
import json
from urllib.parse import urljoin, urlsplit, urlencode


class Form(HTMLParser):
    def __init__(self):
        super().__init__();self.action=None;self.inputs={};self.active=False
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='form' and attrs.get('id')=='kc-form-login':
            self.active=True;self.action=attrs.get('action')
        if tag=='input' and self.active and attrs.get('name') and attrs.get('type')=='hidden':
            self.inputs[attrs['name']]=attrs.get('value','')
    def handle_endtag(self,tag):
        if tag=='form':self.active=False


class Browser:
    def __init__(self,pilot,address):
        self.host=pilot['hostname'];self.address=address;self.cookies=SimpleCookie();self.native=SimpleCookie()
        self.context=ssl.create_default_context(cadata=pilot['tls_certificate'])
        leaf=re.search(r'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----',pilot['tls_certificate'],re.S).group()
        self.pin=hashlib.sha256(ssl.PEM_cert_to_DER_cert(leaf)).digest()
    def request(self,method,url,data=None,extra_headers=None):
        url=urljoin('https://'+self.host+'/',url);parts=urlsplit(url)
        if parts.scheme!='https' or parts.hostname!=self.host or parts.port not in (None,443):
            raise ValueError('IDENTITY_LOGIN_REDIRECT_REFUSED')
        connection=http.client.HTTPSConnection(self.host,context=self.context,timeout=20)
        connection._create_connection=lambda dest,timeout,source_address=None:socket.create_connection((self.address,443),timeout)
        cookie='; '.join(k+'='+v.coded_value for k,v in self.cookies.items() if parts.path.startswith(v['path'] or '/'))
        headers={'Origin':'https://'+self.host,'Cookie':cookie}
        if extra_headers:headers.update(extra_headers)
        if data is not None:headers['Content-Type']='application/x-www-form-urlencoded'
        try:
            connection.connect()
            if hashlib.sha256(connection.sock.getpeercert(binary_form=True)).digest()!=self.pin:
                raise ValueError('IDENTITY_LOGIN_TLS_PIN_FAILED')
            path=parts.path+('?' + parts.query if parts.query else '')
            connection.request(method,path,body=urlencode(data) if data is not None else None,headers=headers)
            response=connection.getresponse();body=response.read();location=response.getheader('Location')
            for key,value in response.getheaders():
                if key.lower()=='set-cookie':
                    self.cookies.load(value)
                    parsed=SimpleCookie();parsed.load(value)
                    for name,morsel in parsed.items():
                        if 'hermes_session' in name:self.native.load(morsel.OutputString())
            return response.status,body,location
        finally:connection.close()
    def follow(self,url):
        for _ in range(12):
            status,body,location=self.request('GET',url)
            if status not in (301,302,303,307,308):return status,body
            url=urljoin(urljoin('https://'+self.host+'/',url),location)
        raise ValueError('IDENTITY_LOGIN_TOO_MANY_REDIRECTS')
    def login(self,prefix,username,password):
        status,body=self.follow(prefix+'/auth/login?provider=arcia')
        form=Form();form.feed(body.decode())
        if status!=200 or not form.action:raise ValueError('IDENTITY_LOGIN_FORM_MISSING')
        status,body,location=self.request('POST',form.action,{**form.inputs,'username':username,'password':password,'credentialId':''})
        if status not in (302,303) or not location:raise ValueError('IDENTITY_LOGIN_REFUSED')
        status,body=self.follow(location)
        if status!=200 or not any(k.endswith('hermes_session_at') for k in self.native):
            for text,code in [('Missing PKCE state cookie','IDENTITY_PKCE_COOKIE_MISSING'),
                              ('OAuth state mismatch','IDENTITY_STATE_MISMATCH'),
                              ('Invalid code','IDENTITY_CODE_REFUSED'),
                              ('Provider unreachable','IDENTITY_PROVIDER_UNAVAILABLE'),
                              ('ARCIA_LOGIN_REFUSED','IDENTITY_CODE_REFUSED')]:
                if text.encode() in body:raise ValueError(code)
            raise ValueError('IDENTITY_SESSION_NOT_ESTABLISHED')
        return self.native

    def portal_login(self,username,password):
        status,body=self.follow('/portal/login')
        form=Form();form.feed(body.decode())
        if status!=200 or not form.action:raise ValueError('PERSONAL_PORTAL_LOGIN_FORM_MISSING')
        status,body,location=self.request('POST',form.action,{**form.inputs,'username':username,'password':password,'credentialId':''})
        if status not in (302,303) or not location:raise ValueError('PERSONAL_PORTAL_LOGIN_REFUSED')
        status,body=self.follow(location)
        match=re.search(rb'const csrf=("[A-Za-z0-9_-]+")',body)
        if status!=200 or not match:raise ValueError('PERSONAL_PORTAL_SESSION_REFUSED')
        return json.loads(match.group(1))
