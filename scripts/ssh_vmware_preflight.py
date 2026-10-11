#!/usr/bin/env python3
"""Private worker; stdin/stdout must be captured by Test-NodeAccess.ps1."""
import base64
import hashlib
import http.client
import io
import json
import os
from pathlib import Path
import re
import ssl
import subprocess
import sys
import time
from urllib.parse import quote, urlencode

from vmware_inventory import Invalid, PinnedTLSContext, validate_connection
from vmware_deploy import NAMES, validate_target, wait_task, seed_contents, make_seed, load_public_key, upload

ROOT = Path(__file__).resolve().parents[1]
CHECKS = ('root_probe', 'debian_13', 'amd64', 'cpu_budget', 'memory_budget',
          'system_disk_budget', 'system_disk_free', 'ntp_synchronized',
          'cgroups_v2', 'vmware_detected', 'swap_disabled', 'tun_supported',
          'dns_official_sources', 'cloud_init_finished', 'vmware_tools_active')


def verification_seed(target, index, challenge, mac):
    contents = seed_contents(target, index, load_public_key(target), challenge, mac)
    user = json.loads(contents['user-data'].split('\n', 1)[1])
    user['ssh_deletekeys'] = False
    user['package_update'] = False
    for field in ('packages', 'apt', 'growpart', 'resize_rootfs', 'ntp'):
        user.pop(field, None)
    user['runcmd'] = [user['runcmd'][1]]
    contents['user-data'] = '#cloud-config\n'+json.dumps(user)
    return make_seed(contents)


def read_guest_proof(vm, challenge, address):
    values = [option.value for option in vm.config.extraConfig if option.key == 'guestinfo.arcia.ssh-key-proof']
    if len(values) != 1: return None
    try:
        proof = json.loads(values[0])
        if proof['challenge'] != challenge: return None
        return parse_keyscan(address+' '+proof['public_key'], address)
    except (ValueError, KeyError, Invalid):
        return None


def inspect_publication(payload):
    from pyVim.connect import SmartConnect, Disconnect
    from pyVmomi import vim
    target=validate_target(payload['target']); connection=validate_connection(payload['connection'])
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
        result={'status':'pending','code':'HOST_KEY_PUBLICATION_STATUS','owned_count':len(nodes),
                'tools_running_count':0,'proof_present_count':0,'proof_verified_count':0,'updated_seed_count':0,
                'pending_question_count':0,'cdrom_locked_question_count':0,'running_reconfigure_count':0,
                'recent_reboot_count':0,'active_tasks':[],'cdrom_count':0,'iso_backing_count':0,'original_seed_count':0,'backing_types':[]}
        for vm in nodes:
            # Refresh vCenter's cached configuration after a guest/runtime change.
            vm.Reload()
            if vm.runtime.bootTime and (time.time()-vm.runtime.bootTime.timestamp()) < 600: result['recent_reboot_count']+=1
            question=vm.runtime.question
            if question:
                result['pending_question_count']+=1
                if any(message.id=='msg.cdromdisconnect.locked' for message in (question.message or [])):
                    result['cdrom_locked_question_count']+=1
            for task in content.taskManager.recentTask:
                info=task.info
                if info.entity==vm and str(info.state) in ('running','queued'):
                    description=info.descriptionId
                    result['active_tasks'].append({'state':str(info.state),'type':description if re.fullmatch(r'[A-Za-z.]{1,80}',description) else 'OTHER'})
                if info.entity==vm and info.descriptionId=='VirtualMachine.reconfigure' and str(info.state)=='running':
                    result['running_reconfigure_count']+=1
            if vm.guest.toolsRunningStatus=='guestToolsRunning': result['tools_running_count']+=1
            if any(option.key=='guestinfo.arcia.ssh-key-proof' for option in vm.config.extraConfig): result['proof_present_count']+=1
            address=target['addresses'][NAMES.index(vm.name)].split('/')[0]
            if read_guest_proof(vm,payload['challenges'][vm.name],address): result['proof_verified_count']+=1
            for device in vm.config.hardware.device:
                if isinstance(device,vim.vm.device.VirtualCdrom):
                    result['backing_types'].append(type(device.backing).__name__)
                    result['cdrom_count']+=1
                    if isinstance(device.backing,vim.vm.device.VirtualCdrom.IsoBackingInfo): result['iso_backing_count']+=1
                    if 'arcia-seed.iso' in getattr(device.backing,'fileName',''): result['original_seed_count']+=1
            if any(isinstance(device,vim.vm.device.VirtualCdrom) and
                   'arcia-ssh-proof.iso' in getattr(device.backing,'fileName','') for device in vm.config.hardware.device):
                result['updated_seed_count']+=1
        return result
    finally:
        try:
            if view is not None: view.Destroy()
        finally: Disconnect(session)


def publish_host_keys(payload):
    """One sequential guest reboot per owned, empty bootstrap VM; no forced reset."""
    from pyVim.connect import SmartConnect, Disconnect
    from pyVmomi import vim
    target = validate_target(payload['target'])
    connection = validate_connection(payload['connection'])
    challenges = payload['challenges']
    if set(challenges) != set(NAMES) or len(set(challenges.values())) != 3:
        raise Invalid('HOST_KEY_CHALLENGE_INVALID')
    # Validate challenges and build inputs before any mutation.
    from vmware_deploy import host_key_publication_command
    for challenge in challenges.values(): host_key_publication_command(challenge)
    context = (PinnedTLSContext(connection['certificate_sha256']) if connection.get('certificate_sha256')
               else ssl.create_default_context(cafile=connection['ca_file'] or None))
    session = SmartConnect(host=connection['server'], port=connection['port'], user=connection['username'],
                           pwd=connection['password'], sslContext=context, httpConnectionTimeout=30)
    view = None
    try:
        content = session.RetrieveContent()
        view = content.viewManager.CreateContainerView(content.rootFolder, [vim.VirtualMachine], True)
        nodes = [vm for vm in view.view if vm.name in NAMES and vm.config and
                 vm.config.annotation == 'ArcIA harness operation '+payload['operation_id']]
        if len(nodes) != 3 or {vm.name for vm in nodes} != set(NAMES):
            raise Invalid('THREE_OWNED_VMS_REQUIRED')
        prepared = []
        for index, name in enumerate(NAMES):
            vm = next(vm for vm in nodes if vm.name == name)
            if str(vm.runtime.powerState) != 'poweredOn' or vm.guest.toolsRunningStatus != 'guestToolsRunning':
                raise Invalid('OWNED_VM_NOT_RUNNING')
            address = target['addresses'][index].split('/')[0]
            if address not in {ip for nic in (vm.guest.net or []) for ip in (nic.ipAddress or [])}:
                raise Invalid('OWNED_VM_NETWORK_MISMATCH')
            devices = vm.config.hardware.device
            cd = [d for d in devices if isinstance(d, vim.vm.device.VirtualCdrom)]
            nics = [d for d in devices if isinstance(d, vim.vm.device.VirtualVmxnet3)]
            if len(cd) != 1 or len(nics) != 1: raise Invalid('VERIFICATION_HARDWARE_INVALID')
            seed = verification_seed(target, index, challenges[name], nics[0].macAddress)
            dc = vm.parent
            while dc is not None and not isinstance(dc, vim.Datacenter): dc = dc.parent
            if dc is None: raise Invalid('DATACENTER_NOT_FOUND')
            dc_path = []; ancestor = dc
            while ancestor.parent is not None: dc_path.append(ancestor.name); ancestor = ancestor.parent
            directory = vm.config.files.vmPathName.split('] ', 1)[1].rsplit('/', 1)[0]
            datastore = vim.Datastore(target['datastore_id'], session._stub)
            relative = directory+'/arcia-ssh-proof.iso'
            query = urlencode({'dcPath': '/'.join(reversed(dc_path)), 'dsName': datastore.name})
            url = f'https://{connection["server"]}:{connection["port"]}/folder/{quote(relative, safe="/")}?{query}'
            prepared.append((vm, cd[0], seed, url, f'[{datastore.name}] {relative}', address, challenges[name]))
        records = []
        for vm, cd, seed, url, backing, address, challenge in prepared:
            proof = read_guest_proof(vm, challenge, address)
            if proof is None:
                if payload.get('read_only') is not False:
                    raise Invalid('HOST_KEY_PUBLICATION_PENDING_NO_REPLAY')
                upload(url, io.BytesIO(seed), len(seed), context, 'PUT', 'application/octet-stream', cookie=session._stub.cookie)
                configure_proof_cd(vm, cd, backing, challenge)
                vm.RebootGuest()
                deadline = time.monotonic()+180
                while time.monotonic() < deadline:
                    proof = read_guest_proof(vm, challenge, address)
                    if proof is not None: break
                    time.sleep(3)
                if proof is None: raise Invalid('HOST_KEY_PUBLICATION_PENDING_NO_REPLAY')
            records.append(dict(node=vm.name, address=address, vm_id=vm._moId, vm_uuid=vm.config.uuid,
                                verified=True, verification_method='vcenter_guestinfo_challenge', **proof))
        if len({record['key'] for record in records}) != 3: raise Invalid('DUPLICATED_HOST_KEYS')
        return {'status': 'verified', 'code': 'THREE_HOST_KEYS_VERIFIED_VIA_VMWARE',
                'operation_id': payload['operation_id'], 'nodes': records}
    finally:
        try:
            if view is not None: view.Destroy()
        finally: Disconnect(session)


def configure_proof_cd(vm, cd, backing, challenge):
    from pyVmomi import vim
    # Send a clean CD device rather than carrying client-ATAPI fields.
    clean = vim.vm.device.VirtualCdrom(key=cd.key, controllerKey=cd.controllerKey, unitNumber=cd.unitNumber,
        backing=vim.vm.device.VirtualCdrom.IsoBackingInfo(fileName=backing),
        connectable=vim.vm.device.VirtualDevice.ConnectInfo(startConnected=True, connected=True, allowGuestControl=False))
    wait_task(vm.ReconfigVM_Task(vim.vm.ConfigSpec(
        extraConfig=[vim.option.OptionValue(key='guestinfo.arcia.ssh-key-proof', value='pending:'+challenge)],
        deviceChange=[vim.vm.device.VirtualDeviceSpec(operation='edit', device=clean)])), timeout=90)
    actual = next(d for d in vm.config.hardware.device if d.key == cd.key)
    if (not isinstance(actual.backing, vim.vm.device.VirtualCdrom.IsoBackingInfo)
            or actual.backing.fileName != backing or not actual.connectable.connected):
        raise Invalid('VERIFICATION_ISO_NOT_CONNECTED_NO_REBOOT')


def parse_keyscan(output, address):
    lines = [line.split() for line in output.splitlines() if line and not line.startswith('#')]
    if len(lines) != 1 or len(lines[0]) != 3 or lines[0][:2] != [address, 'ssh-ed25519']:
        raise Invalid('HOST_KEY_SCAN_INVALID')
    encoded = lines[0][2]
    raw = base64.b64decode(encoded, validate=True)
    if len(raw) != 51 or raw[:19] != b'\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20':
        raise Invalid('HOST_KEY_SCAN_INVALID')
    fingerprint = 'SHA256:' + base64.b64encode(hashlib.sha256(raw).digest()).decode().rstrip('=')
    return {'key': encoded, 'fingerprint': fingerprint}


def discover(payload):
    from pyVim.connect import SmartConnect, Disconnect
    from pyVmomi import vim
    target = validate_target(payload['target'])
    connection = validate_connection(payload['connection'])
    context = (PinnedTLSContext(connection['certificate_sha256']) if connection.get('certificate_sha256')
               else ssl.create_default_context(cafile=connection['ca_file'] or None))
    session = SmartConnect(host=connection['server'], port=connection['port'], user=connection['username'],
                           pwd=connection['password'], sslContext=context, httpConnectionTimeout=30)
    view = None
    try:
        content = session.RetrieveContent()
        view = content.viewManager.CreateContainerView(content.rootFolder, [vim.VirtualMachine], True)
        nodes = [vm for vm in view.view if vm.name in NAMES and vm.config and
                 vm.config.annotation == 'ArcIA harness operation ' + payload['operation_id']]
        if len(nodes) != 3 or {vm.name for vm in nodes} != set(NAMES):
            raise Invalid('THREE_OWNED_VMS_REQUIRED')
        records = []
        for index, name in enumerate(NAMES):
            vm = next(vm for vm in nodes if vm.name == name)
            address = target['addresses'][index].split('/')[0]
            if str(vm.runtime.powerState) != 'poweredOn':
                raise Invalid('OWNED_VM_NOT_RUNNING')
            reported = {ip for nic in (vm.guest.net or []) for ip in (nic.ipAddress or [])}
            if address not in reported or (vm.guest.hostName or '').split('.')[0] != name:
                raise Invalid('OWNED_VM_NETWORK_MISMATCH')
            scanner = Path(os.environ.get('ProgramFiles', 'C:/Program Files'))/'Git/usr/bin/ssh-keyscan.exe'
            scan = subprocess.run([str(scanner) if sys.platform == 'win32' and scanner.is_file() else 'ssh-keyscan', '-T', '8', '-t', 'ed25519', address],
                                  capture_output=True, text=True, timeout=30)
            record = dict(node=name, address=address, vm_id=vm._moId, vm_uuid=vm.config.uuid)
            if scan.returncode or len(scan.stdout) > 4096:
                markers = {'no matching': 'SSH_NEGOTIATION_FAILED', 'Connection refused': 'SSH_CONNECTION_REFUSED',
                           'timed out': 'SSH_CONNECTION_TIMEOUT', 'unsupported': 'SSH_ALGORITHM_UNSUPPORTED',
                           'kex_exchange_identification': 'SSH_KEX_FAILED'}
                record['scan_code'] = next((code for marker, code in markers.items() if marker in scan.stderr), 'HOST_KEY_SCAN_FAILED')
                record['scan_exit_code'] = scan.returncode
            else:
                record.update(parse_keyscan(scan.stdout, address))
            try:
                screenshot = wait_task(vm.CreateScreenshot_Task(), timeout=45)
                match = re.fullmatch(r'\[([^\]]+)\] (.+\.png)', screenshot)
                if not match or '..' in match[2].split('/'):
                    raise Invalid('CONSOLE_PATH_INVALID')
                dc = vm.parent
                while dc is not None and not isinstance(dc, vim.Datacenter):
                    dc = dc.parent
                if dc is None:
                    raise Invalid('DATACENTER_NOT_FOUND')
                dc_path = []; ancestor = dc
                while ancestor and ancestor != content.rootFolder:
                    dc_path.append(ancestor.name); ancestor = ancestor.parent
                query = urlencode({'dcPath': '/'.join(reversed(dc_path)), 'dsName': match[1]})
                channel = http.client.HTTPSConnection(connection['server'], connection['port'],
                                                       context=context, timeout=30)
                try:
                    channel.request('GET', '/folder/' + quote(match[2], safe='/') + '?' + query,
                                    headers={'Cookie': session._stub.cookie})
                    response = channel.getresponse()
                    image = response.read(8*1024*1024 + 1)
                    if response.status != 200 or len(image) > 8*1024*1024 or not image.startswith(b'\x89PNG\r\n\x1a\n'):
                        raise Invalid('CONSOLE_DOWNLOAD_FAILED')
                    record['console_png'] = base64.b64encode(image).decode()
                finally:
                    channel.close()
            except Exception:
                record['console_unavailable'] = True
            records.append(record)
        keys = [record['key'] for record in records if 'key' in record]
        if len(set(keys)) != len(keys):
            raise Invalid('DUPLICATED_HOST_KEYS')
        return {'status': 'discovered', 'code': 'SSH_KEYS_AWAITING_CONSOLE_VALIDATION',
                'operation_id': payload['operation_id'], 'nodes': records}
    finally:
        try:
            if view is not None: view.Destroy()
        finally:
            Disconnect(session)


def verified_nodes(payload):
    target = validate_target(payload['target'])
    trust = payload['trust']
    if trust.get('operation_id') != payload['operation_id'] or len(trust.get('nodes', [])) != 3:
        raise Invalid('SSH_TRUST_SCOPE_INVALID')
    for index, node in enumerate(trust['nodes']):
        if (node.get('node') != NAMES[index] or node.get('address') != target['addresses'][index].split('/')[0]
                or node.get('verification_method') not in ('vcenter_console_ocr', 'vcenter_console_human', 'vcenter_guestinfo_challenge')
                or node.get('verified') is not True):
            raise Invalid('SSH_TRUST_REQUIRED')
        scanned = parse_keyscan(node['address']+' ssh-ed25519 '+node['key'], node['address'])
        if scanned['fingerprint'] != node['fingerprint']:
            raise Invalid('SSH_TRUST_INTEGRITY_INVALID')
    if len({node['key'] for node in trust['nodes']}) != 3:
        raise Invalid('DUPLICATED_HOST_KEYS')
    return target, trust['nodes']


def preflight(payload):
    target, nodes = verified_nodes(payload)
    private_root = Path(payload['private_root']).resolve()
    if private_root.is_relative_to(ROOT) or not private_root.is_dir():
        raise Invalid('PROTECTED_DIRECTORY_REQUIRED')
    public = Path(target['ssh_public_key_path']).resolve()
    identity = public.with_suffix('')
    if not public.is_relative_to(private_root/'ssh') or not identity.is_file():
        raise Invalid('PROTECTED_KEY_REQUIRED')
    # Verify that the personal private key actually belongs to the configured public key.
    keycheck = subprocess.run(['ssh-keygen', '-y', '-P', '', '-f', str(identity)],
                              capture_output=True, text=True, timeout=15)
    if keycheck.returncode or keycheck.stdout.split()[:2] != public.read_text().split()[:2]:
        raise Invalid('SSH_KEY_LOCKED_OR_MISMATCHED')
    known = private_root/'known_hosts.arcia'
    known.write_text(''.join(n['address']+' ssh-ed25519 '+n['key']+'\n' for n in nodes), encoding='utf-8')
    results = []; identifiers = {'machine_id': [], 'product_uuid': []}
    probe = (ROOT/'scripts/node_probe.py').read_bytes()
    for index, node in enumerate(nodes, 1):
        command = ['ssh', '-F', 'NUL' if sys.platform == 'win32' else '/dev/null', '-T',
                   '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
                   '-o', 'IdentitiesOnly=yes', '-o', 'IdentityAgent=none',
                   '-o', 'PasswordAuthentication=no', '-o', 'KbdInteractiveAuthentication=no',
                   '-o', 'HostKeyAlgorithms=ssh-ed25519', '-o', 'UpdateHostKeys=no',
                   '-o', 'ConnectTimeout=10', '-o', 'ConnectionAttempts=1',
                   '-o', 'GlobalKnownHostsFile='+('NUL' if sys.platform == 'win32' else '/dev/null'),
                   '-o', 'UserKnownHostsFile='+str(known), '-i', str(identity),
                   target['ssh_user']+'@'+node['address'], 'sudo -n /usr/bin/python3 -']
        result = {'node': 'N'+str(index), 'passed': False}
        try:
            process = subprocess.run(command, input=probe, capture_output=True, timeout=75)
            if process.returncode or len(process.stdout) > 16384:
                raise Invalid('SSH_OR_SUDO_FAILED')
            raw = json.loads(process.stdout)
            if set(raw.get('checks', {})) != set(CHECKS) or any(type(v) is not bool for v in raw['checks'].values()):
                raise Invalid('PROBE_FORMAT_INVALID')
            result['checks'] = raw['checks']
            for key in identifiers:
                value = raw[key].replace('-', '').lower()
                valid = bool(re.fullmatch(r'[a-f0-9]{32}', value)) and value != '0'*32
                result['checks'][key+'_valid'] = valid
                identifiers[key].append(value if valid else '')
            result['passed'] = all(result['checks'].values())
        except Exception:
            result['code'] = 'SSH_OR_PROBE_FAILED'
            for key in identifiers: identifiers[key].append('')
        results.append(result)
    unique = all(len(values) == 3 and all(values) and len(set(values)) == 3 for values in identifiers.values())
    passed = all(node['passed'] for node in results) and unique
    return {'status': 'verified' if passed else 'blocked',
            'code': 'THREE_LINUX_NODES_PREFLIGHT_PASSED' if passed else 'LINUX_PREFLIGHT_FAILED',
            'nodes': results, 'machine_id_and_uuid_unique': unique,
            'ssh_host_keys_verified': True, 'passed': passed, 'k3s_installed': False}


def main():
    try:
        payload = json.load(sys.stdin)
        if sys.argv[1:] == ['--discover']: result = discover(payload)
        elif sys.argv[1:] == ['--publish']: result = publish_host_keys(payload)
        elif sys.argv[1:] == ['--status']: result = inspect_publication(payload)
        elif not sys.argv[1:]: result = preflight(payload)
        else: raise Invalid('INVALID_WORKER_MODE')
    except Exception as exc:
        allowed = {'HOST_KEY_SCAN_INVALID', 'HOST_KEY_SCAN_FAILED', 'THREE_OWNED_VMS_REQUIRED',
                   'OWNED_VM_NOT_RUNNING', 'OWNED_VM_NETWORK_MISMATCH', 'DUPLICATED_HOST_KEYS',
                   'SSH_TRUST_SCOPE_INVALID', 'SSH_TRUST_REQUIRED', 'SSH_TRUST_INTEGRITY_INVALID',
                   'PROTECTED_DIRECTORY_REQUIRED', 'PROTECTED_KEY_REQUIRED', 'SSH_KEY_LOCKED_OR_MISMATCHED',
                   'HOST_KEY_CHALLENGE_INVALID', 'HOST_KEY_PUBLICATION_PENDING_NO_REPLAY', 'VERIFICATION_HARDWARE_INVALID',
                   'VERIFICATION_ISO_NOT_CONNECTED_NO_REBOOT'}
        code = str(exc) if isinstance(exc, Invalid) and str(exc) in allowed else 'SSH_VALIDATION_WORKER_FAILED'
        import traceback
        lines = [frame.lineno for frame in traceback.extract_tb(exc.__traceback__) if frame.filename == __file__]
        result = {'status': 'blocked', 'code': code, 'passed': False, 'failure_line': lines[-1] if lines else 0}
    print(json.dumps(result))
    return 2 if result['status'] == 'blocked' else 0


if __name__ == '__main__': sys.exit(main())
