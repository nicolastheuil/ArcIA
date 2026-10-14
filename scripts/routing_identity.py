"""Owned, public PKCE client for the private OmniRoute personal page."""
import json
import base64
import secrets


def configure(values):
    scope={'__name__':'routing_identity_support'}
    exec(values['identity_worker_source'],scope)
    operation=values['operation_id']
    scope['owned']('Namespace','arcia-identity',None,operation)
    scope['apply'](values['identity_documents'],operation)
    scope['apply'](values['access_documents'],operation)
    with scope['forward']() as base:
        admin=scope['Admin'](base,values['hostname']);admin.authenticate(values['credentials'])
        realm=admin.resource()
        if realm.get('attributes',{}).get('arcia.operation-id')!=operation:raise ValueError('IDENTITY_FOREIGN_REALM')
        role='ArcIA.ProviderSelfService'
        if not any(r['name']==role for r in admin.resource('/roles')):admin.resource('/roles','POST',{'name':role})
        expected={'clientId':'arcia-routing','name':'OmniRoute personal providers','protocol':'openid-connect',
            'enabled':True,'publicClient':True,'standardFlowEnabled':True,'implicitFlowEnabled':False,
            'directAccessGrantsEnabled':False,'serviceAccountsEnabled':False,
            'redirectUris':[origin+'/personal/callback' for origin in values['origins']],
            'webOrigins':[],'attributes':{'pkce.code.challenge.method':'S256','arcia.operation-id':operation},
            'protocolMappers':[
                {'name':'routing-audience','protocol':'openid-connect','protocolMapper':'oidc-audience-mapper',
                    'config':{'included.client.audience':'arcia-routing','access.token.claim':'true','id.token.claim':'false'}},
                {'name':'routing-roles','protocol':'openid-connect','protocolMapper':'oidc-usermodel-realm-role-mapper',
                    'config':{'claim.name':'arcia_roles','multivalued':'true','jsonType.label':'String',
                        'access.token.claim':'true','id.token.claim':'true','userinfo.token.claim':'true'}}]}
        matches=admin.resource('/clients?clientId=arcia-routing')
        if not matches:admin.resource('/clients','POST',expected)
        else:
            previous=admin.client('arcia-routing')
            if previous.get('attributes',{}).get('arcia.operation-id')!=operation:raise ValueError('FOREIGN_ROUTING_OIDC_CLIENT')
            admin.resource('/clients/'+previous['id'],'PUT',{**previous,**expected})
        client=admin.client('arcia-routing')
        old=scope['owned']('Secret','routing-identity-checker','arcia-routing',operation,True)
        checker=json.loads(base64.b64decode(old['data']['checker.json'])) if old else {'client_secret':secrets.token_urlsafe(48)}
        technical=admin.resource('/clients?clientId=arcia-routing-checker')
        if not technical:
            admin.resource('/clients','POST',{'clientId':'arcia-routing-checker','enabled':True,'publicClient':False,
                'secret':checker['client_secret'],'standardFlowEnabled':False,'implicitFlowEnabled':False,
                'directAccessGrantsEnabled':False,'serviceAccountsEnabled':True,
                'attributes':{'arcia.operation-id':operation}})
        technical=admin.client('arcia-routing-checker')
        if technical.get('attributes',{}).get('arcia.operation-id')!=operation:raise ValueError('FOREIGN_ROUTING_CHECKER_CLIENT')
        service_user=admin.resource('/clients/'+technical['id']+'/service-account-user')
        management=admin.client('realm-management')
        current=admin.resource('/users/'+service_user['id']+'/role-mappings/clients/'+management['id'])
        if any(r['name'] not in ('view-users','query-users') for r in current):raise ValueError('ROUTING_CHECKER_PRIVILEGE_DRIFT')
        roles=[admin.resource('/clients/'+management['id']+'/roles/'+name) for name in ('view-users','query-users')]
        admin.resource('/users/'+service_user['id']+'/role-mappings/clients/'+management['id'],'POST',roles)
        privacy=scope['owned']('Secret','privacy-policy','arcia-privacy',operation)
        policy=json.loads(base64.b64decode(privacy['data']['policy.json']))
        bindings={}
        for name,namespace in [('qualification-a','arcia-hermes'),('qualification-b','arcia-hermes-qualification-b')]:
            binding=scope['owned']('Secret','arcia-oidc-runtime',namespace,operation,True)
            if binding:
                data=binding['data'];bindings[name]={
                    'issuer':base64.b64decode(data['ARCIA_IDENTITY_ISSUER']).decode(),
                    'subject':base64.b64decode(data['ARCIA_IDENTITY_OWNER_SUBJECT']).decode()}
        clients={'tokens':{token:item['scope'] for token,item in policy['tokens'].items()},'legacy_bindings':bindings}
        scope['apply']([
            {'apiVersion':'v1','kind':'Secret','metadata':{'name':'routing-identity-checker','namespace':'arcia-routing'},
                'type':'Opaque','stringData':{'checker.json':json.dumps(checker)}},
            {'apiVersion':'v1','kind':'Secret','metadata':{'name':'routing-clients','namespace':'arcia-routing'},
                'type':'Opaque','stringData':{'clients.json':json.dumps(clients)}}],operation)
        # Update only the sanitizer server, preserving its installed runtime,
        # detector models and all policy secrets. No cloud call is executed.
        privacy_code=scope['owned']('ConfigMap','privacy-code','arcia-privacy',operation)
        privacy_code['data']['server.py']=values['sanitizer_server_source']
        scope['apply']([{'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':'privacy-code','namespace':'arcia-privacy'},
            'data':privacy_code['data']}],operation)
        scope['kube']('rollout','restart','deployment/privacy','-n','arcia-privacy')
        scope['kube']('rollout','status','deployment/privacy','-n','arcia-privacy','--timeout=600s',timeout=620)
        scope['kube']('rollout','restart','deployment/omniroute','-n','arcia-routing')
        scope['kube']('rollout','status','deployment/omniroute','-n','arcia-routing','--timeout=600s',timeout=620)
        dns=scope['owned']('ConfigMap','private-dns-records','arcia-privacy',operation)
        records=json.loads(dns['data']['records.json'])
        service=scope['owned']('Service','omniroute','arcia-routing',operation)
        records['omniroute.arcia-routing.svc.cluster.local']=service['spec']['clusterIP']
        scope['apply']([{'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':'private-dns-records','namespace':'arcia-privacy'},
            'data':{'records.json':json.dumps(records)}}],operation)
        scope['kube']('rollout','restart','deployment/private-dns','-n','arcia-privacy')
        scope['kube']('rollout','status','deployment/private-dns','-n','arcia-privacy','--timeout=120s',timeout=140)
        policies=[{'apiVersion':'networking.k8s.io/v1','kind':'NetworkPolicy',
            'metadata':{'name':'routing-inference-only','namespace':namespace},
            'spec':{'podSelector':{'matchLabels':{'app':'hermes-pilot'}},'policyTypes':['Egress'],
                'egress':[{'to':[{'namespaceSelector':{'matchLabels':{'kubernetes.io/metadata.name':'arcia-routing'}},
                    'podSelector':{'matchLabels':{'app':'omniroute'}}}],'ports':[{'port':20131,'protocol':'TCP'}]}]}}
            for namespace in values['bound_namespaces']]
        scope['apply']([*policies,*[d for d in values['binding_documents'] if d['kind']=='ConfigMap']],operation)
        for doc in values['binding_documents']:
            if doc['kind']!='Deployment':continue
            previous=scope['owned']('Deployment',doc['metadata']['name'],doc['metadata']['namespace'],operation)
            if any(previous['metadata'][k]!=doc['metadata'].get(k) for k in ('uid','resourceVersion')):
                raise ValueError('ROUTING_RUNTIME_CHANGED_RETRY_REQUIRED')
            # Preserve the current deployment and its other managers. No forced
            # SSA adoption of the portal's config/hash fields; optimistic lock.
            scope['kube']('replace','-f','-',document=doc)
        for doc in values['binding_documents']:
            if doc['kind']=='Deployment' and doc['spec'].get('replicas',1):
                scope['kube']('rollout','status','deployment/hermes-pilot','-n',doc['metadata']['namespace'],'--timeout=600s',timeout=620)
        return {'passed':client['redirectUris']==expected['redirectUris'] and client['publicClient'] is True,
            'public_pkce_client':True,'password_grant_enabled':False,'personal_role_created':True,
            'personal_role_automatically_assigned':False,'provider_calls_executed':False,
            'owned_runtime_bindings':len(values['bound_namespaces']),'model_routing':'omniroute_admin_policy'}


if __name__=='__main__':print(json.dumps(configure(ARCIA_INPUT)))
