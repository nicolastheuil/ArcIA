"""Fixed loopback management adapter. Global authority never reaches a browser."""
import json
import re
import time
import uuid
import urllib.request
import jwt


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


OPENER=urllib.request.build_opener(NoRedirect())


class Native:
    def __init__(self,jwt_secret,origin='http://127.0.0.1:20128'):
        if origin!='http://127.0.0.1:20128':raise ValueError('LOOPBACK_MANAGEMENT_REQUIRED')
        self.secret=jwt_secret;self.origin=origin

    def request(self,method,path,value=None):
        if not re.fullmatch(r'/api/(settings|providers|providers/bulk|keys|sync/cloud|(?:providers|keys)/[a-f0-9-]{36})',path):
            raise ValueError('NATIVE_MANAGEMENT_PATH_REFUSED')
        if path=='/api/sync/cloud' and (method!='POST' or value!={'action':'disable'}):
            raise ValueError('NATIVE_CLOUD_ACTION_REFUSED')
        now=int(time.time())
        cookie=jwt.encode({'authenticated':True,'iat':now,'exp':now+30,'jti':str(uuid.uuid4())},self.secret,algorithm='HS256')
        req=urllib.request.Request(self.origin+path,method=method,
            data=json.dumps(value).encode() if value is not None else None,
            headers={'Content-Type':'application/json','Cookie':'auth_token='+cookie})
        # Never propagate native errors/bodies into logs or browser responses.
        try:
            with OPENER.open(req,timeout=20) as response:
                raw=response.read(2097153)
                if len(raw)>2097152:raise ValueError('NATIVE_RESPONSE_LIMIT')
                return json.loads(raw) if raw else {}
        except Exception:raise RuntimeError('OMNIROUTE_MANAGEMENT_UNAVAILABLE') from None

    def private(self):
        value=self.request('GET','/api/settings')
        value=value.get('settings',value)
        if value.get('cloudEnabled') is not False or value.get('requireLogin') is not True:
            raise PermissionError('PRIVATE_AUTHENTICATED_ROUTER_REQUIRED')

    def enforce_private(self):
        value=self.request('GET','/api/settings')
        value=value.get('settings',value)
        if value.get('requireLogin') is not True:raise PermissionError('PRIVATE_AUTHENTICATED_ROUTER_REQUIRED')
        if value.get('cloudEnabled') is not False:
            if value.get('cloudConfigured') or value.get('cloudUrl'):raise PermissionError('PRIVATE_AUTHENTICATED_ROUTER_REQUIRED')
            try:self.request('POST','/api/sync/cloud',{'action':'disable'})
            except RuntimeError:pass
            # The pinned disable route commits the local flag before reporting
            # missing CLOUD_URL. Only read-back proves success; no cloud URL is
            # allowed here, so its external DELETE is never executed.
        self.private()

    def keys(self):
        return [{k:row.get(k) for k in ('id','name')} for row in self.request('GET','/api/keys')['keys']]

    def connections(self):
        value=self.request('GET','/api/providers')
        return [{k:c.get(k) for k in ('id','provider','name','isActive')} for c in value['connections']]

    def create(self,provider,name,key):
        self.private()
        # Bulk's validateKeys=false avoids the single-create API's automatic
        # upstream test. Keys remain native-encrypted; no paid probe is fired.
        value=self.request('POST','/api/providers/bulk',{'provider':provider,'validateKeys':False,
            'entries':[{'name':name,'apiKey':key}],'providerSpecificData':{'autoFetchModels':False}})
        created=value.get('created',[])
        if len(created)!=1:raise RuntimeError('PERSONAL_CONNECTION_CREATION_UNCERTAIN')
        identifier=str(uuid.UUID(created[0]['id']))
        self.request('PUT','/api/providers/'+identifier,{'group':'ArcIA.Personal','globalPriority':None})
        return identifier

    def delete(self,identifier):self.request('DELETE','/api/providers/'+str(uuid.UUID(identifier)))

    def scoped_key(self,name,connections,models):
        if not connections or not models:raise PermissionError('ADMIN_ROUTING_CONFIGURATION_REQUIRED')
        self.private()
        value=self.request('POST','/api/keys',{'name':name,'scopes':[],'allowedConnections':connections,
            'modelAccessMode':'restricted','allowedModels':models,'allowedCombos':[],'noLog':True})
        identifier=str(uuid.UUID(value['id']))
        self.request('PATCH','/api/keys/'+identifier,{'connectionAccessMode':'restricted','allowedConnections':connections,
            'modelAccessMode':'restricted','allowedModels':models,'allowedCombos':[],'scopes':[],
            'noLog':True,'compressionEnabled':False,'cacheDefaultMode':'bypass','allowAutoCombos':True,
            'allowedEndpoints':['chat'],'isActive':True})
        return {'id':identifier,'key':value['key']}

    def revoke_key(self,identifier):self.request('DELETE','/api/keys/'+str(uuid.UUID(identifier)))
