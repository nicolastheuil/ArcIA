"""Private OmniRoute management portal; no public ingress or arbitrary PodSpec."""
import hashlib
import ipaddress
import json
from pathlib import Path
import sys
import kubernetes_apps

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'services/routing'))
from policy import validate_admin_policy
NS='arcia-routing'
PORT=20129


def payload(lock,config,lan_cidrs):
    policy=validate_admin_policy({'automatic_mode':'auto/smart','lan_cidrs':lan_cidrs,
        'personal_providers_enabled':False,'personal_role':'ArcIA.ProviderSelfService'})
    hostname=config['network']['public_hostname']
    if not all(c.isalnum() or c in '.-' for c in hostname):raise ValueError('ROUTING_HOST_INVALID')
    package=json.loads((ROOT/'builder/npm/package-lock.json').read_text())['packages']['node_modules/omniroute']
    runtime={'version':package['version'],'url':package['resolved'],'integrity':package['integrity']}
    source=(ROOT/'services/routing/install.py').read_text(encoding='utf-8')
    npm={name:(ROOT/'builder/npm'/name).read_text(encoding='utf-8') for name in ('package.json','package-lock.json')}
    digest=hashlib.sha256((source+json.dumps(runtime,sort_keys=True)+json.dumps(npm,sort_keys=True)).encode()).hexdigest()
    docs=[]
    def resource(kind,name,spec=None,**extra):
        d={'apiVersion':'networking.k8s.io/v1' if kind=='NetworkPolicy' else ('apps/v1' if kind in ('Deployment','DaemonSet') else 'v1'),
           'kind':kind,'metadata':{'name':name,'namespace':NS},**extra}
        if spec is not None:d['spec']=spec
        return d
    security={'allowPrivilegeEscalation':False,'readOnlyRootFilesystem':True,'capabilities':{'drop':['ALL']}}
    context={'runAsNonRoot':True,'runAsUser':10000,'runAsGroup':10000,'fsGroup':10000,'seccompProfile':{'type':'RuntimeDefault'}}
    image=lock['components']['hermes']['image']
    dns={'to':[{'namespaceSelector':{'matchLabels':{'kubernetes.io/metadata.name':'kube-system'}},'podSelector':{'matchLabels':{'k8s-app':'kube-dns'}}}],
         'ports':[{'port':53,'protocol':p} for p in ('TCP','UDP')]}
    public={'to':[{'ipBlock':{'cidr':'0.0.0.0/0','except':['0.0.0.0/8','10.0.0.0/8','100.64.0.0/10','127.0.0.0/8','169.254.0.0/16',
            '172.16.0.0/12','192.168.0.0/16','224.0.0.0/4','240.0.0.0/4']}}],'ports':[{'port':443,'protocol':'TCP'}]}
    # hostPort needs the same narrow PSA exception as the existing HTTPS ingress.
    ns=kubernetes_apps.namespace(NS);ns['metadata']['labels']['pod-security.kubernetes.io/enforce']='baseline'
    docs.extend([ns,resource('NetworkPolicy','deny-all',{'podSelector':{},'policyTypes':['Ingress','Egress']}),
        resource('ResourceQuota','routing-bounds',{'hard':{'pods':'5','requests.cpu':'2','requests.memory':'3Gi','limits.cpu':'5','limits.memory':'7Gi',
            'persistentvolumeclaims':'2','requests.storage':'10Gi'}}),
        resource('ConfigMap','routing-install',data={'install.py':source,'runtime.json':json.dumps(runtime),**npm}),
        resource('ConfigMap','routing-policy',data={'policy.json':json.dumps(policy,sort_keys=True)}),
        resource('Service','omniroute',{'selector':{'app':'omniroute'},'ports':[{'port':20128,'targetPort':20128}]})])
    for name,size in [('routing-runtime','5Gi'),('routing-data','5Gi')]:
        docs.append(resource('PersistentVolumeClaim',name,{'accessModes':['ReadWriteOncePod'],'storageClassName':'arcia-vsphere','resources':{'requests':{'storage':size}}}))
    base={'automountServiceAccountToken':False,'securityContext':context,'restartPolicy':'Never',
          'containers':[{'name':'installer','image':image,'command':['/opt/hermes/.venv/bin/python','/input/install.py'],
              'env':[{'name':'HOME','value':'/tmp'},{'name':'NPM_CONFIG_CACHE','value':'/tmp/npm-cache'},{'name':'DISABLE_TELEMETRY','value':'1'}],
              'securityContext':security,'resources':{'requests':{'cpu':'100m','memory':'256Mi'},'limits':{'cpu':'1','memory':'2Gi'}},
              'volumeMounts':[{'name':'runtime','mountPath':'/opt/arcia-routing'},{'name':'existing-data','mountPath':'/existing-data','readOnly':True},
                  {'name':'code','mountPath':'/input','readOnly':True},
                  {'name':'tmp','mountPath':'/tmp'}]}],
          'volumes':[{'name':'runtime','persistentVolumeClaim':{'claimName':'routing-runtime'}},
              {'name':'existing-data','persistentVolumeClaim':{'claimName':'routing-data','readOnly':True}},
              {'name':'code','configMap':{'name':'routing-install'}},
              {'name':'tmp','emptyDir':{'sizeLimit':'2Gi'}}]}
    job={'apiVersion':'batch/v1','kind':'Job','metadata':{'name':'routing-install-'+digest[:12],'namespace':NS},
         'spec':{'backoffLimit':0,'activeDeadlineSeconds':1800,'template':{'metadata':{'labels':{'app':'routing-installer'}},'spec':base}}}
    env=[{'name':key,'valueFrom':{'secretKeyRef':{'name':'routing-credentials','key':key}}} for key in
         ('JWT_SECRET','API_KEY_SECRET','STORAGE_ENCRYPTION_KEY','INITIAL_PASSWORD')]
    env.extend({'name':k,'value':v} for k,v in {'PORT':'20128','HOSTNAME':'0.0.0.0','DATA_DIR':'/data',
        'ENABLE_REQUEST_LOGS':'false','DISABLE_TELEMETRY':'1','NEXT_TELEMETRY_DISABLED':'1','AUTH_COOKIE_SECURE':'true',
        'REQUIRE_API_KEY':'true',
        'OMNIROUTE_AUTO_FREE_FALLBACK_TO_FULL_POOL':'false'}.items())
    # Kubernetes service links inject OMNIROUTE_PORT=tcp://...; upstream
    # validates that name as an integer port. DNS is the explicit service path.
    pod={'automountServiceAccountToken':False,'enableServiceLinks':False,'securityContext':context,
        'initContainers':[{'name':'prepare-cache-mount','image':image,'securityContext':security,
            'command':['/opt/hermes/.venv/bin/python','-c',"from pathlib import Path;Path('/opt/arcia-routing/package/dist/.build/next/cache').mkdir(parents=True,exist_ok=True)"],
            'resources':{'requests':{'cpu':'25m','memory':'32Mi'},'limits':{'cpu':'100m','memory':'64Mi'}},
            'volumeMounts':[{'name':'runtime','mountPath':'/opt/arcia-routing'}]}],
        'containers':[{'name':'omniroute','image':image,
        'command':['/usr/local/bin/node','/opt/arcia-routing/package/dist/server.js'],'env':env,'securityContext':security,
        'resources':{'requests':{'cpu':'200m','memory':'512Mi'},'limits':{'cpu':'2','memory':'2Gi'}},'ports':[{'containerPort':20128}],
        'readinessProbe':{'tcpSocket':{'port':20128},'periodSeconds':5},'startupProbe':{'tcpSocket':{'port':20128},'periodSeconds':5,'failureThreshold':120},
        'volumeMounts':[{'name':'runtime','mountPath':'/opt/arcia-routing','readOnly':True},{'name':'data','mountPath':'/data'},
            {'name':'tmp','mountPath':'/tmp'},{'name':'cache','mountPath':'/opt/arcia-routing/package/dist/.build/next/cache'}]}],
        'volumes':[{'name':'runtime','persistentVolumeClaim':{'claimName':'routing-runtime'}},
            {'name':'data','persistentVolumeClaim':{'claimName':'routing-data'}},{'name':'tmp','emptyDir':{'sizeLimit':'512Mi'}},
            {'name':'cache','emptyDir':{'sizeLimit':'512Mi'}}]}
    deployment=resource('Deployment','omniroute',{'replicas':1,'strategy':{'type':'Recreate'},'selector':{'matchLabels':{'app':'omniroute'}},
        'template':{'metadata':{'labels':{'app':'omniroute'},'annotations':{'arcia.io/runtime-sha256':digest}},'spec':pod}})
    allows='\n'.join('allow '+cidr+';' for cidr in lan_cidrs)
    nginx=f'''pid /tmp/nginx.pid;
events {{ worker_connections 256; }}
http {{
  client_body_temp_path /tmp/client; proxy_temp_path /tmp/proxy;
  access_log off; error_log /dev/stderr warn;
  server {{ listen 8443 ssl default_server; ssl_reject_handshake on; }}
  server {{ listen 8443 ssl; server_name {hostname};
    ssl_certificate /tls/tls.crt; ssl_certificate_key /tls/tls.key;
    {allows}
    deny all;
    client_max_body_size 1m;
    location ~ ^/api/(cloud|tunnel)(/|$) {{ return 403; }}
    location ~ ^/api/settings/proxy/(cloudflare|deno|vercel)-deploy(/|$) {{ return 403; }}
    location ~ ^/(v1|api/(chat|playground|messages|responses|translator|batches|files|images|audio|video|combos/test))(/|$) {{ return 403; }}
    location / {{ proxy_pass http://omniroute:20128;
      proxy_set_header Host $host; proxy_set_header X-Forwarded-Proto https;
      proxy_set_header X-Forwarded-For $remote_addr; proxy_set_header X-Real-IP $remote_addr;
      proxy_buffering off; }}
  }}
}}
'''
    docs.extend([resource('ConfigMap','routing-nginx',data={'nginx.conf':nginx}),
        resource('NetworkPolicy','installer-public-only',{'podSelector':{'matchLabels':{'app':'routing-installer'}},'policyTypes':['Egress'],'egress':[dns,public]}),
        resource('NetworkPolicy','omniroute-controlled',{'podSelector':{'matchLabels':{'app':'omniroute'}},'policyTypes':['Ingress','Egress'],
            'ingress':[{'from':[{'podSelector':{'matchLabels':{'app':'routing-lan'}}},{'namespaceSelector':{'matchLabels':{'kubernetes.io/metadata.name':'arcia-privacy'}},
                'podSelector':{'matchLabels':{'app':'cloud-egress'}}}],'ports':[{'port':20128,'protocol':'TCP'}]}],'egress':[dns,public]}),
        resource('NetworkPolicy','lan-only',{'podSelector':{'matchLabels':{'app':'routing-lan'}},'policyTypes':['Ingress','Egress'],
            'ingress':[{'from':[{'ipBlock':{'cidr':c}} for c in lan_cidrs],'ports':[{'port':8443,'protocol':'TCP'}]}],
            'egress':[dns,{'to':[{'podSelector':{'matchLabels':{'app':'omniroute'}}}],'ports':[{'port':20128,'protocol':'TCP'}]}]})])
    lan=resource('DaemonSet','routing-lan',{'selector':{'matchLabels':{'app':'routing-lan'}},'template':{'metadata':{'labels':{'app':'routing-lan'}},'spec':{
        'automountServiceAccountToken':False,'securityContext':{**context,'runAsUser':101,'runAsGroup':101,'fsGroup':101},
        'containers':[{'name':'https','image':lock['components']['ingress']['image'],'command':['nginx'],
            'args':['-g','daemon off;','-c','/etc/nginx/nginx.conf'],'securityContext':security,
            'ports':[{'containerPort':8443,'hostPort':PORT}],
            'resources':{'requests':{'cpu':'50m','memory':'64Mi'},'limits':{'cpu':'200m','memory':'256Mi'}},
            'volumeMounts':[{'name':'config','mountPath':'/etc/nginx/nginx.conf','subPath':'nginx.conf','readOnly':True},
                {'name':'tls','mountPath':'/tls','readOnly':True},{'name':'tmp','mountPath':'/tmp'}]}],
        'volumes':[{'name':'config','configMap':{'name':'routing-nginx'}},{'name':'tls','secret':{'secretName':'routing-tls','defaultMode':288}},
            {'name':'tmp','emptyDir':{'sizeLimit':'64Mi'}}]}}})
    return {'documents':docs,'job':job,'deployment':deployment,'lan':lan,'runtime':runtime,'policy':policy,'digest':digest}
