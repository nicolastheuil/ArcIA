"""Resolve public OCI artifacts, keeping anonymous registry bearer tokens in memory."""
import hashlib
import json
import urllib.parse
import urllib.request
from pin_vmware_images import ACCEPT


def request(url, headers=None):
    with urllib.request.urlopen(urllib.request.Request(url,headers=headers or {}),timeout=60) as response:
        content=response.read(8*1024*1024+1)
        if len(content)>8*1024*1024: raise ValueError('PUBLIC_ARTIFACT_SIZE_LIMIT')
        return content,response.headers


def resolve(reference):
    registry,path=reference.split('/',1)
    repository,tag=path.rsplit(':',1)
    if registry=='ghcr.io':
        base='https://ghcr.io/v2/'+repository
        auth='https://ghcr.io/token?'+urllib.parse.urlencode({'service':'ghcr.io','scope':'repository:'+repository+':pull'})
    elif registry=='docker.io':
        base='https://registry-1.docker.io/v2/'+repository
        auth='https://auth.docker.io/token?'+urllib.parse.urlencode({'service':'registry.docker.io','scope':'repository:'+repository+':pull'})
    else: raise ValueError('PUBLIC_REGISTRY_NOT_ALLOWED')
    token=json.loads(request(auth)[0])['token']
    headers={'Authorization':'Bearer '+token,'Accept':ACCEPT}
    content,response=request(base+'/manifests/'+tag,headers)
    digest='sha256:'+hashlib.sha256(content).hexdigest()
    if response.get('Docker-Content-Digest')!=digest: raise ValueError('OCI_DIGEST_MISMATCH')
    manifest=json.loads(content)
    if 'manifests' in manifest:
        selected=next(m for m in manifest['manifests'] if m.get('platform',{}).get('os')=='linux' and m.get('platform',{}).get('architecture')=='amd64')
        child,_=request(base+'/manifests/'+selected['digest'],headers)
        if 'sha256:'+hashlib.sha256(child).hexdigest()!=selected['digest']: raise ValueError('OCI_PLATFORM_HASH_MISMATCH')
        manifest=json.loads(child)
    config_content,_=request(base+'/blobs/'+manifest['config']['digest'],headers)
    if 'sha256:'+hashlib.sha256(config_content).hexdigest()!=manifest['config']['digest']: raise ValueError('OCI_CONFIG_HASH_MISMATCH')
    config=json.loads(config_content)
    if config['architecture']!='amd64' or config['os']!='linux': raise ValueError('AMD64_LINUX_IMAGE_REQUIRED')
    return {'source':reference,'pinned':registry+'/'+repository+'@'+digest,'image_digest':digest,
            'config':config.get('config',{})}
