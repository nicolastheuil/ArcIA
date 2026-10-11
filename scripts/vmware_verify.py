#!/usr/bin/env python3
"""Read-only verification with a fixed public summary; no guest login."""
import json
import socket
import ssl
import sys
from vmware_inventory import PinnedTLSContext, safe_error_code, validate_connection
from vmware_deploy import NAMES, validate_target, ensure_placement


def verify(payload, enforce_placement=False):
    from pyVim.connect import SmartConnect, Disconnect
    from pyVmomi import vim
    connection=validate_connection(payload['connection']); target=validate_target(payload['target'])
    context=(PinnedTLSContext(connection['certificate_sha256']) if connection.get('certificate_sha256')
             else ssl.create_default_context(cafile=connection['ca_file'] or None))
    session=SmartConnect(host=connection['server'],port=connection['port'],user=connection['username'],
                         pwd=connection['password'],sslContext=context,httpConnectionTimeout=30)
    view=None
    try:
        content=session.RetrieveContent()
        view=content.viewManager.CreateContainerView(content.rootFolder,[vim.VirtualMachine],True)
        nodes=[vm for vm in view.view if vm.name in NAMES and vm.config and
               vm.config.annotation=='ArcIA harness operation '+payload['operation_id']]
        cluster=vim.ClusterComputeResource(target['cluster_id'],session._stub)
        if enforce_placement:
            ensure_placement(cluster,nodes,vim.Datastore(target['datastore_id'],session._stub),
                (vim.dvs.DistributedVirtualPortgroup(target['network_id'],session._stub) if target['network_id'].startswith('dvportgroup-')
                 else vim.Network(target['network_id'],session._stub)))
        result={'status':'pending','code':'VM_VERIFICATION_PENDING','created_count':len(nodes),
            'powered_on_count':0,'tools_running_count':0,'network_matching_count':0,
            'hardware_matching_count':0,'debian13_reported_count':0,'ssh_listening_count':0,
            'distinct_host_count':len({vm.runtime.host._moId for vm in nodes}),
            'uuid_mac_unique':False,'deployed':False,'k3s_installed':False,
            'ssh_validation_in_separate_preflight':True}
        result['anti_affinity_configured']=any(isinstance(rule,vim.cluster.AntiAffinityRuleSpec) and rule.enabled
            and rule.name=='arcia-k3s-separate-esxi' and set(rule.vm)==set(nodes) for rule in (cluster.configurationEx.rule or []))
        uuids=[]; macs=[]
        for vm in nodes:
            if str(vm.runtime.powerState)=='poweredOn': result['powered_on_count']+=1
            if vm.guest.toolsRunningStatus=='guestToolsRunning': result['tools_running_count']+=1
            expected=target['addresses'][NAMES.index(vm.name)].split('/')[0]
            reported={ip for adapter in (vm.guest.net or []) for ip in (adapter.ipAddress or [])}
            if expected in reported and (vm.guest.hostName or '').split('.')[0]==vm.name:
                result['network_matching_count']+=1
            description=(vm.guest.guestFullName or '')+' '+(getattr(vm.guest,'guestDetailedData','') or '')
            if 'Debian' in description and (' 13' in description or "distroVersion='13" in description):
                result['debian13_reported_count']+=1
            devices=vm.config.hardware.device
            disks=[d for d in devices if isinstance(d,vim.vm.device.VirtualDisk)]
            nics=[d for d in devices if isinstance(d,vim.vm.device.VirtualVmxnet3)]
            uuid_enabled=any(option.key.lower()=='disk.enableuuid' and str(option.value).upper()=='TRUE' for option in vm.config.extraConfig)
            if (vm.config.hardware.numCPU==8 and vm.config.hardware.memoryMB==32768 and len(disks)==1
                and disks[0].capacityInKB==150*1024**2 and len(nics)==1 and uuid_enabled
                and any(isinstance(d,vim.vm.device.ParaVirtualSCSIController) for d in devices)):
                result['hardware_matching_count']+=1
            uuids.append(vm.config.uuid)
            macs.extend(d.macAddress for d in nics)
            if str(vm.runtime.powerState)=='poweredOn':
                try:
                    with socket.create_connection((expected,22),timeout=2): result['ssh_listening_count']+=1
                except OSError: pass
        result['uuid_mac_unique']=len(nodes)==3 and len(set(uuids))==3 and len(macs)==3 and len(set(macs))==3
        required=('created_count','powered_on_count','tools_running_count','network_matching_count','hardware_matching_count','debian13_reported_count')
        if all(result[key]==3 for key in required) and result['uuid_mac_unique'] and result['distinct_host_count']==3 and result['anti_affinity_configured']:
            result.update(status='verified',code='THREE_DEBIAN_VMS_VERIFIED',deployed=True)
        return result
    finally:
        try:
            if view is not None: view.Destroy()
        finally: Disconnect(session)


def main():
    try: result=verify(json.load(sys.stdin),enforce_placement=sys.argv[1:]==['--enforce-placement'])
    except Exception as exc: result={'status':'blocked','code':safe_error_code(exc),'deployed':False}
    print(json.dumps(result))
    return 0 if result['status'] in ('pending','verified') else 2


if __name__=='__main__': sys.exit(main())
