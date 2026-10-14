"""Private OmniRoute management portal; no public ingress or arbitrary PodSpec."""
import hashlib
import ipaddress
import json
from pathlib import Path
import sys
import kubernetes_apps
import http.client
import socket
import ssl

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'services/routing'))
from policy import validate_admin_policy
NS='arcia-routing'
LAN_NS='arcia-routing-lan'
PORT=20129


def probe_lan(hostname,addresses,trusted_certificate=None):
    """No content/credential is returned; TLS validates the real SNI hostname."""
    private=[ipaddress.ip_network(c) for c in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16')]
    if len(addresses) not in (1,3) or any(not any(ipaddress.ip_address(a) in n for n in private) for a in addresses):
        raise ValueError('PRIVATE_ROUTER_PROBE_TARGET_REQUIRED')
    context=ssl.create_default_context()
    if trusted_certificate:context.load_verify_locations(cadata=trusted_certificate)
    class Connection(http.client.HTTPSConnection):
        def connect(self):
            sock=socket.create_connection((self.private_address,PORT),timeout=self.timeout)
            try:self.sock=context.wrap_socket(sock,server_hostname=hostname)
            except Exception:sock.close();raise
    checks=[]
    paths={'dashboard':('/dashboard',(200,302,303,307,308)),
           'management':('/api/keys',(401,403)),
           'inference':('/v1/chat/completions',(403,)),
           'public_proxy':('/api/settings/proxy/cloudflare-deploy',(403,)),
           'cloud_sync':('/api/cloud/auth',(403,))}
    for address in addresses:
        node={}
        for name,(path,allowed) in paths.items():
            connection=Connection(hostname,PORT,timeout=12,context=context);connection.private_address=address
            try:
                connection.request('GET',path)
                response=connection.getresponse()
                node[name]=response.status in allowed
                # Do not read HTML, provider metadata or any response body.
            except (OSError,http.client.HTTPException):node[name]=False
            finally:connection.close()
        checks.append(node)
    return {'passed':all(all(c.values()) for c in checks),'tls_dashboard_nodes_verified':sum(c['dashboard'] for c in checks),
        'lan_management_denied_nodes':sum(c['management'] for c in checks),
        'lan_inference_denied_nodes':sum(c['inference'] for c in checks),
        'public_proxy_and_sync_denied_nodes':sum(c['public_proxy'] and c['cloud_sync'] for c in checks),
        'tls_validation_bypassed':False,'model_call_executed':False}


def payload(lock,config,lan_cidrs,private_firewall_boundary=False,ip_https_vip=None):
    policy=validate_admin_policy({'automatic_mode':'auto/smart','lan_cidrs':lan_cidrs,
        'personal_providers_enabled':False,'personal_role':'ArcIA.ProviderSelfService',
        'private_firewall_boundary':private_firewall_boundary,'ip_https_enabled':bool(ip_https_vip)})
    if ip_https_vip:
        vip=ipaddress.ip_address(ip_https_vip)
        if vip.version!=4 or not any(vip in ipaddress.ip_network(c) for c in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16')):
            raise ValueError('PRIVATE_ROUTING_VIP_REQUIRED')
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
    ns=kubernetes_apps.namespace(NS)
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
    proxy=f'''{allows}
    deny all;
    client_max_body_size 1m;
    location ~ ^/api/(cloud|tunnel)(/|$) {{ return 403; }}
    location ~ ^/api/settings/proxy/(cloudflare|deno|vercel)-deploy(/|$) {{ return 403; }}
    location ~ ^/(v1|api/(chat|playground|messages|responses|translator|batches|files|images|audio|video|combos/test))(/|$) {{ return 403; }}
    location / {{ proxy_pass http://omniroute.arcia-routing.svc.cluster.local:20128;
      proxy_set_header Host $http_host; proxy_set_header X-Forwarded-Host $http_host;
      proxy_set_header X-Forwarded-Port 20129; proxy_set_header X-Forwarded-Proto https;
      proxy_set_header X-Forwarded-For $remote_addr; proxy_set_header X-Real-IP $remote_addr;
      proxy_buffering off; }}'''
    default_server='server { listen 8443 ssl default_server; ssl_reject_handshake on; }'
    if ip_https_vip:
        default_server=f'''server {{ listen 8443 ssl default_server; server_name {ip_https_vip};
    ssl_certificate /ip-tls/tls.crt; ssl_certificate_key /ip-tls/tls.key;
    if ($host != "{ip_https_vip}") {{ return 444; }}
    {proxy}
  }}'''
    nginx=f'''pid /tmp/nginx.pid;
error_log /dev/stderr warn;
events {{ worker_connections 256; }}
http {{
  client_body_temp_path /tmp/client; proxy_temp_path /tmp/proxy;
  fastcgi_temp_path /tmp/fastcgi; uwsgi_temp_path /tmp/uwsgi; scgi_temp_path /tmp/scgi;
  access_log off; error_log /dev/stderr warn;
  {default_server}
  server {{ listen 8443 ssl; server_name {hostname};
    ssl_certificate /tls/tls.crt; ssl_certificate_key /tls/tls.key;
    {proxy}
  }}
}}
'''
    def lan_resource(kind,name,spec=None,**extra):
        doc=resource(kind,name,spec,**extra);doc['metadata']['namespace']=LAN_NS;return doc
    # PSA baseline also forbids hostPort. Isolate the ingress exception from
    # the restricted application namespace; every container stays non-root.
    nginx_hash=hashlib.sha256(nginx.encode()).hexdigest()
    nginx_name='routing-nginx-'+nginx_hash[:12]
    docs.extend([kubernetes_apps.namespace(LAN_NS,privileged=True),
        lan_resource('NetworkPolicy','deny-all',{'podSelector':{},'policyTypes':['Ingress','Egress']}),
        lan_resource('ResourceQuota','lan-bounds',{'hard':{'pods':'4','requests.cpu':'250m','requests.memory':'320Mi',
            'limits.cpu':'1','limits.memory':'1280Mi'}}),
        lan_resource('ConfigMap',nginx_name,immutable=True,data={'nginx.conf':nginx}),
        resource('NetworkPolicy','installer-public-only',{'podSelector':{'matchLabels':{'app':'routing-installer'}},'policyTypes':['Egress'],'egress':[dns,public]}),
        resource('NetworkPolicy','omniroute-controlled',{'podSelector':{'matchLabels':{'app':'omniroute'}},'policyTypes':['Ingress','Egress'],
            'ingress':[{'from':[{'namespaceSelector':{'matchLabels':{'kubernetes.io/metadata.name':LAN_NS}},'podSelector':{'matchLabels':{'app':'routing-lan'}}},{'namespaceSelector':{'matchLabels':{'kubernetes.io/metadata.name':'arcia-privacy'}},
                'podSelector':{'matchLabels':{'app':'cloud-egress'}}}],'ports':[{'port':20128,'protocol':'TCP'}]}],'egress':[dns,public]}),
        lan_resource('NetworkPolicy','lan-only',{'podSelector':{'matchLabels':{'app':'routing-lan'}},'policyTypes':['Ingress','Egress'],
            'ingress':[{'from':[{'ipBlock':{'cidr':c}} for c in lan_cidrs],'ports':[{'port':8443,'protocol':'TCP'}]}],
            'egress':[dns,{'to':[{'namespaceSelector':{'matchLabels':{'kubernetes.io/metadata.name':NS}},'podSelector':{'matchLabels':{'app':'omniroute'}}}],'ports':[{'port':20128,'protocol':'TCP'}]}]})])
    lan=lan_resource('DaemonSet','routing-lan',{'selector':{'matchLabels':{'app':'routing-lan'}},'template':{'metadata':{'labels':{'app':'routing-lan'},
        'annotations':{'arcia.io/config-sha256':nginx_hash}},'spec':{
        'automountServiceAccountToken':False,'securityContext':{**context,'runAsUser':101,'runAsGroup':101,'fsGroup':101},
        'containers':[{'name':'https','image':lock['components']['ingress']['image'],'command':['nginx'],
            'args':['-g','daemon off;','-c','/etc/nginx/nginx.conf'],'securityContext':security,
            'ports':[{'containerPort':8443,'hostPort':PORT}],
            'startupProbe':{'tcpSocket':{'port':8443},'failureThreshold':24,'periodSeconds':5},
            'readinessProbe':{'tcpSocket':{'port':8443},'periodSeconds':5},
            'resources':{'requests':{'cpu':'50m','memory':'64Mi'},'limits':{'cpu':'200m','memory':'256Mi'}},
            'volumeMounts':[{'name':'config','mountPath':'/etc/nginx/nginx.conf','subPath':'nginx.conf','readOnly':True},
                {'name':'tls','mountPath':'/tls','readOnly':True},{'name':'tmp','mountPath':'/tmp'}]}],
        'volumes':[{'name':'config','configMap':{'name':nginx_name}},{'name':'tls','secret':{'secretName':'routing-tls','defaultMode':288}},
            {'name':'tmp','emptyDir':{'sizeLimit':'64Mi'}}]}}})
    if ip_https_vip:
        lan_pod=lan['spec']['template']['spec']
        lan_pod['volumes'].append({'name':'ip-tls','secret':{'secretName':'routing-ip-tls','defaultMode':288}})
        lan_pod['containers'][0]['volumeMounts'].append({'name':'ip-tls','mountPath':'/ip-tls','readOnly':True})
    return {'documents':docs,'job':job,'deployment':deployment,'lan':lan,'runtime':runtime,'policy':policy,'digest':digest}
