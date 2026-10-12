"""SSH transport for fixed, versioned engineer operations. Private worker I/O only."""
from pathlib import Path
import json
import subprocess
import sys
from ssh_vmware_preflight import verified_nodes

ROOT = Path(__file__).resolve().parents[1]
class GuestFailure(RuntimeError): pass


def transport(payload):
    target, nodes = verified_nodes(payload)
    root = Path(payload['private_root']).resolve()
    identity = Path(target['ssh_public_key_path']).resolve().with_suffix('')
    # MSIX may resolve files to LocalCache while keeping the directory alias.
    # Compare the actual directory identity; do not weaken the SSH boundary.
    if (root.is_relative_to(ROOT) or not identity.is_file() or identity.is_symlink()
            or not identity.parent.samefile(root/'ssh')):
        raise ValueError('PROTECTED_SSH_IDENTITY_REQUIRED')
    known = root/'known_hosts.arcia'
    expected = ''.join(n['address']+' ssh-ed25519 '+n['key']+'\n' for n in nodes)
    if known.read_text() != expected: raise ValueError('SSH_TRUST_INTEGRITY')
    base = ['ssh', '-F', 'NUL' if sys.platform == 'win32' else '/dev/null', '-T',
        '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'IdentitiesOnly=yes',
        '-o', 'IdentityAgent=none', '-o', 'PasswordAuthentication=no', '-o', 'KbdInteractiveAuthentication=no',
        '-o', 'HostKeyAlgorithms=ssh-ed25519', '-o', 'UpdateHostKeys=no', '-o', 'ConnectTimeout=10',
        '-o', 'ConnectionAttempts=1', '-o', 'GlobalKnownHostsFile='+('NUL' if sys.platform == 'win32' else '/dev/null'),
        '-o', 'UserKnownHostsFile='+str(known), '-i', str(identity)]
    return target, nodes, base


def guest(target, node, base, script, values, *, root=False, timeout=180):
    code = ('ARCIA_INPUT = '+repr(values)+'\n').encode()+script
    command = base+[target['ssh_user']+'@'+node['address'],
                    'sudo -n /usr/bin/python3 -' if root else '/usr/bin/python3 -']
    process = subprocess.run(command, input=code, capture_output=True, timeout=timeout)
    if process.returncode or len(process.stdout) > 2*1024*1024:
        failure=GuestFailure('FIXED_GUEST_OPERATION_FAILED')
        failure.private_output={'stdout':process.stdout.decode(errors='replace'),'stderr':process.stderr.decode(errors='replace')}
        raise failure
    result = json.loads(process.stdout)
    if not isinstance(result, dict): raise ValueError('GUEST_RESULT_FORMAT')
    return result
