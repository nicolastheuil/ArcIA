"""Register only the pinned builder MCP table; never print existing config."""
import json
import os
from pathlib import Path
import sys
import tomllib
import re


def unregister(value):
    path=Path(value['config_path'])
    if not path.exists(): return {'status':'removed','code':'LOCAL_CONTEXT7_ABSENT'}
    original=path.read_text(encoding='utf-8')
    parsed=tomllib.loads(original)
    current=parsed.get('mcp_servers',{}).get('arcia_context7')
    if current is None:return {'status':'removed','code':'LOCAL_CONTEXT7_ABSENT'}
    if current.get('args')!=[value['entry']]:
        raise ValueError('FOREIGN_CONTEXT7_UNINSTALL_REFUSED')
    updated=re.sub(r'(?ms)^\[mcp_servers\.arcia_context7(?:\.env)?\]\s*\n.*?(?=^\[|\Z)','',original)
    after=tomllib.loads(updated)
    expected=parsed.copy();expected['mcp_servers']=dict(parsed['mcp_servers'])
    del expected['mcp_servers']['arcia_context7']
    if after!=expected:raise ValueError('UNINSTALL_CONFIG_PRESERVATION_FAILED')
    temporary=path.with_name('arcia-mcp-uninstall-'+str(os.getpid())+'.tmp')
    try:
        with temporary.open('x',encoding='utf-8',newline='\n') as stream:stream.write(updated)
        os.replace(temporary,path)
    finally:temporary.unlink(missing_ok=True)
    return {'status':'removed','code':'LOCAL_CONTEXT7_REMOVED_OTHER_SETTINGS_PRESERVED'}


def register(value):
    path = Path(value['config_path'])
    text = path.read_text(encoding='utf-8') if path.exists() else ''
    config = tomllib.loads(text)
    expected = {'command': value['node'], 'args': [value['entry']],
                'startup_timeout_sec': 30, 'tool_timeout_sec': 60,
                'env': {'DISABLE_TELEMETRY': '1'}}
    previous = config.get('mcp_servers', {}).get('arcia_context7')
    if previous is not None:
        if previous != expected:
            raise ValueError('EXISTING_BUILDER_MCP_CONFLICT')
        return {'status': 'configured', 'code': 'PINNED_CONTEXT7_ALREADY_REGISTERED'}
    section = ('\n\n[mcp_servers.arcia_context7]\ncommand = '+json.dumps(value['node'])+
               '\nargs = '+json.dumps([value['entry']])+
               '\nstartup_timeout_sec = 30\ntool_timeout_sec = 60\n'
               '[mcp_servers.arcia_context7.env]\nDISABLE_TELEMETRY = "1"\n')
    updated = text + section
    if tomllib.loads(updated)['mcp_servers']['arcia_context7'] != expected:
        raise ValueError('BUILDER_MCP_SERIALIZATION_FAILED')
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name('arcia-mcp-config-'+str(os.getpid())+'.tmp')
    try:
        with temporary.open('x', encoding='utf-8', newline='\n') as stream:
            stream.write(updated)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return {'status': 'configured', 'code': 'PINNED_CONTEXT7_REGISTERED'}


if __name__ == '__main__':
    try:
        value=json.load(sys.stdin)
        print(json.dumps(unregister(value) if value.get('action')=='unregister' else register(value)))
    except Exception:
        print(json.dumps({'status': 'blocked', 'code': 'BUILDER_MCP_REGISTRATION_FAILED'}))
        sys.exit(2)
