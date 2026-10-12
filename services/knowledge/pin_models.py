"""Engineer-only refresh of public model hashes; never run in agent runtime."""
import hashlib
import json
import time
import urllib.request
from pathlib import Path

MODELS = {
    'dense': ('intfloat/multilingual-e5-small', '614241f622f53c4eeff9890bdc4f31cfecc418b3', 384),
    'late': ('lightonai/mLateOn', 'bbd883ae1fadb563056ff73b1061ae8172a3fcda', 128),
}

def fetch(url):
    for attempt in range(5):
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                return response.read(50*1024*1024)
        except OSError:
            if attempt == 4: raise
            time.sleep(1)

def main():
    out={}
    for key,(repo,revision,dimension) in MODELS.items():
        value=json.loads(fetch('https://huggingface.co/api/models/'+repo+'/revision/'+revision+'?blobs=true'))
        files={}
        for entry in value['siblings']:
            name=entry['rfilename']
            if not name.endswith(('.json','.safetensors','.txt','.model')) or name.startswith(('onnx/','openvino/')):continue
            if entry.get('lfs'):
                digest=entry['lfs']['sha256'];size=entry['lfs']['size']
            else:
                data=fetch('https://huggingface.co/'+repo+'/resolve/'+revision+'/'+name)
                digest=hashlib.sha256(data).hexdigest();size=len(data)
            files[name]={'sha256':digest,'size':size}
        out[key]={'repository':repo,'revision':revision,'dimension':dimension,'files':files}
    Path(__file__).with_name('models.lock.json').write_text(json.dumps(out,indent=2)+'\n')
    print('PUBLIC_MODEL_MANIFEST_WRITTEN')

if __name__=='__main__':main()
