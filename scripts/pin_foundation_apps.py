"""Explicit resolution of public qualification applications; never deploys."""
import hashlib
import json
from pathlib import Path
import re
import yaml
from public_oci import request,resolve

ROOT=Path(__file__).resolve().parents[1]


def main():
    lock=json.loads((ROOT/'versions.lock.yaml').read_text())
    url='https://github.com/cloudnative-pg/cloudnative-pg/releases/download/v1.30.1/cnpg-1.30.1.yaml'
    raw=request(url)[0]
    digest=hashlib.sha256(raw).hexdigest()
    source_url='https://raw.githubusercontent.com/cloudnative-pg/cloudnative-pg/'+lock['components']['cloudnative_pg']['revision']+'/releases/cnpg-1.30.1.yaml'
    if raw!=request(source_url)[0]:
        raise ValueError('CNPG_RELEASE_CHECKSUM_MISMATCH')
    operator=resolve('ghcr.io/cloudnative-pg/cloudnative-pg:1.30.1')
    revision=json.loads(request('https://api.github.com/repos/cloudnative-pg/artifacts/commits/main')[0])['sha']
    catalog_url='https://raw.githubusercontent.com/cloudnative-pg/artifacts/'+revision+'/image-catalogs/catalog-standard-trixie.yaml'
    catalog_raw=request(catalog_url)[0]
    pgref=next(i['image'] for i in yaml.safe_load(catalog_raw)['spec']['images'] if i['major']==18)
    postgres=resolve(pgref.split('@')[0])
    if postgres['image_digest']!=pgref.split('@')[1]: raise ValueError('POSTGRES_CATALOG_DIGEST_MISMATCH')
    hermes=resolve('docker.io/nousresearch/hermes-agent:v0.21.6')
    ingress=resolve('docker.io/library/nginx:1.31.6')
    # Resolve all sources before updating any artifact.
    rendered=raw.decode().replace('ghcr.io/cloudnative-pg/cloudnative-pg:1.30.1',operator['pinned'])
    directory=ROOT/'deploy/vendor/cnpg';directory.mkdir(parents=True,exist_ok=True)
    (directory/'operator.yaml').write_text(rendered,encoding='utf-8',newline='\n')
    license_url='https://raw.githubusercontent.com/cloudnative-pg/cloudnative-pg/'+lock['components']['cloudnative_pg']['revision']+'/LICENSE'
    (directory/'LICENSE.txt').write_bytes(request(license_url)[0])
    lock['components']['cloudnative_pg'].update(image_digest=operator['image_digest'],image_repository='ghcr.io/cloudnative-pg/cloudnative-pg')
    lock['components']['postgres_pgvector']={'version':pgref.split(':')[1].split('@')[0],
        'image':pgref,'image_digest':postgres['image_digest'],'catalog_source':catalog_url,
        'catalog_sha256':hashlib.sha256(catalog_raw).hexdigest(),'status':'pinned_not_deployed'}
    lock['components']['hermes'].update(image_digest=hermes['image_digest'],image=hermes['pinned'],
        image_labels=hermes['config'].get('Labels',{}),status='pinned_not_deployed')
    lock['components']['ingress']={'version':'1.31.6','image':ingress['pinned'],'image_digest':ingress['image_digest'],
        'source':'https://github.com/nginx/nginx/releases/tag/release-1.31.6','status':'pinned_not_deployed'}
    lock['cnpg_source']={'url':url,'upstream_sha256':digest,
        'rendered_sha256':hashlib.sha256(rendered.encode()).hexdigest()}
    (ROOT/'versions.lock.yaml').write_text(json.dumps(lock,indent=2)+'\n',newline='\n')
    print('FOUNDATION_APPLICATION_SOURCES_AND_DIGESTS_PINNED')


if __name__=='__main__': main()
