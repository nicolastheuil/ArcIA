"""Synthetic verification executed inside the Hermes container; booleans only."""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import queue
import socket
import subprocess
import threading
import time
import yaml

ROOT=Path('/opt/arcia-tools')


def main():
    checks={}
    def command(name,*args):
        result=subprocess.run([str(ROOT/'bin'/name),*args],capture_output=True,text=True,timeout=90,
            env=dict(os.environ,DISABLE_TELEMETRY='1',HOME='/opt/data'))
        return result.returncode==0,result.stdout+result.stderr
    for name,version in [('skills','1.7.2'),('lintlang','0.8.2'),('rtk','0.51.0'),('certbot','5.8.0')]:
        ok,content=command(name,'--version');checks[name+'_version']=ok and version in content
    headroom=subprocess.run([str(ROOT/'python/bin/python'),'-c',
        "import headroom,importlib.metadata;print(importlib.metadata.version('headroom-ai'))"],capture_output=True,text=True,timeout=90)
    checks['headroom_import_version']=headroom.returncode==0 and '0.40.0' in headroom.stdout
    ok,listing=command('lintlang','scan',str(ROOT/'AGENTS.md'),str(ROOT/'role.md'),'--format','json')
    checks['lintlang_synthetic_scan']=ok and bool(listing)
    ok,skills=command('skills','--help');checks['skills_cli_executable']=ok
    settings=yaml.safe_load(Path('/opt/data/config.yaml').read_text())
    checks['native_mcp_configured']=settings['mcp_servers']['arcia_context7']['command']==str(ROOT/'bin/context7')
    checks['native_skills_configured']=str(ROOT/'skills') in settings['skills']['external_dirs']
    listing=subprocess.run(['/opt/hermes/.venv/bin/hermes','skills','list'],capture_output=True,text=True,timeout=90,
        env=dict(os.environ,COLUMNS='300'))
    names=['verification-before-completion','systematic-debugging','receiving-code-review','test-driven-development','python-patterns','postgres-patterns']
    checks['six_skills_discovered_by_hermes']=listing.returncode==0 and all(name in listing.stdout for name in names)
    try:
        (ROOT/'unexpected-write').write_text('synthetic');checks['tools_read_only']=False
    except OSError: checks['tools_read_only']=True
    try:
        socket.create_connection(('1.1.1.1',443),timeout=3).close();checks['direct_public_egress_denied']=False
    except OSError: checks['direct_public_egress_denied']=True
    process=subprocess.Popen([str(ROOT/'bin/context7')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,text=True,env=dict(os.environ,**settings['mcp_servers']['arcia_context7']['env']))
    messages=queue.Queue()
    def read():
        for line in process.stdout:
            try:messages.put(json.loads(line))
            except ValueError:pass
    threading.Thread(target=read,daemon=True).start()
    threading.Thread(target=lambda:process.stderr.read(),daemon=True).start()
    def call(identifier,method,params):
        process.stdin.write(json.dumps({'jsonrpc':'2.0','id':identifier,'method':method,'params':params})+'\n');process.stdin.flush()
        deadline=time.monotonic()+60
        while time.monotonic()<deadline:
            result=messages.get(timeout=max(.1,deadline-time.monotonic()))
            if result.get('id')==identifier:
                if 'error' in result:raise ValueError('MCP_PROBE_FAILED')
                return result['result']
        raise ValueError('MCP_PROBE_TIMEOUT')
    try:
        checks['context7_initialize']=bool(call(1,'initialize',{'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'arcia-synthetic-probe','version':'1'}}))
        process.stdin.write('{"jsonrpc":"2.0","method":"notifications/initialized"}\n');process.stdin.flush()
        tools=call(2,'tools/list',{})
        checks['context7_tools_list']={'resolve-library-id','query-docs'}<={t['name'] for t in tools['tools']}
        result=call(3,'tools/call',{'name':'resolve-library-id','arguments':{'libraryName':'PostgreSQL','query':'Official PostgreSQL full text search documentation'}})
        content=' '.join(item.get('text','') for item in result.get('content',[])).lower()
        checks['context7_unfiltered_external_query_blocked']='403' in content or result.get('isError',False)
    finally:
        process.terminate()
        try:process.wait(timeout=10)
        except subprocess.TimeoutExpired:process.kill();process.wait()
    manifest=json.loads((ROOT/'installed.json').read_text())
    checks['omniroute_package_version']=json.loads((ROOT/'npm/node_modules/omniroute/package.json').read_text())['version']=='3.8.51'
    route=subprocess.run(['/usr/local/bin/node',str(ROOT/'npm/node_modules/omniroute/bin/omniroute.mjs'),'--version'],
        capture_output=True,text=True,timeout=30,env=dict(os.environ,CI='1',OMNIROUTE_NO_UPDATE_NOTIFIER='1'))
    checks['omniroute_cli_version']=route.returncode==0 and '3.8.51' in route.stdout
    client=settings['mcp_servers'].get('arcia_knowledge')
    if globals().get('ARCIA_REQUIRE_KNOWLEDGE',True):
        checks['knowledge_native_mcp_configured']=bool(client)
    if client:
        process=subprocess.Popen([client['command'],*client['args']],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        messages=queue.Queue()
        threading.Thread(target=read,daemon=True).start()
        threading.Thread(target=lambda:process.stderr.read(),daemon=True).start()
        try:
            checks['knowledge_mcp_initialize']=bool(call(1,'initialize',{'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'arcia-probe','version':'1'}}))
            tools=call(2,'tools/list',{})
            checks['knowledge_mcp_read_only_tools']={t['name'] for t in tools['tools']}=={'knowledge_search','knowledge_download_asset'}
            result=call(3,'tools/call',{'name':'knowledge_search','arguments':{'query':'restoreSnapshot','version':'1'}})
            content=json.loads(result['content'][0]['text'])
            checks['knowledge_mcp_real_search']=not result.get('isError',False) and bool(content['results'])
        finally:
            process.terminate();process.wait(timeout=10)
    return {'checks':checks,'passed':all(checks.values()),'catalog_sha256':manifest['catalog_sha256']}


if __name__=='__main__': print(json.dumps(main()))
