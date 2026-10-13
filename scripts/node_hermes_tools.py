"""Fixed engineer operations on the designated Hermes workload; private I/O."""
import json
import subprocess
import time
import hashlib

NS = 'arcia-hermes'
K3S = '/usr/local/bin/k3s'


def kube(*args, document=None, timeout=90):
    result = subprocess.run([K3S, 'kubectl', *args], capture_output=True,
        input=json.dumps(document).encode() if document is not None else None, timeout=timeout)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors='replace'))
    return result.stdout.decode()


def workload(values, allow_stopped=False):
    deployment = json.loads(kube('get', 'deployment', 'hermes-pilot', '-n', NS, '-o', 'json'))
    if deployment['metadata'].get('annotations', {}).get('arcia.io/operation-id') != values['operation_id']:
        raise ValueError('HERMES_OWNERSHIP_REQUIRED')
    pods = json.loads(kube('get', 'pods', '-n', NS, '-l', 'app=hermes-pilot', '-o', 'json'))['items']
    running = [p for p in pods if not p['metadata'].get('deletionTimestamp') and p['status']['phase'] == 'Running']
    if allow_stopped and not running and deployment['spec'].get('replicas')==0:
        return deployment,None
    if len(running) != 1:
        raise ValueError('SINGLE_RUNNING_HERMES_REQUIRED')
    return deployment, running[0]


def python(pod, source, timeout=90, tools=False):
    return kube('exec', pod['metadata']['name'], '-n', NS, '-c', 'hermes', '--',
        '/opt/arcia-tools/python/bin/python' if tools else '/opt/hermes/.venv/bin/python', '-c', source, timeout=timeout)


def inspect(values):
    _, pod = workload(values)
    source = """import json,sys,importlib.util,shutil,subprocess
from pathlib import Path
value={'python_version':sys.version.split()[0], 'python_executable':sys.executable,
 'node_present':bool(shutil.which('node')), 'pip_present':importlib.util.find_spec('pip') is not None,
 'mcp_present':importlib.util.find_spec('mcp') is not None,
 'installed_tools_volume':Path('/opt/arcia-tools/installed.json').is_file()}
for name in ('node','npm','uv'):
 value[name+'_path']=shutil.which(name)
 if value[name+'_path']:
  value[name+'_version']=subprocess.run([name,'--version'],capture_output=True,text=True,timeout=10).stdout.strip()
print(json.dumps(value))
"""
    result=json.loads(python(pod, source))
    if values.get('benchmark_source') and result['installed_tools_volume']:
        result['token_tools_benchmark']=json.loads(python(pod,values['benchmark_source'],timeout=180,tools=True))
    jobs=json.loads(kube('get','jobs','-n',NS,'-o','json'))['items']
    result['installer_jobs']=[{'active':j.get('status',{}).get('active',0),
        'succeeded':j.get('status',{}).get('succeeded',0),'failed':j.get('status',{}).get('failed',0)}
        for j in jobs if j['metadata']['name'].startswith('hermes-tools-install-')]
    result['installer_error_codes']=[]
    for job in jobs:
        if not job['metadata']['name'].startswith('hermes-tools-install-'):continue
        log=kube('logs','job/'+job['metadata']['name'],'-n',NS,'--tail=80',timeout=30)
        patterns={'ERESOLVE':'NPM_PEER_RESOLUTION','ENOSPC':'DISK_FULL','No space left':'DISK_FULL',
            'Permission denied':'PERMISSION_DENIED','No module named ensurepip':'ENSUREPIP_MISSING',
            'No module named venv':'VENV_MISSING','Read-only file system':'READ_ONLY_PATH',
            'No matching distribution':'WHEEL_UNAVAILABLE','Could not find a version':'PACKAGE_UNAVAILABLE',
            'Cannot find module':'NODE_MODULE_MISSING','EUSAGE':'NPM_LOCK_USAGE',
            'Invalid':'INVALID_PACKAGE_LOCK','Killed':'PROCESS_KILLED'}
        result['installer_error_codes'] += [code for text,code in patterns.items() if text.lower() in log.lower()]
    return result


def cleanup_failed(values):
    jobs=json.loads(kube('get','jobs','-n',NS,'-o','json'))['items']
    removed=0
    for job in jobs:
        if not job['metadata']['name'].startswith('hermes-tools-install-'):continue
        if job['metadata'].get('annotations',{}).get('arcia.io/operation-id')!=values['operation_id']:
            raise ValueError('FOREIGN_INSTALLER_REFUSED')
        if not any(c['type']=='Failed' and c['status']=='True' for c in job.get('status',{}).get('conditions',[])):
            raise ValueError('ONLY_FAILED_INSTALLER_CLEANUP_ALLOWED')
        kube('delete','job',job['metadata']['name'],'-n',NS,'--wait=true','--timeout=90s',timeout=100);removed+=1
    return {'passed':True,'failed_jobs_removed':removed}


def apply_owned(documents,operation):
    for doc in documents:
        doc['metadata'].setdefault('annotations',{})['arcia.io/operation-id']=operation
        existing=kube('get',doc['kind'],doc['metadata']['name'],'-n',NS,'--ignore-not-found','-o','json')
        if existing and json.loads(existing)['metadata'].get('annotations',{}).get('arcia.io/operation-id')!=operation:
            raise ValueError('FOREIGN_TOOL_RESOURCE')
    kube('apply','--server-side','--field-manager=arcia-foundation','-f','-',
        document={'apiVersion':'v1','kind':'List','items':documents})


def verify(values):
    _,pod=workload(values)
    source='ARCIA_REQUIRE_KNOWLEDGE = '+repr(values.get('require_knowledge',True))+'\n'+values['verify_source']
    result=json.loads(python(pod,source,timeout=400,tools=True))
    result['checks']['tools_catalogue_matches_current_lock']=result.get('catalog_sha256')==values['catalog_sha256']
    result['passed']=all(result['checks'].values())
    return result


def configuration(values):
    workload(values,allow_stopped=True)
    config=json.loads(kube('get','configmap','hermes-pilot-config','-n',NS,'-o','json'))
    if config['metadata'].get('annotations',{}).get('arcia.io/operation-id')!=values['operation_id']:
        raise ValueError('HERMES_CONFIG_OWNERSHIP_REQUIRED')
    return {'config':config['data']['config.yaml']}


def install(values):
    deployment,pod=workload(values,allow_stopped=True)
    installed='arcia.io/tools-sha256' in deployment['spec']['template']['metadata'].get('annotations',{})
    if installed:
        if deployment['spec']['template']['metadata']['annotations']['arcia.io/tools-sha256']==values['catalog_sha256']:
            return verify(values)
    config=json.loads(kube('get','configmap','hermes-pilot-config','-n',NS,'-o','json'))
    if config['metadata'].get('annotations',{}).get('arcia.io/operation-id')!=values['operation_id']:
        raise ValueError('HERMES_CONFIG_OWNERSHIP_REQUIRED')
    original=config['data']['config.yaml']
    if not installed and any(line.startswith(('mcp_servers:','skills:')) for line in original.splitlines()):
        raise ValueError('EXISTING_TOOLS_CONFIG_REQUIRES_EXPLICIT_MERGE')
    if hashlib.sha256(original.encode()).hexdigest()!=values['original_config_sha256']:
        raise ValueError('HERMES_CONFIG_CHANGED_DURING_PREPARATION')
    new_yaml=values['merged_config']
    # All sources are prepared and owned before the first mutation.
    apply_owned([d for d in values['documents'] if d['kind']!='Job'],values['operation_id'])
    if installed:
        kube('scale','deployment/hermes-pilot','-n',NS,'--replicas=0')
        deadline=time.monotonic()+150
        while time.monotonic()<deadline:
            if not json.loads(kube('get','pods','-n',NS,'-l','app=hermes-pilot','-o','json'))['items']:break
            time.sleep(2)
        else:raise ValueError('TOOLS_OWNER_NOT_STOPPED')
    apply_owned([d for d in values['documents'] if d['kind']=='Job'],values['operation_id'])
    job=next(d['metadata']['name'] for d in values['documents'] if d['kind']=='Job')
    try:
        deadline=time.monotonic()+1200
        while time.monotonic()<deadline:
            state=json.loads(kube('get','job',job,'-n',NS,'-o','json'))['status']
            if any(c['type']=='Failed' and c['status']=='True' for c in state.get('conditions',[])):
                raise ValueError('INSTALLER_JOB_FAILED')
            if state.get('succeeded')==1:break
            time.sleep(3)
        else:raise ValueError('INSTALLER_TIMEOUT')
    except Exception as exc:
        logs=kube('logs','job/'+job,'-n',NS,'--all-containers','--tail=60',timeout=30)
        raise RuntimeError('INSTALLER_FAILED\n'+logs) from exc
    kube('delete','job',job,'-n',NS,'--wait=true','--timeout=90s',timeout=100)
    kube('rollout','status','deployment/context7-docs','-n',NS,'--timeout=180s',timeout=200)
    kube('patch','configmap','hermes-pilot-config','-n',NS,'--field-manager=arcia-foundation','--type=merge','-p',json.dumps({'data':{'config.yaml':new_yaml}}))
    config_name='hermes-config-'+hashlib.sha256(new_yaml.encode()).hexdigest()[:16]
    apply_owned([{'apiVersion':'v1','kind':'ConfigMap','metadata':{'name':config_name,'namespace':NS},'immutable':True,'data':{'config.yaml':new_yaml}}],values['operation_id'])
    spec=deployment['spec']['template']['spec']
    next(v for v in spec['volumes'] if v['name']=='config')['configMap']['name']=config_name
    container=next(c for c in spec['containers'] if c['name']=='hermes')
    plugin_mount={'name':'tools','mountPath':'/opt/data/plugins/arcia-platform','subPath':'plugins/arcia-platform','readOnly':True}
    if not any(m['mountPath']==plugin_mount['mountPath'] for m in container['volumeMounts']):
        container['volumeMounts'].append(plugin_mount)
    if not installed:
        container['volumeMounts'].append({'name':'tools','mountPath':'/opt/arcia-tools','readOnly':True})
        spec['volumes'].append({'name':'tools','persistentVolumeClaim':{'claimName':'hermes-tools','readOnly':True}})
    container['env']=[e for e in container['env'] if e['name'] not in ('PATH','RTK_TELEMETRY_DISABLED')]
    container['env'].append({'name':'PATH','value':'/opt/arcia-tools/bin:/opt/arcia-tools/python/bin:/opt/hermes/.venv/bin:/usr/local/bin:/usr/bin:/bin'})
    container['env'].append({'name':'RTK_TELEMETRY_DISABLED','value':'1'})
    annotations=deployment['spec']['template']['metadata'].setdefault('annotations',{})
    annotations['arcia.io/tools-sha256']=values['catalog_sha256']
    annotations['arcia.io/config-sha256']=hashlib.sha256(new_yaml.encode()).hexdigest()
    kube('patch','deployment','hermes-pilot','-n',NS,'--field-manager=arcia-foundation','--type=merge','-p',json.dumps({'spec':{'replicas':1,'template':deployment['spec']['template']}}))
    kube('rollout','status','deployment/hermes-pilot','-n',NS,'--timeout=600s',timeout=620)
    return verify(values)


if __name__ == '__main__':
    print(json.dumps({'prepare_hermes_tools_config':configuration,'inspect_hermes_tools': inspect,'install_hermes_tools':install,'verify_hermes_tools':verify,'cleanup_failed_hermes_tools':cleanup_failed}[ARCIA_INPUT['action']](ARCIA_INPUT)))
