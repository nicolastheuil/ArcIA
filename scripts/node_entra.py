"""Appended to the owned Kubernetes worker; fixed auth canary operations only."""
ENTRA_NS='arcia-entra-test'


def verify_local_admin(values):
    # No credentials in process arguments or returned diagnostics.
    listener=socket.socket();listener.bind(('127.0.0.1',0));port=listener.getsockname()[1];listener.close()
    proc=subprocess.Popen(['/usr/local/bin/k3s','kubectl','port-forward','-n',ENTRA_NS,
                           'service/hermes-pilot',str(port)+':9119','--address=127.0.0.1'],
                          stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        deadline=time.monotonic()+25
        while time.monotonic()<deadline:
            if proc.poll() is not None:return False
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=1):break
            except OSError:time.sleep(.2)
        else:return False
        headers={'Host':values['hostname'],'Origin':'https://'+values['hostname'],
                 'X-Forwarded-Proto':'https','X-Forwarded-Prefix':'/entra-test','Content-Type':'application/json'}
        body=json.dumps({'provider':'basic','username':'admin','password':values['local_admin']['password']}).encode()
        request=urllib.request.Request('http://127.0.0.1:'+str(port)+'/auth/password-login',data=body,headers=headers)
        with urllib.request.urlopen(request,timeout=15) as response:
            return response.status==200 and json.load(response).get('ok') is True
    except (OSError,ValueError):return False
    finally:
        proc.terminate()
        try:proc.wait(timeout=5)
        except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=5)


def install_entra_test(values):
    operation=values['operation_id'];docs=values['documents']
    ingress=owned('DaemonSet','pilot-https','arcia-ingress',operation)
    volume=next(v for v in ingress['spec']['template']['spec']['volumes'] if v['name']=='config')
    current_cm=owned('ConfigMap',volume['configMap']['name'],'arcia-ingress',operation)
    if set(current_cm['data'])!={'nginx.conf'}:raise ValueError('ENTRA_TEST_INGRESS_CONFIG_DRIFT')
    nginx=current_cm['data']['nginx.conf'];route=values['ingress_route']
    if 'location ^~ /entra-test/' in nginx:
        if route not in nginx:raise ValueError('ENTRA_TEST_INGRESS_ROUTE_DRIFT')
    else:
        if nginx.count('    location / {')!=1:raise ValueError('ENTRA_TEST_INGRESS_INSERTION_REQUIRED')
        nginx=nginx.replace('    location / {',route+'    location / {')
    # Reject foreign resources before any create; preserve claims and admin secrets.
    preserved={}
    for d in docs+[values['job']]:
        old=owned(d['kind'],d['metadata']['name'],d['metadata'].get('namespace'),operation,True)
        if old and d['kind']=='PersistentVolumeClaim':
            preserved[d['metadata']['name']]=(old['metadata']['uid'],old['spec'].get('volumeName'))
        if old and d['kind']=='Secret' and d['metadata']['name']=='hermes-pilot-auth':
            expected={k:base64.b64encode(v.encode()).decode() for k,v in d['stringData'].items()}
            if old.get('data')!=expected:raise ValueError('ENTRA_TEST_LOCAL_ADMIN_DRIFT')
    job=values['job']
    workloads=[d for d in docs if d['kind']=='Deployment' and d['metadata']['name'] in ('hermes-pilot','context7-docs')]
    apply([d for d in docs if d not in workloads]+[job],operation)
    kube('wait','job/'+job['metadata']['name'],'-n',ENTRA_NS,'--for=condition=complete','--timeout=1500s',timeout=1520)
    apply(workloads,operation)
    for name in ('entra-auth-egress','context7-docs','hermes-pilot'):
        kube('rollout','status','deployment/'+name,'-n',ENTRA_NS,'--timeout=300s',timeout=320)
    # Validate the exact new Nginx text in an existing proxy pod before switching.
    pod=next(p for p in json.loads(kube('get','pods','-l','app=pilot-https','-n','arcia-ingress','-o','json'))['items']
             if p.get('status',{}).get('phase')=='Running')['metadata']['name']
    # kube(document=...) encodes JSON, so pipe Nginx using subprocess input directly.
    result=subprocess.run(['/usr/local/bin/k3s','kubectl','exec','-i',pod,'-n','arcia-ingress','--','/bin/sh','-c',
        'cat > /tmp/entra-nginx.conf && nginx -t -c /tmp/entra-nginx.conf'],input=nginx.encode(),capture_output=True,timeout=30)
    if result.returncode:raise ValueError('ENTRA_TEST_INGRESS_SYNTAX_REFUSED')
    sha=hashlib.sha256(nginx.encode()).hexdigest();name='pilot-nginx-entra-'+sha[:16]
    apply([{'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':name,'namespace':'arcia-ingress'},
            'immutable':True,'data':{'nginx.conf':nginx}}],operation)
    volume['configMap']['name']=name
    kube('patch','daemonset','pilot-https','-n','arcia-ingress','--type=merge','-p',json.dumps({
        'metadata':{'resourceVersion':ingress['metadata']['resourceVersion']},'spec':{'template':ingress['spec']['template']}}))
    kube('rollout','status','daemonset/pilot-https','-n','arcia-ingress','--timeout=180s',timeout=200)
    for claim,expected in preserved.items():
        now=owned('PersistentVolumeClaim',claim,ENTRA_NS,operation)
        if (now['metadata']['uid'],now['spec'].get('volumeName'))!=expected:raise ValueError('ENTRA_TEST_VOLUME_DRIFT')
    return {'passed':True,'keycloak_deleted':False,'other_runtimes_modified':False,'native_oidc_provider':True,
            'local_admin_count_in_canary':1,'existing_canary_pvcs_preserved':True,'interactive_login_verified':False,'model_call_executed':False}


def verify_entra_test(values):
    operation=values['operation_id'];deployment=owned('Deployment','hermes-pilot',ENTRA_NS,operation)
    native_probe="""import json,urllib.request,urllib.error,os
r={}
try:
 q=urllib.request.urlopen('http://127.0.0.1:9119/api/auth/providers',timeout=15)
 p=json.load(q);items=p if isinstance(p,list) else p.get('providers',[])
 names={v.get('name',v.get('id')) for v in items}
 r['entra_advertised']='entra' in names;r['local_admin_advertised']='basic' in names
 q=urllib.request.urlopen('http://127.0.0.1:9119/api/config',timeout=15)
 r['anonymous_config_denied']=False
except urllib.error.HTTPError as e:r['anonymous_config_denied']=e.code==401
except Exception:r['probe_failed']=True
print(json.dumps(r))"""
    checks=json.loads(kube('exec','deployment/hermes-pilot','-n',ENTRA_NS,'--','/opt/hermes/.venv/bin/python','-c',native_probe,timeout=40))
    spec=deployment['spec']['template']['spec']
    checks.update(single_writer=deployment['spec']['replicas']==1 and deployment['spec']['strategy']['type']=='Recreate',
                  no_service_account=spec.get('automountServiceAccountToken') is False,
                  keycloak_still_available=bool(owned('Deployment','keycloak','arcia-identity',operation)['status'].get('availableReplicas')))
    checks['auth_only_network_policy_present']=bool(owned('NetworkPolicy','hermes-auth-only',ENTRA_NS,operation))
    checks['local_admin_login_verified']=verify_local_admin(values)
    required=('entra_advertised','local_admin_advertised','anonymous_config_denied','single_writer','no_service_account',
              'keycloak_still_available','auth_only_network_policy_present','local_admin_login_verified')
    return {'passed':all(checks.get(k) is True for k in required),
            'checks':checks,'interactive_login_verified':False,'keycloak_deleted':False,'model_call_executed':False}


if __name__=='__main__':
    print(json.dumps({'install_entra_test':install_entra_test,'verify_entra_test':verify_entra_test}[ARCIA_INPUT['action']](ARCIA_INPUT)))
