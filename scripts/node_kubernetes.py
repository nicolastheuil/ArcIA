"""Fixed administrative Kubernetes actions. Private input/output, strict SSH only."""
import json
import subprocess
from pathlib import Path
import re
import time
import uuid
import datetime
import hashlib
import http.client
import socket
import ssl

K3S = '/usr/local/bin/k3s'


def kubectl(*args, document=None, timeout=90):
    result = subprocess.run([K3S, 'kubectl', *args],
        input=json.dumps(document).encode() if document is not None else None,
        capture_output=True, timeout=timeout)
    if result.returncode:
        # This exception is encrypted by the engineer wrapper, never forwarded.
        raise RuntimeError(result.stderr.decode(errors='replace'))
    return result.stdout.decode()


def get(resource, namespace=None):
    args = ['get', resource, '-o', 'json']
    if namespace: args += ['-n', namespace]
    return json.loads(kubectl(*args))


def inspect(values):
    nodes = get('nodes')['items']
    expected = set(values['nodes'])
    if {n['metadata']['name'] for n in nodes} != expected:
        raise ValueError('KUBERNETES_NODE_SCOPE_MISMATCH')
    ready = kubectl('get', '--raw=/readyz').strip() == 'ok'
    vip_ready = kubectl('--server=https://'+values['api_endpoint']+':6443',
                        'get', '--raw=/readyz').strip() == 'ok'
    encryption = subprocess.run([K3S, 'secrets-encrypt', 'status'], capture_output=True,
                                timeout=30, check=True).stdout.decode()
    pods = json.loads(kubectl('get', 'pods', '-A', '-o', 'json'))['items']
    return {'ready': ready, 'vip_ready': vip_ready,
        'encryption_enabled': bool(re.search(r'Encryption Status:\s+Enabled', encryption)),
        'encryption_hashes_match': 'hashes match' in encryption.casefold(),
        'nodes': [{'name': n['metadata']['name'],
            'ready': any(c['type']=='Ready' and c['status']=='True' for c in n['status']['conditions']),
            'version': n['status']['nodeInfo']['kubeletVersion'],
            'provider_id_present': n['spec'].get('providerID','').startswith('vsphere://'),
            'uninitialized': any(t['key']=='node.cloudprovider.kubernetes.io/uninitialized' for t in n['spec'].get('taints',[])),
            'control_plane': 'node-role.kubernetes.io/control-plane' in n['metadata']['labels'],
            'etcd': 'node-role.kubernetes.io/etcd' in n['metadata']['labels']}
            for n in nodes],
        'pod_count': len(pods),
        'ready_pod_count': sum(any(c['type']=='Ready' and c['status']=='True' for c in p.get('status',{}).get('conditions',[])) for p in pods),
        'pending_pod_count': sum(p.get('status',{}).get('phase')=='Pending' for p in pods),
        'storage_classes': get('storageclasses')['items']}


def install_vmware(values):
    operation=str(uuid.UUID(values['operation_id']))
    documents=values['documents']
    # Check ownership of every target before the first mutation. Secrets are
    # never returned and server-side apply avoids a plaintext last-applied copy.
    apply_owned(documents,operation)
    results=[]
    for namespace,resource in [('kube-system','daemonset/vsphere-cloud-controller-manager'),
        ('vmware-system-csi','deployment/vsphere-csi-controller'),('vmware-system-csi','daemonset/vsphere-csi-node')]:
        try:
            kubectl('rollout','status',resource,'-n',namespace,'--timeout=180s',timeout=200)
            results.append(True)
        except RuntimeError: results.append(False)
    result=vmware_state(values)
    result['rollouts']=results
    return result


def vmware_state(values):
    result=inspect(values)
    result['workloads']=[]
    result['diagnostics']=[]
    for namespace in ('kube-system','vmware-system-csi'):
        pods=get('pods',namespace)['items']
        result['workloads']+=pods
        for pod in pods:
            for container in pod['spec']['containers']:
                if 'vsphere' not in container['name']: continue
                try: log=kubectl('logs',pod['metadata']['name'],'-n',namespace,'-c',container['name'],'--tail=40',timeout=15)
                except RuntimeError: log=''
                result['diagnostics'].append({'container':container['name'],'log':log})
    if kubectl('get','namespace','arcia-storage-qualification','--ignore-not-found','-o','json'):
        result['storage_diagnostics']={'pods':get('pods','arcia-storage-qualification'),
            'events':get('events','arcia-storage-qualification'),'pvcs':get('pvc','arcia-storage-qualification')}
        for pod in result['storage_diagnostics']['pods']['items']:
            try: result['diagnostics'].append({'container':'proof','log':kubectl('logs',pod['metadata']['name'],'-n','arcia-storage-qualification','--tail=10',timeout=15)})
            except RuntimeError: pass
    return result


def apply_owned(documents, operation):
    empty_classes=[]
    for doc in documents:
        doc['metadata'].setdefault('annotations',{})['arcia.io/operation-id']=operation
        args=['get',doc['kind'],doc['metadata']['name'],'--ignore-not-found','-o','json']
        if doc['metadata'].get('namespace'): args+=['-n',doc['metadata']['namespace']]
        existing=kubectl(*args)
        if existing:
            current=json.loads(existing)
            if current['metadata'].get('annotations',{}).get('arcia.io/operation-id')!=operation:
                raise ValueError('FOREIGN_KUBERNETES_RESOURCE')
            if doc['kind']=='StorageClass' and current.get('parameters')!=doc.get('parameters'):
                name=doc['metadata']['name']
                if name not in ('arcia-vsphere','arcia-vsphere-qualification') or any(
                    pv['spec'].get('storageClassName')==name for pv in get('pv')['items']):
                    raise ValueError('STORAGECLASS_MIGRATION_WITH_VOLUMES_REFUSED')
                empty_classes.append(name)
    # Immutable SC corrections are permitted only for owned, empty classes.
    for name in empty_classes: kubectl('delete','storageclass',name,'--wait=true')
    kubectl('apply','--server-side','--field-manager=arcia-foundation','-f','-',
        document={'apiVersion':'v1','kind':'List','items':documents})


def storage_pod(name, hostname, image, marker, write=False):
    command=('printf %s '+marker+' > /data/proof; sync;' if write else 'test "$(cat /data/proof)" = '+marker+' || exit 9;')+' sleep 600'
    return {'apiVersion':'v1','kind':'Pod','metadata':{'name':name,'namespace':'arcia-storage-qualification'},
        'spec':{'automountServiceAccountToken':False,'restartPolicy':'Never',
            'securityContext':{'runAsNonRoot':True,'runAsUser':1000,'runAsGroup':1000,'fsGroup':1000,
                'seccompProfile':{'type':'RuntimeDefault'}},
            'nodeSelector':{'kubernetes.io/hostname':hostname},
            'containers':[{'name':'proof','image':image,'command':['sh','-c',command],
                'resources':{'requests':{'cpu':'10m','memory':'16Mi'},'limits':{'cpu':'100m','memory':'32Mi'}},
                'securityContext':{'allowPrivilegeEscalation':False,'readOnlyRootFilesystem':True,'capabilities':{'drop':['ALL']}},
                'volumeMounts':[{'name':'data','mountPath':'/data'}]}],
            'volumes':[{'name':'data','persistentVolumeClaim':{'claimName':'rwop-proof'}}]}}


def qualify_storage(values):
    operation=str(uuid.UUID(values['operation_id']))
    namespace='arcia-storage-qualification'
    marker='arcia-synthetic-'+operation
    image=values['image']
    if not re.fullmatch(r'registry.k8s.io/e2e-test-images/busybox@sha256:[a-f0-9]{64}',image):
        raise ValueError('PINNED_QUALIFICATION_IMAGE_REQUIRED')
    health=inspect(values)
    if not all(n['provider_id_present'] and not n['uninitialized'] for n in health['nodes']):
        raise ValueError('VMWARE_INITIALIZED_NODES_REQUIRED')
    production=json.loads(kubectl('get','storageclass','arcia-vsphere','-o','json'))
    if production['metadata'].get('annotations',{}).get('arcia.io/operation-id')!=operation:
        raise ValueError('OWNED_STORAGECLASS_REQUIRED')
    sc={'apiVersion':'storage.k8s.io/v1','kind':'StorageClass','metadata':{'name':'arcia-vsphere-qualification'},
        'provisioner':production['provisioner'],'parameters':production['parameters'],
        'reclaimPolicy':'Delete','volumeBindingMode':'WaitForFirstConsumer'}
    ns={'apiVersion':'v1','kind':'Namespace','metadata':{'name':namespace,
        'labels':{'pod-security.kubernetes.io/enforce':'restricted'}}}
    policy={'apiVersion':'networking.k8s.io/v1','kind':'NetworkPolicy','metadata':{'name':'deny-all','namespace':namespace},
        'spec':{'podSelector':{},'policyTypes':['Ingress','Egress']}}
    pvc={'apiVersion':'v1','kind':'PersistentVolumeClaim','metadata':{'name':'rwop-proof','namespace':namespace},
        'spec':{'accessModes':['ReadWriteOncePod'],'storageClassName':sc['metadata']['name'],
            'resources':{'requests':{'storage':'1Gi'}}}}
    apply_owned([ns,sc],operation)
    previous=kubectl('get','pvc','rwop-proof','-n',namespace,'--ignore-not-found','-o','json')
    if previous:
        previous=json.loads(previous)
        if previous['metadata'].get('annotations',{}).get('arcia.io/operation-id')!=operation:
            raise ValueError('FOREIGN_QUALIFICATION_PVC')
        if not previous['spec'].get('volumeName'):
            for name in ('writer','reader','contender'):
                kubectl('delete','pod',name,'-n',namespace,'--ignore-not-found','--wait=true','--timeout=90s',timeout=100)
            kubectl('delete','pvc','rwop-proof','-n',namespace,'--wait=true','--timeout=90s',timeout=100)
    apply_owned([policy,pvc],operation)
    checks={}
    volume=None
    def delete_pod(name):
        kubectl('delete','pod',name,'-n',namespace,'--ignore-not-found','--wait=true','--timeout=90s',timeout=100)
    def ready_pod(name, hostname, write=False):
        delete_pod(name)
        apply_owned([storage_pod(name,hostname,image,marker,write)],operation)
        kubectl('wait','pod/'+name,'-n',namespace,'--for=condition=Ready','--timeout=180s',timeout=200)
        proof=kubectl('exec',name,'-n',namespace,'--','cat','/data/proof').strip()
        if proof!=marker: raise ValueError('STORAGE_CONTENT_MISMATCH')
    try:
        ready_pod('writer',values['nodes'][0],True)
        volume=json.loads(kubectl('get','pvc','rwop-proof','-n',namespace,'-o','json'))['spec']['volumeName']
        checks['provision_write_read']=True
        delete_pod('contender')
        apply_owned([storage_pod('contender',values['nodes'][0],image,marker)],operation)
        deadline=time.monotonic()+40
        while time.monotonic()<deadline:
            contender=json.loads(kubectl('get','pod','contender','-n',namespace,'-o','json'))
            events=json.loads(kubectl('get','events','-n',namespace,'--field-selector=involvedObject.name=contender','-o','json'))
            if contender.get('status',{}).get('phase')=='Running': raise ValueError('RWOP_DOUBLE_WRITER')
            messages=' '.join(e.get('message','') for e in events['items'])
            if 'ReadWriteOncePod' in messages or 'already in use' in messages:
                checks['second_writer_refused']=True;break
            time.sleep(2)
        if not checks.get('second_writer_refused'): raise ValueError('RWOP_REFUSAL_NOT_PROVEN')
        delete_pod('contender');delete_pod('writer')
        ready_pod('reader',values['nodes'][0])
        checks['pod_recreation_persistence']=True
        delete_pod('reader')
        ready_pod('reader',values['nodes'][1])
        checks['cross_node_persistence']=True
        delete_pod('reader')
        kubectl('delete','pvc','rwop-proof','-n',namespace,'--wait=true','--timeout=90s',timeout=100)
        kubectl('wait','pv/'+volume,'--for=delete','--timeout=180s',timeout=200)
        checks['synthetic_volume_deleted']=True
    except Exception as exc:
        # Retain detailed diagnosis privately, including events, never in safe output.
        return {'checks':checks,'failure':str(exc),'pods':get('pods',namespace),
                'events':get('events',namespace),'pvcs':get('pvc',namespace)}
    finally:
        for name in ('writer','reader','contender'):
            try: delete_pod(name)
            except Exception: pass
    return {'checks':checks,'abrupt_node_fencing_qualified':False,'rwx_qualified':False}


def app_state(values):
    result={'pods':[],'events':[],'logs':[]}
    for namespace in ('cnpg-system','arcia-data','arcia-hermes','arcia-ingress'):
        if not kubectl('get','namespace',namespace,'--ignore-not-found','-o','json'): continue
        pods=get('pods',namespace)['items']
        result['pods']+=pods
        result['events']+=get('events',namespace)['items']
        for pod in pods:
            for container in pod['spec']['containers']:
                try: log=kubectl('logs',pod['metadata']['name'],'-n',namespace,'-c',container['name'],'--tail=25',timeout=15)
                except RuntimeError: log=''
                result['logs'].append({'namespace':namespace,'container':container['name'],'log':log})
    if kubectl('get','crd','clusters.postgresql.cnpg.io','--ignore-not-found','-o','json'):
        cluster=kubectl('get','cluster.postgresql.cnpg.io','arcia-postgres','-n','arcia-data','--ignore-not-found','-o','json')
        result['postgres']=json.loads(cluster) if cluster else None
    return result


def install_postgres(values):
    apply_owned(values['operator'],values['operation_id'])
    kubectl('wait','crd/clusters.postgresql.cnpg.io','--for=condition=Established','--timeout=90s',timeout=100)
    kubectl('rollout','status','deployment/cnpg-controller-manager','-n','cnpg-system','--timeout=180s',timeout=200)
    apply_owned(values['database'],values['operation_id'])
    try:
        kubectl('wait','cluster.postgresql.cnpg.io/arcia-postgres','-n','arcia-data','--for=condition=Ready','--timeout=600s',timeout=620)
        ready=True
    except RuntimeError: ready=False
    result=app_state(values);result['ready']=ready
    return result


def install_hermes(values):
    desired=next((d for d in values.get('hermes',[]) if d['kind']=='Deployment' and d['metadata']['name']=='hermes-pilot'),None)
    if desired and desired['spec']['template']['metadata'].get('annotations',{}).get('arcia.io/privacy-boundary')=='required':
        dns=owned('Service','private-dns','arcia-privacy',values['operation_id'])['spec']['clusterIP']
        desired['spec']['template']['spec'].update(dnsPolicy='None',dnsConfig={'nameservers':[dns],
            'searches':['arcia-hermes.svc.cluster.local','svc.cluster.local','cluster.local'],'options':[{'name':'ndots','value':'1'}]})
    # Reconcile the two resources patched by the first tools installer. This
    # narrow migration is restricted to our operation and a verified catalog;
    # normal application continues without force-conflicts for every other object.
    current=kubectl('get','deployment','hermes-pilot','-n','arcia-hermes','--ignore-not-found','-o','json')
    if current:
        current=json.loads(current)
        if current['metadata'].get('annotations',{}).get('arcia.io/operation-id')!=values['operation_id']:
            raise ValueError('FOREIGN_HERMES_DEPLOYMENT')
        if values.get('bootstrap_base'):
            # Never downgrade an existing instance or remove tools/MCP on resume.
            kubectl('rollout','status','deployment/hermes-pilot','-n','arcia-hermes','--timeout=600s',timeout=620)
            return {'pods':[], 'ready':True, 'existing_hermes_preserved':True}
        desired=next(d for d in values['hermes'] if d['kind']=='Deployment' and d['metadata']['name']=='hermes-pilot')
        old_hash=current['spec']['template']['metadata'].get('annotations',{}).get('arcia.io/tools-sha256')
        new_hash=desired['spec']['template']['metadata'].get('annotations',{}).get('arcia.io/tools-sha256')
        if old_hash and old_hash!=new_hash:raise ValueError('TOOLS_CATALOG_REINSTALL_REQUIRED')
        if old_hash:
            for kind,name in [('ConfigMap','hermes-pilot-config'),('Deployment','hermes-pilot')]:
                existing=owned(kind,name,'arcia-hermes',values['operation_id'])
                existing=json.loads(kubectl('get',kind,name,'-n','arcia-hermes','--show-managed-fields=true','-o','json'))
                if any(m['manager']=='kubectl-patch' for m in existing['metadata'].get('managedFields',[])):
                    doc=next(d for d in values['hermes'] if d['kind']==kind and d['metadata']['name']==name)
                    doc['metadata'].setdefault('annotations',{})['arcia.io/operation-id']=values['operation_id']
                    kubectl('apply','--server-side','--force-conflicts','--field-manager=arcia-foundation','-f','-',document=doc)
    apply_owned(values['hermes'],values['operation_id'])
    try:
        kubectl('rollout','status','deployment/hermes-pilot','-n','arcia-hermes','--timeout=600s',timeout=620)
        ready=True
    except RuntimeError: ready=False
    if ready:
        apply_owned(values['ingress'],values['operation_id'])
        try:
            kubectl('rollout','status','daemonset/pilot-https','-n','arcia-ingress','--timeout=180s',timeout=200)
        except RuntimeError: ready=False
    result=app_state(values);result['ready']=ready
    return result


def owned(kind, name, namespace, operation):
    obj=json.loads(kubectl('get',kind,name,'-n',namespace,'-o','json'))
    if obj['metadata'].get('annotations',{}).get('arcia.io/operation-id')!=operation:
        raise ValueError('FOREIGN_QUALIFICATION_RESOURCE')
    return obj


def probe_live_endpoints(values):
    api=kubectl('--server=https://'+values['api_endpoint']+':6443','get','--raw=/readyz').strip()=='ok'
    pem=re.search(r'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----',values['certificate'],re.S).group()
    expected=hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem)).digest()
    context=ssl.create_default_context(cadata=values['certificate'])
    connection=http.client.HTTPSConnection(values['hostname'],context=context,timeout=10)
    connection._create_connection=lambda dest,timeout,source_address=None: socket.create_connection((values['https_ip'],443),timeout)
    try:
        connection.connect()
        pinned=hashlib.sha256(connection.sock.getpeercert(binary_form=True)).digest()==expected
        connection.request('GET','/api/health')
        response=connection.getresponse();healthy=response.status==200;response.read()
    finally: connection.close()
    return {'api_ready':api,'https_ready':healthy and pinned}


def qualify_apps(values):
    """Synthetic only: controlled PG switchover, Hermes persistence and isolation."""
    operation=str(uuid.UUID(values['operation_id']))
    checks={}
    ns='arcia-data';name='arcia-postgres'
    def cluster(): return owned('cluster.postgresql.cnpg.io',name,ns,operation)
    def sql(pod,query):
        return kubectl('exec',pod,'-n',ns,'-c','postgres','--','psql','-X','-v','ON_ERROR_STOP=1',
            '-U','postgres','-d','arcia','-tAc',query,timeout=90).strip()
    initial=cluster()
    if initial['status'].get('readyInstances')!=3: raise ValueError('THREE_READY_DATABASE_INSTANCES_REQUIRED')
    pods=[p for p in get('pods',ns)['items'] if p['metadata'].get('labels',{}).get('cnpg.io/cluster')==name
          and p['status'].get('phase')=='Running']
    checks['postgres_three_distinct_nodes']=len(pods)==3 and len({p['spec']['nodeName'] for p in pods})==3
    primary=initial['status']['currentPrimary']
    replicas=[p['metadata']['name'] for p in pods if p['metadata']['name']!=primary]
    marker='synthetic-'+operation
    # A dedicated schema and operation key never touch application/customer rows.
    sql(primary,"CREATE SCHEMA IF NOT EXISTS arcia_qualification; CREATE TABLE IF NOT EXISTS arcia_qualification.canary (operation_id text PRIMARY KEY, marker text NOT NULL); INSERT INTO arcia_qualification.canary VALUES ('"+operation+"','"+marker+"') ON CONFLICT (operation_id) DO UPDATE SET marker=EXCLUDED.marker;")
    query="SELECT marker FROM arcia_qualification.canary WHERE operation_id='"+operation+"';"
    checks['postgres_pgvector_query']=sql(primary,"SELECT '[1,2]'::vector <-> '[1,2]'::vector;")=='0'
    checks['postgres_synchronous_replica']=int(sql(primary,"SELECT count(*) FROM pg_stat_replication WHERE state='streaming' AND sync_state IN ('sync','quorum');"))>=1
    deadline=time.monotonic()+60
    while time.monotonic()<deadline:
        if all(sql(p,query)==marker for p in replicas): checks['postgres_replica_canary']=True;break
        time.sleep(2)
    if not checks.get('postgres_replica_canary'): raise ValueError('REPLICA_CANARY_NOT_REPLICATED')
    # Mirror the pinned CNPG promote plugin: optimistic status patch, never pg_ctl.
    current=cluster();target=replicas[0]
    patch={'metadata':{'resourceVersion':current['metadata']['resourceVersion']},'status':{
        'targetPrimary':target,'targetPrimaryTimestamp':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'phase':'Switchover in progress','phaseReason':'Synthetic qualification switchover'}}
    kubectl('patch','cluster.postgresql.cnpg.io',name,'-n',ns,'--subresource=status','--type=merge','-p',json.dumps(patch))
    deadline=time.monotonic()+240
    while time.monotonic()<deadline:
        current=cluster()
        if current['status'].get('currentPrimary')==target and current['status'].get('readyInstances')==3:
            if sql(target,'SELECT pg_is_in_recovery();')=='f':
                checks['postgres_controlled_switchover']=True;break
        time.sleep(3)
    if not checks.get('postgres_controlled_switchover'): raise ValueError('POSTGRES_SWITCHOVER_NOT_VERIFIED')
    checks['postgres_switchover_canary_preserved']=sql(target,query)==marker
    sql(target,"DELETE FROM arcia_qualification.canary WHERE operation_id='"+operation+"';")
    ns='arcia-hermes'
    deployment=owned('deployment','hermes-pilot',ns,operation)
    if deployment['spec']['replicas']!=1 or deployment['spec']['strategy']['type']!='Recreate':
        raise ValueError('HERMES_SINGLE_OWNER_REQUIRED')
    claim=owned('pvc','hermes-pilot-state',ns,operation)
    if claim['spec']['accessModes']!=['ReadWriteOncePod']: raise ValueError('HERMES_RWOP_REQUIRED')
    def hermes_pod():
        pods=json.loads(kubectl('get','pods','-n',ns,'-l','app=hermes-pilot','-o','json'))['items']
        active=[p for p in pods if not p['metadata'].get('deletionTimestamp') and p['status'].get('phase')=='Running']
        if len(active)!=1: raise ValueError('HERMES_OWNER_NOT_UNIQUE')
        return active[0]
    def python(pod,source):
        return kubectl('exec',pod['metadata']['name'],'-n',ns,'--','/opt/hermes/.venv/bin/python','-c',source,timeout=30).strip()
    pod=hermes_pod();old_uid=pod['metadata']['uid']
    checks['hermes_native_sqlite_present']=python(pod,"from pathlib import Path;print((Path('/opt/data')/'state.db').is_file())")=='True'
    # The canary is separate from Hermes' own schema; its SQLite transaction is synthetic.
    python(pod,"import sqlite3;db=sqlite3.connect('/opt/data/arcia-qualification.db');db.execute('CREATE TABLE IF NOT EXISTS canary (marker TEXT)');db.execute('DELETE FROM canary');db.execute('INSERT INTO canary VALUES (?)',('"+marker+"',));db.commit();db.close()")
    # Reachable control target = in-cluster Postgres. A failed public target alone proves nothing.
    db_service=json.loads(kubectl('get','service','arcia-postgres-rw','-n','arcia-data','-o','json'))['spec']['clusterIP']
    probe="import socket;s=socket.socket();s.settimeout(3);print(s.connect_ex(('"+db_service+"',5432))!=0);s.close()"
    checks['hermes_cross_namespace_egress_denied']=python(pod,probe)=='True'
    dns_probe=python(pod,"import socket;socket.setdefaulttimeout(3)\ntry:\n socket.getaddrinfo('kubernetes.default.svc.cluster.local',443);print(True)\nexcept OSError: print(False)")=='True'
    if deployment['spec']['template']['metadata'].get('annotations',{}).get('arcia.io/tools-sha256'):
        checks['hermes_internal_dns_allowed']=dns_probe
    else:checks['hermes_dns_egress_denied']=not dns_probe
    kubectl('delete','pod',pod['metadata']['name'],'-n',ns,'--wait=true','--timeout=90s',timeout=100)
    kubectl('rollout','status','deployment/hermes-pilot','-n',ns,'--timeout=180s',timeout=200)
    pod=hermes_pod()
    checks['hermes_pod_recreated']=pod['metadata']['uid']!=old_uid
    checks['hermes_sqlite_persistence']=python(pod,"import sqlite3;db=sqlite3.connect('/opt/data/arcia-qualification.db');print(db.execute('SELECT marker FROM canary').fetchone()[0]=='"+marker+"');db.close()")=='True'
    python(pod,"from pathlib import Path;Path('/opt/data/arcia-qualification.db').unlink()")
    checks['hermes_single_owner_after_restart']=len(json.loads(kubectl('get','pods','-n',ns,'-l','app=hermes-pilot','-o','json'))['items'])==1
    return {'checks':checks,'abrupt_node_fencing_qualified':False,'customer_writes_replayed':False}


if __name__ == '__main__':
    actions = {'inspect_cluster': inspect,'install_vmware':install_vmware,'inspect_vmware':vmware_state,'qualify_storage':qualify_storage,
        'install_postgres':install_postgres,'install_hermes':install_hermes,'inspect_apps':app_state,'qualify_apps':qualify_apps,
        'probe_live_endpoints':probe_live_endpoints}
    print(json.dumps(actions[ARCIA_INPUT['action']](ARCIA_INPUT)))
