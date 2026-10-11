"""Protected Linux controller; input and output must remain in encrypted wrapper."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

CALLBACK='''from ansible.plugins.callback import CallbackBase
import json,os
class CallbackModule(CallbackBase):
    CALLBACK_VERSION=2.0
    CALLBACK_TYPE='aggregate'
    CALLBACK_NAME='arcia_result'
    CALLBACK_NEEDS_ENABLED=True
    def v2_playbook_on_stats(self,stats):
        values=[stats.summarize(h) for h in sorted(stats.processed) if h!='localhost']
        with open(os.environ['ARCIA_STATS_FILE'],'w') as handle: json.dump(values,handle)
'''


def execute(payload):
    os.umask(0o077)
    parent=Path.home()/'.local/share/arcia-controller'
    parent.mkdir(parents=True,mode=0o700,exist_ok=True);parent.chmod(0o700)
    # Same engineer key, short-lived copy on an owner-only ext4 filesystem.
    # Windows mount permissions cannot provide OpenSSH's mode-0600 guarantee.
    with tempfile.TemporaryDirectory(prefix='install-',dir=parent) as temporary:
        root=Path(temporary).resolve()
        if not root.is_relative_to(parent.resolve()): raise ValueError('CONTROLLER_PATH_SCOPE')
        for name,content in payload['files'].items():
            path=root/name
            if not path.resolve().is_relative_to(root) or Path(name).is_absolute(): raise ValueError('SOURCE_PATH_SCOPE')
            path.parent.mkdir(parents=True,exist_ok=True,mode=0o700);path.write_text(content);path.chmod(0o600)
        identity=root/'identity';identity.write_text(payload['identity']);identity.chmod(0o600)
        known=root/'known_hosts';known.write_text(payload['known_hosts']);known.chmod(0o600)
        inventory=payload['inventory']
        for host in inventory['all']['children']['k3s_servers']['hosts'].values():
            host['ansible_ssh_private_key_file']=str(identity)
            host['ansible_ssh_common_args']=('-o StrictHostKeyChecking=yes -o IdentitiesOnly=yes -o IdentityAgent=none '
                '-o PasswordAuthentication=no -o KbdInteractiveAuthentication=no -o GlobalKnownHostsFile=/dev/null '
                '-o UserKnownHostsFile='+str(known))
        (root/'inventory.json').write_text(json.dumps(inventory));(root/'inventory.json').chmod(0o600)
        callbacks=root/'callbacks';callbacks.mkdir(mode=0o700)
        (callbacks/'arcia_result.py').write_text(CALLBACK)
        environment={**os.environ,'ANSIBLE_CONFIG':str(root/'infra/ansible/ansible.cfg'),
            'ANSIBLE_CALLBACK_PLUGINS':str(callbacks),'ANSIBLE_CALLBACKS_ENABLED':'arcia_result',
            'ARCIA_STATS_FILE':str(root/'stats.json'),'ANSIBLE_NOCOLOR':'1','ANSIBLE_HOST_KEY_CHECKING':'True',
            'ANSIBLE_LOCAL_TEMP':str(root/'ansible-temp')}
        process=subprocess.run([sys.executable,'-m','ansible.cli.playbook',
            str(root/'infra/ansible/site.yml'),'-i',str(root/'inventory.json')],
            cwd=root,env=environment,capture_output=True,timeout=4800)
        stats=json.loads((root/'stats.json').read_text()) if (root/'stats.json').is_file() else []
        return {'returncode':process.returncode,'stats':stats,
            'stdout':process.stdout.decode(errors='replace'),'stderr':process.stderr.decode(errors='replace')}


if __name__=='__main__':
    try: result=execute(json.load(sys.stdin))
    except Exception:
        import traceback
        result={'returncode':2,'stats':[],'private_failure':traceback.format_exc()}
    print(json.dumps(result))
