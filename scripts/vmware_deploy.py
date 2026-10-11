#!/usr/bin/env python3
"""Private VMware worker: stdin/stdout are captured by the protected launcher.

No untrusted fault text or raw configuration is logged. No deletion or adoption.
"""
import hashlib
import http.client
import io
import ipaddress
import json
from pathlib import Path
import re
import ssl
import sys
import time
import traceback
import uuid
from urllib.parse import quote, urlencode, urlsplit
from xml.sax.saxutils import escape

from vmware_inventory import Invalid, PinnedTLSContext, safe_error_code, validate_connection

NAMES = ('arcia-k3s-01', 'arcia-k3s-02', 'arcia-k3s-03')
ROOT = Path(__file__).resolve().parents[1]


def host_key_publication_command(challenge):
    if not isinstance(challenge, str) or not re.fullmatch(r'[a-f0-9-]{36}', challenge):
        raise Invalid('HOST_KEY_CHALLENGE_INVALID')
    code = ("import json,subprocess;from pathlib import Path;"
            "key=' '.join(Path('/etc/ssh/ssh_host_ed25519_key.pub').read_text().split()[:2]);"
            "proof=json.dumps({'challenge':"+repr(challenge)+",'public_key':key},separators=(',',':'));"
            "subprocess.run(['/usr/bin/vmtoolsd','--cmd','info-set guestinfo.arcia.ssh-key-proof '+proof],check=True)")
    return ['/usr/bin/python3', '-c', code]


def validate_target(target):
    required = {'schema_version','cluster_id','datastore_id','network_id','folder_id','addresses',
                'gateway','dns','ntp','ssh_user','ssh_public_key_path'}
    if not isinstance(target, dict) or set(target) != required or target['schema_version'] != 1:
        raise Invalid('TARGET_FIELDS_INVALID')
    for field, prefix in (('cluster_id','domain-c'),('datastore_id','datastore-'),
                          ('network_id',None),('folder_id','group-v')):
        value = target[field]
        if not isinstance(value, str) or not re.fullmatch(r'[a-zA-Z0-9-]+', value) or (prefix and not value.startswith(prefix)):
            raise Invalid('PLACEMENT_REFERENCE_INVALID')
    if not re.fullmatch(r'(network-|dvportgroup-)\d+', target['network_id']):
        raise Invalid('NETWORK_REFERENCE_INVALID')
    if not isinstance(target['addresses'], list) or len(target['addresses']) != 3:
        raise Invalid('THREE_ADDRESSES_REQUIRED')
    try:
        addresses = [ipaddress.IPv4Interface(value) for value in target['addresses']]
        gateway = ipaddress.IPv4Address(target['gateway'])
        dns = [ipaddress.IPv4Address(value) for value in target['dns']]
    except (ValueError, TypeError):
        raise Invalid('IP_CONFIGURATION_INVALID') from None
    if len({a.ip for a in addresses}) != 3 or len({a.network for a in addresses}) != 1:
        raise Invalid('IP_ADDRESSES_DUPLICATE_OR_SUBNETS_DIFFER')
    subnet = addresses[0].network
    if not all(a.ip.is_private and a.ip not in (subnet.network_address, subnet.broadcast_address, gateway) for a in addresses):
        raise Invalid('PRIVATE_USABLE_ADDRESSES_REQUIRED')
    if gateway not in subnet or gateway in (subnet.network_address, subnet.broadcast_address) or not dns:
        raise Invalid('GATEWAY_OR_DNS_INVALID')
    if not target['ntp'] or not all(isinstance(n,str) and re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9.-]{0,252}', n) for n in target['ntp']):
        raise Invalid('NTP_REQUIRED')
    if not isinstance(target['ssh_user'], str) or not re.fullmatch(r'[a-z_][a-z0-9_-]{0,30}', target['ssh_user']) or target['ssh_user'] in ('root','debian'):
        raise Invalid('PERSONAL_SSH_ACCOUNT_REQUIRED')
    key_path = target['ssh_public_key_path']
    if not isinstance(key_path,str) or not key_path.lower().endswith('.pub'):
        raise Invalid('PUBLIC_KEY_FILE_REQUIRED')
    return target


def load_public_key(target):
    path = Path(target['ssh_public_key_path'])
    if path.stat().st_size > 16384:
        raise Invalid('PUBLIC_KEY_INVALID')
    key = path.read_text(encoding='utf-8').strip()
    if '\n' in key or not re.fullmatch(r'(ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp(?:256|384|521)) [A-Za-z0-9+/=]+(?: [^\r\n]*)?', key):
        raise Invalid('PUBLIC_KEY_INVALID')
    return key


def seed_contents(target, index, public_key, instance_id, nic_mac):
    lock = json.loads((ROOT/'infra/vmware/debian-image.lock.json').read_text())
    # JSON is valid YAML 1.2; no user-controlled shell or YAML interpolation.
    user = {'hostname':NAMES[index], 'manage_etc_hosts':True, 'disable_root':True,
            'ssh_pwauth':False, 'ssh_deletekeys':True,
            'users':[{'name':target['ssh_user'], 'groups':['sudo'], 'shell':'/bin/bash',
                      'lock_passwd':True, 'sudo':['ALL=(ALL) NOPASSWD:ALL'],
                      'ssh_authorized_keys':[public_key]}],
            'growpart':{'mode':'auto','devices':['/'],'ignore_growroot_disabled':False},
            'resize_rootfs':True, 'package_update':True, 'package_upgrade':False,
            'apt':{'preserve_sources_list':False, 'sources_list':
                'deb [check-valid-until=no] https://snapshot.debian.org/archive/debian/20261001T000000Z/ trixie main\n'
                'deb [check-valid-until=no] https://snapshot.debian.org/archive/debian-security/20261001T000000Z/ trixie-security main\n'},
            'packages':[['open-vm-tools',lock['open_vm_tools_version']]],
            'ntp':{'enabled':True,'servers':target['ntp']},
            'runcmd':[['systemctl','enable','--now','open-vm-tools'],
                      host_key_publication_command(instance_id),
                      ['sh','-c','test -x /usr/bin/vmtoolsd && mkdir -p /var/lib/arcia && touch /var/lib/arcia/bootstrap-ready']]}
    network = {'version':2, 'ethernets':{'arcia0':{'match':{'macaddress':nic_mac},'set-name':'arcia0','dhcp4':False,'dhcp6':False,
        'addresses':[target['addresses'][index]],'routes':[{'to':'default','via':target['gateway']}],
        'nameservers':{'addresses':target['dns']}}}}
    return {'user-data':'#cloud-config\n'+json.dumps(user),
            'meta-data':json.dumps({'instance-id':instance_id,'local-hostname':NAMES[index]}),
            'network-config':json.dumps(network)}


def make_seed(contents):
    import pycdlib
    iso=pycdlib.PyCdlib()
    iso.new(interchange_level=3, joliet=3, rock_ridge='1.09', vol_ident='CIDATA')
    streams=[]
    try:
        for index,(name,value) in enumerate(contents.items()):
            data=value.encode('utf-8'); stream=io.BytesIO(data); streams.append(stream)
            iso.add_fp(stream,len(data),iso_path=f'/DATA{index}.;1',rr_name=name,joliet_path='/'+name)
        output=io.BytesIO(); iso.write_fp(output)
        return output.getvalue()
    finally:
        iso.close()


def ovf_descriptor(size, guest_id):
    # One disk, fixed hardware, network mapping supplied separately by managed ID.
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<Envelope xmlns="http://schemas.dmtf.org/ovf/envelope/1" xmlns:ovf="http://schemas.dmtf.org/ovf/envelope/1"
 xmlns:rasd="http://schemas.dmtf.org/wbem/wscim/1/cim-schema/2/CIM_ResourceAllocationSettingData"
 xmlns:vssd="http://schemas.dmtf.org/wbem/wscim/1/cim-schema/2/CIM_VirtualSystemSettingData"
 xmlns:vmw="http://www.vmware.com/schema/ovf">
 <References><File ovf:id="diskfile" ovf:href="disk.vmdk" ovf:size="{size}"/></References>
 <DiskSection><Info>Debian base disk</Info><Disk ovf:diskId="disk1" ovf:fileRef="diskfile" ovf:capacity="3221225472" ovf:format="http://www.vmware.com/interfaces/specifications/vmdk.html#streamOptimized"/></DiskSection>
 <NetworkSection><Info>Selected private network</Info><Network ovf:name="arcia-network"/></NetworkSection>
 <VirtualSystem ovf:id="arcia-debian"><Info>ArcIA Debian 13</Info><Name>arcia-debian</Name>
 <OperatingSystemSection ovf:id="101" vmw:osType="{escape(guest_id)}"><Info>Debian 13 amd64</Info></OperatingSystemSection>
 <VirtualHardwareSection><Info>ArcIA node</Info><System><vssd:ElementName>ArcIA</vssd:ElementName><vssd:InstanceID>0</vssd:InstanceID><vssd:VirtualSystemIdentifier>arcia-debian</vssd:VirtualSystemIdentifier><vssd:VirtualSystemType>vmx-19</vssd:VirtualSystemType></System>
 <Item><rasd:ElementName>8 vCPU</rasd:ElementName><rasd:InstanceID>1</rasd:InstanceID><rasd:ResourceType>3</rasd:ResourceType><rasd:VirtualQuantity>8</rasd:VirtualQuantity></Item>
 <Item><rasd:AllocationUnits>byte * 2^20</rasd:AllocationUnits><rasd:ElementName>32 GiB RAM</rasd:ElementName><rasd:InstanceID>2</rasd:InstanceID><rasd:ResourceType>4</rasd:ResourceType><rasd:VirtualQuantity>32768</rasd:VirtualQuantity></Item>
 <Item><rasd:Address>0</rasd:Address><rasd:ElementName>PVSCSI</rasd:ElementName><rasd:InstanceID>3</rasd:InstanceID><rasd:ResourceSubType>VirtualSCSI</rasd:ResourceSubType><rasd:ResourceType>6</rasd:ResourceType></Item>
 <Item><rasd:AddressOnParent>0</rasd:AddressOnParent><rasd:ElementName>System disk</rasd:ElementName><rasd:HostResource>ovf:/disk/disk1</rasd:HostResource><rasd:InstanceID>4</rasd:InstanceID><rasd:Parent>3</rasd:Parent><rasd:ResourceType>17</rasd:ResourceType></Item>
 <Item><rasd:AddressOnParent>7</rasd:AddressOnParent><rasd:AutomaticAllocation>true</rasd:AutomaticAllocation><rasd:Connection>arcia-network</rasd:Connection><rasd:ElementName>VMXNET3</rasd:ElementName><rasd:InstanceID>5</rasd:InstanceID><rasd:ResourceSubType>VmxNet3</rasd:ResourceSubType><rasd:ResourceType>10</rasd:ResourceType></Item>
 </VirtualHardwareSection></VirtualSystem></Envelope>'''


def wait_task(task, timeout=600):
    deadline=time.monotonic()+timeout
    while str(task.info.state) not in ('success','error'):
        if time.monotonic()>deadline: raise Invalid('VMWARE_TASK_TIMEOUT_STATE_UNCERTAIN')
        time.sleep(1)
    if str(task.info.state)=='error': raise Invalid('VMWARE_TASK_FAILED')
    return task.info.result


def wait_lease(lease):
    deadline=time.monotonic()+120
    while str(lease.state)!='ready':
        if str(lease.state)=='error': raise Invalid('OVF_IMPORT_LEASE_FAILED')
        if time.monotonic()>deadline: raise Invalid('OVF_IMPORT_LEASE_TIMEOUT')
        time.sleep(1)


def upload(url, source, length, context, method, content_type, cookie=None, lease=None):
    parts=urlsplit(url)
    if parts.scheme!='https' or not parts.hostname or parts.username or parts.password:
        raise Invalid('HTTPS_UPLOAD_REQUIRED')
    channel=http.client.HTTPSConnection(parts.hostname,parts.port or 443,context=context,timeout=60)
    try:
        channel.putrequest(method,parts.path+('?' + parts.query if parts.query else ''))
        channel.putheader('Content-Type',content_type); channel.putheader('Content-Length',str(length))
        if cookie: channel.putheader('Cookie',cookie)
        channel.endheaders()
        sent=0; next_progress=0
        while chunk:=source.read(1024*1024):
            channel.send(chunk); sent+=len(chunk)
            if lease and time.monotonic()>=next_progress:
                lease.HttpNfcLeaseProgress(min(99,int(100*sent/length))); next_progress=time.monotonic()+5
        response=channel.getresponse()
        if response.status not in (200,201,204): raise Invalid('DATASTORE_UPLOAD_FAILED')
        response.read()
    finally:
        channel.close()


def trusted_lease_context(device):
    pem=getattr(device,'sslCertificate',None)
    if pem: return PinnedTLSContext(hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem)).hexdigest())
    pin=device.sslThumbprint.replace(':','').lower()
    if not re.fullmatch(r'[a-f0-9]+',pin) or len(pin) not in (40,64,128): raise Invalid('NFC_CERTIFICATE_PIN_REQUIRED')
    return PinnedTLSContext(pin,{40:'sha1',64:'sha256',128:'sha512'}[len(pin)])


def ensure_placement(cluster, nodes, datastore, network):
    """A scoped optional rule preserves separation while permitting HA restart."""
    from pyVmomi import vim
    if len(nodes)!=3 or {vm.name for vm in nodes}!=set(NAMES): raise Invalid('THREE_OWNED_VMS_REQUIRED')
    name='arcia-k3s-separate-esxi'
    rules=[rule for rule in (cluster.configurationEx.rule or []) if rule.name==name]
    if rules:
        if len(rules)!=1 or not isinstance(rules[0],vim.cluster.AntiAffinityRuleSpec) or set(rules[0].vm)!=set(nodes):
            raise Invalid('EXISTING_PLACEMENT_RULE_REFUSED')
        if not rules[0].enabled: raise Invalid('PLACEMENT_RULE_DISABLED')
    else:
        rule=vim.cluster.AntiAffinityRuleSpec(name=name,enabled=True,mandatory=False,userCreated=True,vm=nodes)
        spec=vim.cluster.ConfigSpecEx(rulesSpec=[vim.cluster.RuleSpec(operation='add',info=rule)])
        wait_task(cluster.ReconfigureComputeResource_Task(spec,modify=True))
    hosts=[h for h in cluster.host if str(h.runtime.connectionState)=='connected' and not h.runtime.inMaintenanceMode
           and datastore in h.datastore and network in h.network]
    if len(hosts)<3: return False
    for _ in range(30):
        if len({vm.runtime.host for vm in nodes})==3: return True
        time.sleep(1)
    # Manual DRS may only recommend placement. Migrate only our new VMs.
    kept=set()
    for vm in sorted(nodes,key=lambda v:v.name):
        current=vm.runtime.host
        if current not in kept:
            kept.add(current); continue
        occupied={node.runtime.host for node in nodes}
        candidates=[host for host in hosts if host not in occupied and host.summary.quickStats.overallMemoryUsage is not None
                    and host.summary.hardware.memorySize-host.summary.quickStats.overallMemoryUsage*1024**2>=32*1024**3]
        if not candidates: raise Invalid('SEPARATE_HOST_CAPACITY_UNAVAILABLE')
        destination=sorted(candidates,key=lambda h:h._moId)[0]
        wait_task(vm.MigrateVM_Task(pool=cluster.resourcePool,host=destination,priority='defaultPriority'))
        kept.add(destination)
    return len({vm.runtime.host for vm in nodes})==3


def deploy(payload, created, plan_only=False):
    from pyVim.connect import SmartConnect, Disconnect
    from pyVmomi import vim
    connection=validate_connection(payload['connection']); target=validate_target(payload['target'])
    public_key=load_public_key(target)
    operation=str(uuid.UUID(payload['operation_id']))
    disk=Path(payload['disk_path']); receipt=json.loads(Path(payload['receipt_path']).read_text())
    lock=json.loads((ROOT/'infra/vmware/debian-image.lock.json').read_text())
    with disk.open('rb') as stream: checksum=hashlib.file_digest(stream,'sha512').hexdigest()
    if receipt.get('source_sha512')!=lock['sha512'] or checksum!=receipt.get('vmdk_sha512'):
        raise Invalid('VMDK_RECEIPT_INVALID')
    context=(PinnedTLSContext(connection['certificate_sha256']) if connection.get('certificate_sha256')
             else ssl.create_default_context(cafile=connection['ca_file'] or None))
    session=SmartConnect(host=connection['server'],port=connection['port'],user=connection['username'],
                         pwd=connection['password'],sslContext=context,httpConnectionTimeout=30)
    view=None
    try:
        content=session.RetrieveContent()
        if content.about.apiType!='VirtualCenter': raise Invalid('VCENTER_REQUIRED')
        view=content.viewManager.CreateContainerView(content.rootFolder,[vim.ClusterComputeResource,vim.Datastore,vim.Network,vim.Folder,vim.VirtualMachine],True)
        objects={o._moId:o for o in view.view}
        cluster,datastore,network,folder=[objects[target[k]] for k in ('cluster_id','datastore_id','network_id','folder_id')]
        if not isinstance(cluster,vim.ClusterComputeResource) or not isinstance(datastore,vim.Datastore) or not isinstance(network,vim.Network) or not isinstance(folder,vim.Folder): raise Invalid('PLACEMENT_TYPE_INVALID')
        if any(isinstance(o,vim.VirtualMachine) and o.name in NAMES for o in objects.values()): raise Invalid('EXISTING_ARCIA_VM_REFUSED')
        hosts=sorted([h for h in cluster.host if str(h.runtime.connectionState)=='connected' and not h.runtime.inMaintenanceMode and datastore in h.datastore and network in h.network],key=lambda h:h._moId)
        if not hosts or not datastore.summary.accessible or datastore.summary.freeSpace<450*1024**3: raise Invalid('SHARED_DATASTORE_OR_CAPACITY_INSUFFICIENT')
        selected=[hosts[i%len(hosts)] for i in range(3)]
        for host in set(selected):
            used=host.summary.quickStats.overallMemoryUsage
            if used is None or host.summary.hardware.memorySize-used*1024**2<selected.count(host)*32*1024**3: raise Invalid('HOST_MEMORY_INSUFFICIENT')
        datacenter=cluster
        while not isinstance(datacenter,vim.Datacenter):
            datacenter=datacenter.parent
            if datacenter is None: raise Invalid('DATACENTER_NOT_FOUND')
        parent=folder
        while parent is not None and parent!=datacenter.vmFolder: parent=parent.parent
        if parent is None or not any(kind in ('VirtualMachine',vim.VirtualMachine) for kind in folder.childType): raise Invalid('VM_FOLDER_INVALID')
        guest_ids=None
        for host in set(selected):
            options=cluster.environmentBrowser.QueryConfigOption(key='vmx-19',host=host)
            if options is None: raise Invalid('VM_HARDWARE_VERSION_UNSUPPORTED')
            supported={g.id for g in options.guestOSDescriptor}
            guest_ids=supported if guest_ids is None else guest_ids & supported
        guest_id=next((g for g in ('debian13_64Guest','debian12_64Guest','other6xLinux64Guest',
                                  'debian11_64Guest','other5xLinux64Guest','debian10_64Guest','other4xLinux64Guest') if g in guest_ids),None)
        if not guest_id: raise Invalid('DEBIAN_GUEST_PROFILE_UNSUPPORTED')
        specs=[]
        for index,host in enumerate(selected):
            params=vim.OvfManager.CreateImportSpecParams(entityName=NAMES[index],diskProvisioning='thin',hostSystem=host,
                networkMapping=[vim.OvfManager.NetworkMapping(name='arcia-network',network=network)])
            imported=content.ovfManager.CreateImportSpec(ovf_descriptor(disk.stat().st_size,guest_id),cluster.resourcePool,datastore,params)
            if imported.error: raise Invalid('OVF_SPEC_REJECTED')
            imported.importSpec.configSpec.annotation='ArcIA harness operation '+operation
            specs.append(imported)
        if plan_only:
            return {'status':'validated','code':'VM_CREATION_PREFLIGHT_PASSED','deployed':False,
                    'vm_count':3,'distinct_host_count':len(set(selected)),'created_count':0}
        # All target/OVF validation precedes the first mutation.
        for index,host in enumerate(selected):
            imported=specs[index]
            created.append({'name':NAMES[index],'id':None,'state':'import_dispatched_uncertain','operation_id':operation})
            lease=cluster.resourcePool.ImportVApp(imported.importSpec,folder,host)
            wait_lease(lease)
            vm=lease.info.entity
            created[-1].update({'id':vm._moId,'state':'importing'})
            try:
                for item in imported.fileItem:
                    if item.path!='disk.vmdk': raise Invalid('UNEXPECTED_OVF_FILE')
                    device=next(d for d in lease.info.deviceUrl if d.importKey==item.deviceId)
                    url=device.url.replace('://*:', '://'+connection['server']+':').replace('://*/','://'+connection['server']+'/')
                    with disk.open('rb') as stream:
                        upload(url,stream,disk.stat().st_size,trusted_lease_context(device),'POST','application/x-vnd.vmware-streamVmdk',lease=lease)
                lease.HttpNfcLeaseComplete()
            except Exception:
                # Abort this uncommitted import only; never delete a completed VM.
                lease.HttpNfcLeaseAbort(vim.fault.OvfFault())
                raise
            created[-1]['state']='imported_powered_off'
            devices=vm.config.hardware.device
            nics=[d for d in devices if isinstance(d,vim.vm.device.VirtualVmxnet3)]
            if len(nics)!=1 or not nics[0].macAddress or not any(isinstance(d,vim.vm.device.ParaVirtualSCSIController) for d in devices): raise Invalid('IMPORTED_HARDWARE_MISMATCH')
            if vm.config.hardware.numCPU!=8 or vm.config.hardware.memoryMB!=32768: raise Invalid('IMPORTED_HARDWARE_MISMATCH')
            disks=[d for d in devices if isinstance(d,vim.vm.device.VirtualDisk)]
            if len(disks)!=1: raise Invalid('UNEXPECTED_IMPORTED_DISKS')
            disks[0].capacityInKB=150*1024**2
            changes=[vim.vm.device.VirtualDeviceSpec(operation='edit',device=disks[0])]
            # Seed is uploaded through vCenter using the accepted vCenter identity.
            instance_id=str(uuid.uuid4())
            seed=make_seed(seed_contents(target,index,public_key,instance_id,nics[0].macAddress))
            created[-1]['host_key_challenge']=instance_id
            directory=vm.config.files.vmPathName.split('] ',1)[1].rsplit('/',1)[0]
            relative=directory+'/arcia-seed.iso'
            dc_path=[]; node=datacenter
            while node.parent is not None: dc_path.append(node.name); node=node.parent
            query=urlencode({'dcPath':'/'.join(reversed(dc_path)),'dsName':datastore.name})
            url=f'https://{connection["server"]}:{connection["port"]}/folder/{quote(relative,safe="/")}?{query}'
            upload(url,io.BytesIO(seed),len(seed),context,'PUT','application/octet-stream',cookie=session._stub.cookie)
            ide=next((d for d in devices if isinstance(d,vim.vm.device.VirtualIDEController)),None)
            if ide is None:
                ide=vim.vm.device.VirtualIDEController(key=-101,busNumber=0)
                changes.append(vim.vm.device.VirtualDeviceSpec(operation='add',device=ide))
            cd=vim.vm.device.VirtualCdrom(key=-102,controllerKey=ide.key,unitNumber=0,
                backing=vim.vm.device.VirtualCdrom.IsoBackingInfo(fileName=f'[{datastore.name}] {relative}'),
                connectable=vim.vm.device.VirtualDevice.ConnectInfo(startConnected=True,allowGuestControl=False,connected=True))
            changes.append(vim.vm.device.VirtualDeviceSpec(operation='add',device=cd))
            config=vim.vm.ConfigSpec(deviceChange=changes,extraConfig=[vim.option.OptionValue(key='disk.EnableUUID',value='TRUE'),
                vim.option.OptionValue(key='guestinfo.arcia.ssh-key-proof',value='pending:'+instance_id)])
            wait_task(vm.ReconfigVM_Task(config)); wait_task(vm.PowerOnVM_Task(host=host))
            created[-1]['state']='powered_on_boot_unverified'
        own_nodes=[vim.VirtualMachine(record['id'],session._stub) for record in created]
        separated=ensure_placement(cluster,own_nodes,datastore,network)
        return {'status':'created','code':'THREE_VMS_POWERED_ON','created':created,'created_count':len(created),
                'deployed':True,'separate_hosts_verified':separated,'debian_boot_verified':False,'k3s_installed':False}
    finally:
        try:
            if view is not None: view.Destroy()
        finally: Disconnect(session)


def main():
    created=[]
    try:
        result=deploy(json.load(sys.stdin),created,plan_only=sys.argv[1:]==['--validate-only'])
    except Exception as exc:
        lines=[frame.lineno for frame in traceback.extract_tb(exc.__traceback__) if Path(frame.filename).resolve()==Path(__file__).resolve()]
        result={'status':'blocked','code':safe_error_code(exc),'created':created,'created_count':sum(bool(vm['id']) for vm in created),
                'failure_line':lines[-1] if lines else 0,
                'deployed':False,'partial_or_uncertain':bool(created)}
    print(json.dumps(result))
    return 0 if result['status'] in ('created','validated') else 2


if __name__=='__main__': sys.exit(main())
