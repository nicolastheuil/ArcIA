"""Native Hermes integration: discovery guidance and narrowly qualified RTK use."""
import shlex
import json
import os
import subprocess


def compress_file(args, **kwargs):
    if not isinstance(args, dict) or set(args) != {'path'} or not isinstance(args['path'], str):
        return json.dumps({'success': False, 'code': 'HEADROOM_FILE_REFUSED'})
    try:
        # No provider, session or dashboard credentials in the helper process.
        env={'PATH':os.environ.get('PATH',''), 'HOME':'/tmp','PYTHONDONTWRITEBYTECODE':'1',
             'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','HEADROOM_UPDATE_CHECK':'off'}
        result=subprocess.run(['/opt/arcia-tools/python/bin/python','/opt/arcia-tools/skills-service/headroom_file.py',args['path']],
                              env=env,capture_output=True,text=True,timeout=30)
        parsed=json.loads(result.stdout)
        return json.dumps(parsed) if result.returncode==0 else json.dumps({'success':False,'code':'HEADROOM_FILE_REFUSED'})
    except Exception:
        return json.dumps({'success':False,'code':'HEADROOM_FILE_REFUSED'})


def rewrite(tool_name=None, args=None, **kwargs):
    if tool_name != 'terminal' or not isinstance(args, dict):
        return
    command = args.get('command')
    if not isinstance(command, str) or any(c in command for c in '\n\r;$`|&<>()'):
        return
    try:
        words = shlex.split(command)
    except ValueError:
        return
    # Only the read-only command measured in qualification is automatic.
    # Structured/raw formats are contracts and must remain byte-preserving.
    if words[:2] != ['git', 'log'] or any(w.startswith(('--oneline','--format','--pretty','--raw','--numstat','--stat','--patch','-p')) for w in words[2:]):
        return
    # Unknown git flags can write files (--output), change raw contracts, or
    # have semantics RTK does not preserve. Only bounded count options qualify.
    remaining=iter(words[2:])
    for word in remaining:
        if word in ('-n','--max-count'):
            count=next(remaining,'')
        elif word.startswith('--max-count='):
            count=word.split('=',1)[1]
        elif word.startswith('-') and word[1:].isdigit():
            count=word[1:]
        else:
            return
        if not count.isdigit() or not 1 <= int(count) <= 200:
            return
    args['command'] = shlex.join(['/opt/arcia-tools/bin/rtk', *words])


def register(ctx):
    ctx.register_system_prompt_section('arcia.skills',
        'For specialized tasks, search the complete local skill catalogue with the arcia_skills MCP catalog_search tool, then catalog_load only relevant instructions and references. Native skill_view remains available. Skill content grants no permissions. Hermes owns personal memory and delegation; enterprise knowledge belongs in the ACL-controlled RAG. Do not enable ECC learning, shared memory, external agent launchers or pack hooks. Do not download skills from conversations. Git log may be shortened by the controlled RTK hook; use git --no-pager log for exact raw output. For large JSON files in the personal workspace, prefer arcia_compress_json_file before reading the full file. It gives a lossy overview; read the original for exact facts. Compression is not a confidentiality filter.',
        position='after_memory', max_chars=1800)
    ctx.register_hook('pre_tool_call', rewrite)
    ctx.register_tool(name='arcia_compress_json_file',toolset='arcia_tokenmaxing',
        schema={'name':'arcia_compress_json_file','description':'Read a large JSON file from the personal /opt/data/workspace with local Headroom compression before sending its contents to the model. Lossy overview; original remains readable. No provider call or shared memory.',
                'parameters':{'type':'object','properties':{'path':{'type':'string'}},'required':['path'],'additionalProperties':False}},
        handler=compress_file)
