"""Render VMware foundation only from protected instance state and pinned sources."""
import hashlib
import json
from pathlib import Path
import socket
import ssl
import uuid
import tempfile
import yaml
from vmware_inventory import PinnedTLSContext, validate_connection

ROOT = Path(__file__).resolve().parents[1]


def certificate_endpoint(connection, certificate, private_root):
    # The engineer may have enrolled an IP while vCenter's certificate contains
    # only DNS SANs. Select an existing SAN resolving to the same designated host.
    with tempfile.NamedTemporaryFile(mode='w',suffix='.crt',dir=private_root,delete=False) as file:
        file.write(certificate)
        path=Path(file.name)
    try: decoded=ssl._ssl._test_decode_cert(str(path))
    finally: path.unlink()
    designated={item[4][0] for item in socket.getaddrinfo(connection['server'],connection['port'],type=socket.SOCK_STREAM)}
    for kind,name in decoded.get('subjectAltName',[]):
        if kind!='DNS' or '*' in name: continue
        try: addresses={item[4][0] for item in socket.getaddrinfo(name,connection['port'],type=socket.SOCK_STREAM)}
        except socket.gaierror: continue
        if designated & addresses:
            with socket.create_connection((name,connection['port']),timeout=15) as channel:
                with PinnedTLSContext(connection['certificate_sha256']).wrap_socket(channel,server_hostname=name):
                    return name
    raise ValueError('VCENTER_CERTIFICATE_DNS_ENDPOINT_REQUIRED')


def source_documents(lock):
    result=[]
    for name, source in lock['vmware_foundation']['sources'].items():
        content=(ROOT/'deploy/vendor/vmware'/name).read_bytes()
        if hashlib.sha256(content).hexdigest()!=source['rendered_sha256']:
            raise ValueError('VMWARE_SOURCE_HASH_MISMATCH')
        for doc in yaml.safe_load_all(content):
            if doc: result.extend(doc['items'] if doc['kind']=='List' else [doc])
    return result


def render(lock, operation, connection, service, datacenters, policy):
    operation=str(uuid.UUID(operation))
    if service['operation_id']!=operation or service['status']!='created_verified':
        raise ValueError('OWNED_VMWARE_SERVICE_REQUIRED')
    if lock['components']['k3s']['version'].split('.')[1]!=lock['components']['vsphere_cpi']['version'].split('.')[1]:
        raise ValueError('CPI_KUBERNETES_MINOR_MISMATCH')
    server=connection['server']
    cpi=yaml.safe_dump({'global':{'caFile':'/etc/cloud/ca.crt','insecureFlag':False},
        'vcenter':{server:{'server':server,'port':connection['port'],'user':service['username'],
            'password':service['password'],'datacenters':datacenters,'insecureFlag':False}}},sort_keys=False)
    quote=json.dumps
    csi='[Global]\ncluster-id = '+quote(operation)+'\nca-file = "/etc/cloud/ca.crt"\n\n'
    csi+='[VirtualCenter '+quote(server)+']\n'
    csi+='\n'.join(k+' = '+quote(str(v)) for k,v in {
        'user':service['username'],'password':service['password'],'port':connection['port'],
        'datacenters':','.join(datacenters)}.items())+'\ninsecure-flag = false\n'
    documents=[{'apiVersion':'v1','kind':'Namespace','metadata':{'name':'vmware-system-csi',
        'labels':{'pod-security.kubernetes.io/enforce':'privileged','pod-security.kubernetes.io/audit':'restricted',
            'pod-security.kubernetes.io/warn':'restricted'}}}]
    for namespace,name,key,value in [('kube-system','arcia-vsphere-cpi','vsphere.conf',cpi),
            ('vmware-system-csi','vsphere-config-secret','csi-vsphere.conf',csi)]:
        documents.append({'apiVersion':'v1','kind':'Secret','metadata':{'name':name,'namespace':namespace},
            'type':'Opaque','stringData':{key:value,'ca.crt':connection['certificate_pem']}})
    for doc in source_documents(lock):
        if doc['kind']=='Service' and doc['metadata']['name']=='vsphere-cloud-controller-manager':
            continue # Upstream's unused administration NodePort is not needed.
        if doc['kind']=='DaemonSet' and doc['metadata']['name']=='vsphere-cloud-controller-manager':
            spec=doc['spec']['template']['spec']
            spec['nodeSelector']={'node-role.kubernetes.io/control-plane':'true'}
            # Use Exists because K3s may encode the control-plane label as true or empty.
            spec.pop('nodeSelector')
            spec['affinity']={'nodeAffinity':{'requiredDuringSchedulingIgnoredDuringExecution':{'nodeSelectorTerms':[
                {'matchExpressions':[{'key':'node-role.kubernetes.io/control-plane','operator':'Exists'}]}]}}}
            spec['volumes'][0]={'name':'vsphere-config-volume','secret':{'secretName':'arcia-vsphere-cpi'}}
            spec['tolerations'].append({'key':'node-role.kubernetes.io/control-plane','operator':'Exists','effect':'NoSchedule'})
            spec['containers'][0]['args'].append('--leader-elect=true')
        if doc['kind']=='DaemonSet' and doc['metadata']['name']=='vsphere-csi-node':
            spec=doc['spec']['template']['spec']
            # K3s keeps kubelet state in the standard /var/lib/kubelet directory.
            spec.setdefault('tolerations',[]).append({'key':'node-role.kubernetes.io/control-plane','operator':'Exists','effect':'NoSchedule'})
        if doc['kind'] in ('DaemonSet','Deployment'):
            configuration=cpi if doc['metadata']['name']=='vsphere-cloud-controller-manager' else csi
            doc['spec']['template']['metadata'].setdefault('annotations',{})['arcia.io/config-sha256']=hashlib.sha256(configuration.encode()).hexdigest()
        documents.append(doc)
    documents.append({'apiVersion':'storage.k8s.io/v1','kind':'StorageClass',
        'metadata':{'name':'arcia-vsphere'},'provisioner':'csi.vsphere.vmware.com',
        'parameters':{'storagepolicyname':policy,'csi.storage.k8s.io/fstype':'ext4'},
        'reclaimPolicy':'Retain','allowVolumeExpansion':True,'volumeBindingMode':'WaitForFirstConsumer'})
    for doc in documents:
        doc['metadata'].setdefault('annotations',{})['arcia.io/operation-id']=operation
    return documents


def prepare(payload, lock):
    from pyVim.connect import SmartConnect, Disconnect
    from pyVmomi import vim
    connection=validate_connection(payload['connection'])
    service=payload['service']
    if payload['foundation']['operation_id']!=payload['operation_id']:
        raise ValueError('VMWARE_FOUNDATION_SCOPE')
    context=PinnedTLSContext(connection['certificate_sha256'])
    with socket.create_connection((connection['server'],connection['port']),timeout=15) as channel:
        with context.wrap_socket(channel,server_hostname=connection['server']) as tls:
            certificate=ssl.DER_cert_to_PEM_cert(tls.getpeercert(binary_form=True))
    endpoint=certificate_endpoint(connection,certificate,payload['private_root'])
    session=SmartConnect(host=connection['server'],port=connection['port'],user=service['username'],
        pwd=service['password'],sslContext=context,httpConnectionTimeout=30)
    try:
        datacenters=set()
        for record in payload['foundation']['nodes']:
            vm=vim.VirtualMachine(record['id'],session._stub)
            if vm.config.annotation!='ArcIA harness operation '+payload['operation_id']:
                raise ValueError('OWNED_VM_SCOPE_REQUIRED')
            if not any(o.key=='disk.EnableUUID' and str(o.value).casefold()=='true' for o in vm.config.extraConfig):
                raise ValueError('VM_DISK_UUID_REQUIRED')
            parent=vm.parent
            while parent and not isinstance(parent,vim.Datacenter): parent=parent.parent
            if parent is None: raise ValueError('DATACENTER_REQUIRED')
            datacenters.add(parent.name)
        policy=payload['instance']['config']['storage']['policy_ref']
        matches=[p for p in payload['foundation']['policies'] if p['id']==policy and p['compatible']]
        if len(matches)!=1:
            raise ValueError('COMPATIBLE_STORAGE_POLICY_REQUIRED')
        return render(lock,payload['operation_id'],{**connection,'server':endpoint,'certificate_pem':certificate},
                      service,sorted(datacenters),matches[0]['name'])
    finally: Disconnect(session)
