"""Bounded MCP smoke test. Only a generic public documentation request."""
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
import time


def verify():
    entry = Path(os.environ['LOCALAPPDATA'])/'ArcIA-Builder/npm/node_modules/@upstash/context7-mcp/dist/index.js'
    process = subprocess.Popen([shutil.which('node'), str(entry)], stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8',
        env=dict(os.environ, DISABLE_TELEMETRY='1'))
    messages = queue.Queue()
    def read():
        for line in process.stdout:
            try: messages.put(json.loads(line))
            except ValueError: pass
    threading.Thread(target=read, daemon=True).start()
    threading.Thread(target=lambda: process.stderr.read(), daemon=True).start()
    def call(identifier, method, params):
        process.stdin.write(json.dumps({'jsonrpc':'2.0','id':identifier,'method':method,'params':params})+'\n')
        process.stdin.flush()
        deadline=time.monotonic()+60
        while time.monotonic()<deadline:
            response=messages.get(timeout=max(0.1,deadline-time.monotonic()))
            if response.get('id')==identifier:
                if 'error' in response: raise ValueError('MCP_RPC_FAILED')
                return response['result']
        raise ValueError('MCP_TIMEOUT')
    try:
        initialize=call(1,'initialize',{'protocolVersion':'2025-03-26',
            'capabilities':{},'clientInfo':{'name':'arcia-synthetic-probe','version':'1.0'}})
        process.stdin.write('{"jsonrpc":"2.0","method":"notifications/initialized"}\n');process.stdin.flush()
        listing=call(2,'tools/list',{})
        names={t['name'] for t in listing['tools']}
        if not {'resolve-library-id','query-docs'}<=names:
            raise ValueError('CONTEXT7_TOOLS_MISSING')
        result=call(3,'tools/call',{'name':'resolve-library-id','arguments':{
            'libraryName':'PostgreSQL','query':'Official PostgreSQL full text search documentation'}})
        content=' '.join(x.get('text','') for x in result.get('content',[])).casefold()
        remote=not result.get('isError',False) and 'library id' in content and 'postgres' in content
        return {'status':'verified' if remote else 'partial','code':'CONTEXT7_MCP_AND_GENERIC_QUERY_VERIFIED' if remote else 'CONTEXT7_MCP_READY_REMOTE_QUERY_NOT_VERIFIED',
                'initialize':bool(initialize),'required_tools_present':True,'generic_remote_query':remote}
    finally:
        process.terminate()
        try: process.wait(timeout=10)
        except subprocess.TimeoutExpired: process.kill();process.wait()


if __name__=='__main__':
    try: result=verify()
    except Exception: result={'status':'blocked','code':'CONTEXT7_SMOKE_TEST_FAILED'}
    root=Path(os.environ['LOCALAPPDATA'])/'ArcIA-Builder'
    root.mkdir(exist_ok=True)
    (root/'context7-status.json').write_text(json.dumps(result),encoding='utf-8')
    print(json.dumps(result))
    sys.exit(0 if result['status']=='verified' else 2)
