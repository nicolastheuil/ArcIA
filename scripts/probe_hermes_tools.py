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
    import sys
    sys.path.insert(0,str(ROOT/'skills-service'))
    from catalog import Catalog
    catalog=Catalog()
    expected=json.loads((ROOT/'catalog/index.json').read_text())
    installed=json.loads((ROOT/'installed.json').read_text())
    checks['rich_skills_catalogue_present']=len(catalog.entries)==installed['skills_count'] and len(catalog.entries)>500
    checks['all_skill_sources_present']={e['provider'] for e in catalog.entries.values()}=={'hermes','ecc','superpowers','vercel'}
    checks['catalogue_mcp_configured']=settings['mcp_servers']['arcia_skills']['args']==['/opt/arcia-tools/skills-service/server.py']
    checks['native_memory_owner']=settings['memory']['memory_enabled'] is True and settings['memory']['user_profile_enabled'] is True
    checks['native_skills_available']=listing.returncode==0 and 'arcia-skills' in listing.stdout and 'pdf' in listing.stdout
    checks['skills_index_digest_verified']=hashlib.sha256((ROOT/'catalog/index.json').read_bytes()).hexdigest()==installed['skills_index_sha256']
    checks['catalogue_research_discovery']=any('research' in x['name'] for x in catalog.search('research',provider='ecc')['matches'])
    checks['catalogue_writing_discovery']=any('writing' in x['name'] for x in catalog.search('rédaction',provider='ecc')['matches'])
    checks['catalogue_all_instructions_hash_valid']=all(hashlib.sha256((ROOT/'catalog/content'/e['provider']/e['path']/'SKILL.md').read_bytes()).hexdigest()==e['files']['SKILL.md'] for e in catalog.entries.values())
    checks['catalogue_all_have_credits_licences']=all(e.get('credit') and e.get('license') and e.get('license_url') for e in catalog.entries.values())
    checks['catalogue_load_all_sources']=all(catalog.load(next(e['id'] for e in catalog.entries.values() if e['provider']==provider))['content'] for provider in ('hermes','ecc','superpowers','vercel'))
    checks['catalogue_path_traversal_denied']=False
    try:catalog.load(next(iter(catalog.entries)),'../../config.yaml')
    except ValueError:checks['catalogue_path_traversal_denied']=True
    checks['catalogue_unknown_source_denied']=False
    try:catalog.load('untrusted:arbitrary')
    except ValueError:checks['catalogue_unknown_source_denied']=True
    process_skills=subprocess.Popen(['/opt/hermes/.venv/bin/python',str(ROOT/'skills-service/server.py')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    def skills_rpc(identifier,method,params=None):
        process_skills.stdin.write(json.dumps({'jsonrpc':'2.0','id':identifier,'method':method,'params':params or {}})+'\n');process_skills.stdin.flush()
        return json.loads(process_skills.stdout.readline())
    try:
        checks['catalogue_mcp_initialize']=skills_rpc(1,'initialize',{'protocolVersion':'2024-11-05'})['result']['serverInfo']['name']=='arcia-skills'
        checks['catalogue_mcp_tools']=len(skills_rpc(2,'tools/list')['result']['tools'])==3
        hit=skills_rpc(3,'tools/call',{'name':'catalog_search','arguments':{'query':'research','provider':'ecc'}})
        match=json.loads(hit['result']['content'][0]['text'])['matches'][0]
        loaded=skills_rpc(4,'tools/call',{'name':'catalog_load','arguments':{'id':match['id']}})
        checks['catalogue_mcp_search_load']=bool(json.loads(loaded['result']['content'][0]['text'])['content'])
        checks['catalogue_mcp_arbitrary_options_denied']='error' in skills_rpc(5,'tools/call',{'name':'catalog_search','arguments':{'url':'https://example.invalid'}})
    finally:
        process_skills.terminate();process_skills.communicate(timeout=10)
    native_probe="""import sys,json,importlib.util,tempfile
from pathlib import Path
sys.path.insert(0,'/opt/hermes')
from hermes_cli import plugins
manager=plugins.get_plugin_manager();manager.discover_and_load()
loaded=next((p for p in manager.list_plugins() if p['name']=='arcia-platform'),{})
checks={'native_platform_plugin_loaded':loaded.get('enabled') is True and loaded.get('error') is None,
 'native_platform_plugin_tool_registered':loaded.get('tools')==1,
 'native_discovery_prompt_registered':any('catalog_search' in str(s) for s in plugins.render_system_prompt_sections({}))}
args={'command':'git log -n 15'}
plugins.invoke_hook('pre_tool_call',tool_name='terminal',args=args)
checks['native_rtk_hook_rewrites_qualified_command']=args['command'].startswith('/opt/arcia-tools/bin/rtk git log')
args={'command':'git push'};plugins.invoke_hook('pre_tool_call',tool_name='terminal',args=args)
checks['native_rtk_hook_preserves_writes']=args['command']=='git push'
spec=importlib.util.spec_from_file_location('arcia_platform_probe','/opt/data/plugins/arcia-platform/__init__.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
workspace=Path('/opt/data/workspace');workspace.mkdir(exist_ok=True)
items=[{'id':i,'state':'ok','detail':'synthetic repeated event'} for i in range(150)]
items[67]={'id':67,'state':'FATAL','detail':'SYNTHETIC_CRITICAL_MARKER_67'}
with tempfile.NamedTemporaryFile(mode='w',suffix='.json',prefix='.arcia-token-',dir=workspace) as f:
 json.dump(items,f);f.flush();value=json.loads(module.compress_file({'path':f.name}))
 checks['headroom_native_tool_reduces_json']=value.get('success') is True and value.get('compressed') is True
 checks['headroom_native_tool_preserves_error']= 'SYNTHETIC_CRITICAL_MARKER_67' in value.get('content','')
 checks['headroom_original_remains_readable']=Path(f.name).is_file() and json.loads(Path(f.name).read_text())==items
denied=json.loads(module.compress_file({'path':'/opt/data/config.yaml'}))
checks['headroom_private_configuration_read_denied']=denied.get('success') is False
print(json.dumps(checks))
"""
    native=subprocess.run(['/opt/hermes/.venv/bin/python','-c',native_probe],capture_output=True,text=True,timeout=90)
    if native.returncode==0:checks.update(json.loads(native.stdout))
    else:checks['native_platform_plugin_qualification']=False
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
            arguments=globals().get('ARCIA_TOOLS_KNOWLEDGE_ARGUMENTS',{'query':'restoreSnapshot','version':'1'})
            result=call(3,'tools/call',{'name':'knowledge_search','arguments':arguments})
            content=json.loads(result['content'][0]['text'])
            checks['knowledge_mcp_real_search']=not result.get('isError',False) and bool(content['results'])
        finally:
            process.terminate();process.wait(timeout=10)
    return {'checks':checks,'passed':all(checks.values()),'catalog_sha256':manifest['catalog_sha256']}


if __name__=='__main__': print(json.dumps(main()))
