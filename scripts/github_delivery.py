"""Read-only delivery status. Credentials remain inside the protected process."""
import json
import subprocess
import urllib.request

REPOSITORY='nicolastheuil/ArcIA'

def main():
    result=subprocess.run(['git','credential','fill'],input=b'protocol=https\nhost=github.com\n\n',
        capture_output=True,timeout=30,check=True)
    credentials=dict(line.split('=',1) for line in result.stdout.decode().splitlines() if '=' in line)
    def get(path):
        req=urllib.request.Request('https://api.github.com/repos/'+REPOSITORY+path,
            headers={'Authorization':'Bearer '+credentials['password'],'Accept':'application/vnd.github+json',
                'User-Agent':'arcia-engineer-delivery-status'})
        with urllib.request.urlopen(req,timeout=30) as response:return json.load(response)
    branch=get('/branches/main')
    runs=get('/actions/runs?branch=main&event=push&per_page=3')['workflow_runs']
    print(json.dumps({'main_sha':branch['commit']['sha'],'runs':[
        {key:run[key] for key in ('id','head_sha','status','conclusion','html_url')} for run in runs]}))

if __name__=='__main__':
    try:main()
    except Exception as exc:print(json.dumps({'status':'unavailable','error_type':type(exc).__name__}))
