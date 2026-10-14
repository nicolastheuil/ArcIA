"""Fixed owned-cluster operations; native credentials never leave protected I/O."""
import base64
import hashlib
import json
import secrets
import subprocess
import time

NS='arcia-routing'
LAN_NS='arcia-routing-lan'


def kube(*args,document=None,timeout=90):
    result=subprocess.run(['/usr/local/bin/k3s','kubectl',*args],
        input=json.dumps(document).encode() if document is not None else None,capture_output=True,timeout=timeout)
    if result.returncode:raise RuntimeError('ROUTING_KUBERNETES_OPERATION_FAILED')
    return result.stdout.decode()


def owned(kind,name,namespace,operation,optional=False):
    args=['get',kind,name,'-o','json']
    if namespace:args+=['-n',namespace]
    if optional:args+=['--ignore-not-found']
    raw=kube(*args)
    if not raw:return None
    doc=json.loads(raw)
    if doc['metadata'].get('annotations',{}).get('arcia.io/operation-id')!=operation:raise ValueError('FOREIGN_ROUTING_RESOURCE')
    return doc


def apply(documents,operation):
    for doc in documents:
        meta=doc['metadata'];owned(doc['kind'],meta['name'],meta.get('namespace'),operation,True)
        meta.setdefault('annotations',{})['arcia.io/operation-id']=operation
    kube('apply','--server-side','--field-manager=arcia-foundation','-f','-',
         document={'apiVersion':'v1','kind':'List','items':documents})


RPC='''import json,os,sys,urllib.request,urllib.error,http.cookiejar
value=json.load(sys.stdin)
jar=http.cookiejar.CookieJar()
opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
base='http://127.0.0.1:20128'
def request(method,path,data=None):
    req=urllib.request.Request(base+path,method=method,data=json.dumps(data).encode() if data is not None else None,
        headers={'Content-Type':'application/json','Origin':base,'X-Forwarded-Proto':'https'})
    with opener.open(req,timeout=30) as response:return json.load(response)
# API requests are internal, but the cookie must stay Secure for browser use.
# Use its server-minted value in a Cookie header on this loopback RPC only.
login=request('POST','/api/auth/login',{'password':os.environ['INITIAL_PASSWORD']})
cookies='; '.join(c.name+'='+c.value for c in jar)
if not cookies:raise RuntimeError('ROUTING_ADMIN_COOKIE_REQUIRED')
if value['method']=='PATCH' and value['path']=='/api/settings':
    value['data']['currentPassword']=os.environ['INITIAL_PASSWORD']
req=urllib.request.Request(base+value['path'],method=value['method'],
    data=json.dumps(value.get('data')).encode() if value.get('data') is not None else None,
    headers={'Content-Type':'application/json','Cookie':cookies,'Origin':base,'X-Forwarded-Proto':'https'})
with opener.open(req,timeout=45) as response:print(json.dumps(json.load(response)))
'''


def native(operation,method,path,data=None):
    owned('Deployment','omniroute',NS,operation)
    pods=json.loads(kube('get','pods','-n',NS,'-l','app=omniroute','-o','json'))['items']
    active=[p for p in pods if p['status']['phase']=='Running' and not p['metadata'].get('deletionTimestamp')]
    if len(active)!=1:raise ValueError('SINGLE_ROUTER_OWNER_REQUIRED')
    # Values are stdin, never argv. Output remains inside the protected worker.
    result=subprocess.run(['/usr/local/bin/k3s','kubectl','exec','-i',active[0]['metadata']['name'],'-n',NS,'--',
        '/opt/hermes/.venv/bin/python','-c',RPC],input=json.dumps({'method':method,'path':path,'data':data}).encode(),
        capture_output=True,timeout=100)
    if result.returncode:raise RuntimeError('OMNIROUTE_MANAGEMENT_API_FAILED')
    return json.loads(result.stdout)


def inspect(values):
    op=values['operation_id'];owned('Namespace',NS,None,op)
    deployment=owned('Deployment','omniroute',NS,op)
    lan=owned('DaemonSet','routing-lan',LAN_NS,op)
    policy=json.loads(owned('ConfigMap','routing-policy',NS,op)['data']['policy.json'])
    return {'router_ready':deployment.get('status',{}).get('readyReplicas',0)==1,
        'lan_ready_nodes':lan.get('status',{}).get('numberReady',0),'lan_port':20129,'public_ingress_created':False,
        'automatic_mode':policy['automatic_mode'],'personal_provider_role':policy['personal_role'],
        'single_state_owner':deployment['spec']['replicas']==1 and deployment['spec']['strategy']['type']=='Recreate'}


def install(values):
    op=values['operation_id'];existing=owned('Namespace',NS,None,op,True)
    previous=owned('Deployment','omniroute',NS,op,True) if existing else None
    repair=False
    if previous and previous['spec']['template']['metadata']['annotations'].get('arcia.io/runtime-sha256')!=values['digest']:
        if not values.get('repair_unqualified_runtime') or previous.get('status',{}).get('readyReplicas',0):
            raise ValueError('CONTROLLED_ROUTER_RUNTIME_UPGRADE_REQUIRED')
        if owned('ConfigMap','routing-qualification-proof',NS,op,True):
            raise ValueError('QUALIFIED_ROUTER_REPAIR_REFUSED')
        repair=True
    apply(values['documents'],op)
    # Remove only the owned, never-started relay from the initial PSA failure.
    # No application workload, provider state or volume is touched.
    old_lan=owned('DaemonSet','routing-lan',NS,op,True)
    if old_lan:
        if old_lan.get('status',{}).get('currentNumberScheduled',0)!=0:
            raise ValueError('ACTIVE_ROUTING_RELAY_MIGRATION_REQUIRED')
        kube('delete','daemonset','routing-lan','-n',NS,'--wait=true','--timeout=90s')
        for kind,name in [('ConfigMap','routing-nginx'),('NetworkPolicy','lan-only'),('Secret','routing-tls')]:
            if owned(kind,name,NS,op,True):kube('delete',kind,name,'-n',NS,'--wait=true','--timeout=90s')
    secret=owned('Secret','routing-credentials',NS,op,True)
    if not secret:
        credentials={key:secrets.token_urlsafe(48) for key in ('JWT_SECRET','INITIAL_PASSWORD')}
        credentials.update({key:secrets.token_hex(32) for key in ('API_KEY_SECRET','STORAGE_ENCRYPTION_KEY')})
        apply([{'apiVersion':'v1','kind':'Secret','metadata':{'name':'routing-credentials','namespace':NS},'type':'Opaque',
            'stringData':credentials}],op)
    tls=owned('Secret','pilot-tls','arcia-ingress',op)
    apply([{'apiVersion':'v1','kind':'Secret','metadata':{'name':'routing-tls','namespace':LAN_NS},'type':'kubernetes.io/tls','data':tls['data']}],op)
    if values['policy'].get('ip_https_enabled'):
        ip_tls=owned('Secret','routing-ip-tls',LAN_NS,op,True)
        supplied=values.get('ip_tls')
        if supplied:
            data={k:base64.b64encode(supplied[v].encode()).decode() for k,v in [('tls.crt','certificate_pem'),('tls.key','private_key_pem')]}
            if ip_tls and ip_tls.get('data')!=data:raise ValueError('CONTROLLED_ROUTING_IP_TLS_ROTATION_REQUIRED')
            if not ip_tls:apply([{'apiVersion':'v1','kind':'Secret','metadata':{'name':'routing-ip-tls','namespace':LAN_NS},
                'type':'kubernetes.io/tls','data':data}],op)
        elif not ip_tls:raise ValueError('PROTECTED_ROUTING_IP_CERTIFICATE_REQUIRED')
    if repair:
        kube('scale','deployment/omniroute','-n',NS,'--replicas=0')
        kube('wait','--for=delete','pods','-l','app=omniroute','-n',NS,'--timeout=180s',timeout=200)
        previous=None
    if not previous:
        name=values['job']['metadata']['name'];job=owned('Job',name,NS,op,True)
        if job and any(c['type']=='Failed' and c['status']=='True' for c in job.get('status',{}).get('conditions',[])):
            kube('delete','job',name,'-n',NS,'--wait=true','--timeout=90s',timeout=100)
        apply([values['job']],op);deadline=time.monotonic()+1800
        while time.monotonic()<deadline:
            job=owned('Job',name,NS,op)
            if job.get('status',{}).get('succeeded')==1:break
            if any(c['type']=='Failed' and c['status']=='True' for c in job.get('status',{}).get('conditions',[])):
                raise RuntimeError('OMNIROUTE_INSTALLER_FAILED')
            time.sleep(3)
        else:raise TimeoutError('OMNIROUTE_INSTALL_TIMEOUT')
        kube('delete','job',name,'-n',NS,'--wait=true','--timeout=90s',timeout=100)
    apply([values['deployment'],values['lan']],op)
    kube('rollout','status','deployment/omniroute','-n',NS,'--timeout=600s',timeout=620)
    # The initial password may have been changed by the administrator. Never
    # reset it or overwrite settings during reconciliation.
    if not previous:native(op,'PATCH','/api/settings',{'requireLogin':True})
    kube('rollout','status','daemonset/routing-lan','-n',LAN_NS,'--timeout=300s',timeout=320)
    result=inspect(values)
    result.update(passed=result['router_ready'] and result['lan_ready_nodes']==3,credentials_preserved=bool(secret),
                  existing_volumes_preserved=bool(previous),providers_automatically_activated=False)
    return result


def verify(values):
    result=inspect(values)
    # Negative authentication check survives an administrator password change.
    owned('Deployment','omniroute',NS,values['operation_id'])
    code="import urllib.request,urllib.error;\ntry:\n urllib.request.urlopen('http://127.0.0.1:20128/api/keys',timeout=15);print(0)\nexcept urllib.error.HTTPError as e:print(e.code)"
    status=kube('exec','deployment/omniroute','-n',NS,'--','/opt/hermes/.venv/bin/python','-c',code)
    result['anonymous_management_denied']=status.strip() in ('401','403')
    result['passed']=result['router_ready'] and result['lan_ready_nodes']==3 and result['single_state_owner'] and result['anonymous_management_denied']
    result['model_call_executed']=False
    if result['passed']:
        apply([{'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':'routing-qualification-proof','namespace':NS},
            'data':{'proof.json':json.dumps({'portal_verified':True,'verified_at_unix':int(time.time())})}}],values['operation_id'])
    return result


def access(values):
    credentials=owned('Secret','routing-credentials',NS,values['operation_id'])
    return {'initial_password':base64.b64decode(credentials['data']['INITIAL_PASSWORD']).decode()}


def network_policy(values):
    op=values['operation_id']
    if not owned('Namespace',NS,None,op,True):return {'lan_cidrs':[]}
    current=owned('ConfigMap','routing-policy',NS,op,True)
    policy=json.loads(current['data']['policy.json']) if current else {}
    return {'lan_cidrs':policy.get('lan_cidrs',[]),'private_firewall_boundary':policy.get('private_firewall_boundary',False),
        'ip_https_enabled':policy.get('ip_https_enabled',False)}


def public_ip_certificate(values):
    secret=owned('Secret','routing-ip-tls',LAN_NS,values['operation_id'])
    return {'certificate_pem':base64.b64decode(secret['data']['tls.crt']).decode()}


def read_bindings(values):
    result={};operation=values['operation_id']
    for namespace in values['namespaces']:
        if namespace not in ('arcia-hermes','arcia-hermes-qualification-b') and not __import__('re').fullmatch(r'arcia-user-p(?:0[1-9]|[12][0-9]|3[0-2])',namespace):
            raise ValueError('FIXED_ROUTING_NAMESPACE_REQUIRED')
        deployment=owned('Deployment','hermes-pilot',namespace,operation,True)
        if not deployment:continue
        spec=deployment['spec']['template']['spec']
        name=next(v for v in spec['volumes'] if v['name']=='config')['configMap']['name']
        result[namespace]={'deployment':deployment,'config':owned('ConfigMap',name,namespace,operation)}
    return result


if __name__=='__main__':
    print(json.dumps({'install_omniroute':install,'inspect_omniroute':inspect,'verify_omniroute':verify,
        'read_omniroute_access':access,'read_omniroute_network':network_policy,
        'read_omniroute_public_ip_certificate':public_ip_certificate,'read_omniroute_runtime_bindings':read_bindings}[ARCIA_INPUT['action']](ARCIA_INPUT)))
