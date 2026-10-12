"""Resolve only public VMware foundation sources and OCI images; never deploy."""
import hashlib
import json
from pathlib import Path
import re
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
CPI_REVISION = '26afdddaa7c641f50ec5823c3e4fbe390ea894d4'
CPI_VERSION = 'v1.37.0'
CSI_REVISION = '27ec91d0a0fc820724cc5d7a0a2f69d12bc4ff34'
SOURCES = {
    'cpi-daemonset.yaml': ('kubernetes/cloud-provider-vsphere', CPI_REVISION,
        'manifests/controller-manager/vsphere-cloud-controller-manager-ds.yaml'),
    'cpi-roles.yaml': ('kubernetes/cloud-provider-vsphere', CPI_REVISION,
        'manifests/controller-manager/cloud-controller-manager-roles.yaml'),
    'cpi-bindings.yaml': ('kubernetes/cloud-provider-vsphere', CPI_REVISION,
        'manifests/controller-manager/cloud-controller-manager-role-bindings.yaml'),
    'csi-driver.yaml': ('kubernetes-sigs/vsphere-csi-driver', CSI_REVISION,
        'manifests/vanilla/vsphere-csi-driver.yaml'),
}
ACCEPT = ', '.join(('application/vnd.oci.image.index.v1+json',
    'application/vnd.docker.distribution.manifest.list.v2+json',
    'application/vnd.oci.image.manifest.v1+json', 'application/vnd.docker.distribution.manifest.v2+json'))


def fetch(url, accept=None):
    request = urllib.request.Request(url, headers={'User-Agent': 'ArcIA-public-artifact-resolver/1',
                                                   'Accept': accept or '*/*'})
    with urllib.request.urlopen(request, timeout=45) as response:
        data = response.read(4*1024*1024+1)
        if len(data) > 4*1024*1024: raise ValueError('ARTIFACT_SIZE_LIMIT')
        return data, response.headers.get('Docker-Content-Digest')


def resolve(reference):
    if not re.fullmatch(r'registry\.k8s\.io/[a-z0-9_./-]+:v[0-9.]+', reference):
        raise ValueError('UNEXPECTED_PUBLIC_REGISTRY')
    repository, tag = reference.removeprefix('registry.k8s.io/').rsplit(':', 1)
    data, declared = fetch('https://registry.k8s.io/v2/'+repository+'/manifests/'+tag, ACCEPT)
    digest = 'sha256:'+hashlib.sha256(data).hexdigest()
    if declared and declared != digest: raise ValueError('REGISTRY_DIGEST_MISMATCH')
    document = json.loads(data)
    # Index manifests must explicitly contain the target platform; retain the index digest.
    if 'manifests' in document:
        if not any(m.get('platform', {}).get('os') == 'linux' and
                   m.get('platform', {}).get('architecture') == 'amd64' for m in document['manifests']):
            raise ValueError('AMD64_IMAGE_MISSING')
    elif not document.get('config', {}).get('digest') or not document.get('layers'):
        raise ValueError('INVALID_OCI_MANIFEST')
    return {'source': reference, 'digest': digest,
            'pinned': 'registry.k8s.io/'+repository+'@'+digest}


def main():
    destination = ROOT/'deploy/vendor/vmware'
    lock = json.loads((ROOT/'versions.lock.yaml').read_text())
    documents, sources, references = {}, {}, set()
    # Resolve everything before writing, so a registry failure cannot half-update the lock.
    for name, (repository, revision, path) in SOURCES.items():
        url = 'https://raw.githubusercontent.com/'+repository+'/'+revision+'/'+path
        data, _ = fetch(url)
        text = data.decode('utf-8')
        documents[name] = text
        references.update(re.findall(r'^\s*image:\s*(\S+)\s*$', text, re.M))
        sources[name] = {'url': url, 'revision': revision,
                         'upstream_sha256': hashlib.sha256(data).hexdigest()}
    images = {reference: resolve(reference) for reference in sorted(references)}
    licenses = {}
    for prefix, (repository, revision, _) in (('cpi', SOURCES['cpi-daemonset.yaml']),
                                            ('csi', SOURCES['csi-driver.yaml'])):
        licenses[prefix+'-LICENSE.txt'] = fetch('https://raw.githubusercontent.com/'+repository+'/'+revision+'/LICENSE')[0]
    for name, document in documents.items():
        for reference, image in images.items():
            document = document.replace('image: '+reference, 'image: '+image['pinned'])
        documents[name] = document
        sources[name]['rendered_sha256'] = hashlib.sha256(document.encode()).hexdigest()
    cpi = images['registry.k8s.io/cloud-pv-vsphere/cloud-provider-vsphere:'+CPI_VERSION]
    lock['components']['vsphere_cpi'] = {'version': CPI_VERSION, 'revision': CPI_REVISION,
        'source': 'https://github.com/kubernetes/cloud-provider-vsphere/releases/tag/'+CPI_VERSION,
        'image_digest': cpi['digest'], 'image_repository': cpi['pinned'].split('@')[0],
        'status': 'source_verified_not_qualified'}
    lock['components']['vsphere_csi']['image_digest'] = images['registry.k8s.io/csi-vsphere/driver:v3.7.3']['digest']
    lock['vmware_foundation'] = {'sources': sources, 'images': list(images.values()),
        'qualification_status': 'not_deployed_not_qualified'}
    destination.mkdir(parents=True, exist_ok=True)
    for name, document in documents.items(): (destination/name).write_text(document, encoding='utf-8', newline='\n')
    for name, data in licenses.items(): (destination/name).write_bytes(data)
    (ROOT/'versions.lock.yaml').write_text(json.dumps(lock, indent=2)+'\n', encoding='utf-8', newline='\n')
    print(json.dumps({'status': 'sources_pinned', 'manifests': len(documents), 'images': len(images), 'deployed': False}))


if __name__ == '__main__':
    try: main()
    except Exception:
        print('{"status":"blocked","code":"PUBLIC_ARTIFACT_RESOLUTION_FAILED","deployed":false}')
        sys.exit(2)
