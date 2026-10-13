"""Explicit deletion of fixed personal slots whose Keycloak subject no longer exists.

No automatic GC: disabled users and unallocated slots are always retained.
Plans and results contain private resource identifiers and stay protected.
"""
import hashlib
import json
import re
import time
from urllib.error import HTTPError
from urllib.parse import quote


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def missing_user(admin, subject):
    if not isinstance(subject, str) or not subject:
        raise ValueError('PERSONAL_CLEANUP_SUBJECT_REQUIRED')
    try:
        admin.resource('/users/' + quote(subject, safe=''))
    except HTTPError as exc:
        exc.close()
        if exc.code == 404:
            return True
        raise
    return False


def inventory(admin, owned, kube, operation):
    realm = admin.resource()
    if realm.get('attributes', {}).get('arcia.operation-id') != operation:
        raise ValueError('PERSONAL_CLEANUP_FOREIGN_REALM')
    config = owned('ConfigMap', 'portal-config', 'arcia-access', operation)
    settings = json.loads(config['data']['portal.json'])
    candidates = []
    for slot in settings['slots']:
        if (not re.fullmatch(r'p(?:0[1-9]|[12][0-9]|3[0-2])', slot['id']) or
                slot['namespace'] != 'arcia-user-' + slot['id']):
            raise ValueError('PERSONAL_CLEANUP_SLOT_SCOPE')
        ns = slot['namespace']
        binding = owned('ConfigMap', 'slot-binding', ns, operation)
        record = json.loads(binding['data']['binding.json'])
        if not record:
            continue
        if record.get('issuer') != 'https://' + settings['hostname'] + '/identity/realms/arcia':
            raise ValueError('PERSONAL_CLEANUP_FOREIGN_ISSUER')
        if not missing_user(admin, record.get('subject')):
            continue
        namespace = owned('Namespace', ns, None, operation)
        if namespace['metadata'].get('labels', {}).get('arcia.io/personal-pool') != 'true':
            raise ValueError('PERSONAL_CLEANUP_NAMESPACE_SCOPE')
        claims = json.loads(kube('get', 'pvc', '-n', ns, '-o', 'json'))['items']
        if {c['metadata']['name'] for c in claims} != {'hermes-pilot-state', 'hermes-tools'}:
            raise ValueError('PERSONAL_CLEANUP_UNEXPECTED_CLAIMS')
        volumes = []
        for claim in claims:
            if claim['metadata'].get('annotations', {}).get('arcia.io/operation-id') != operation:
                raise ValueError('PERSONAL_CLEANUP_FOREIGN_CLAIM')
            name = claim['spec'].get('volumeName')
            pv = json.loads(kube('get', 'pv', name, '-o', 'json')) if name else None
            if pv:
                ref = pv['spec'].get('claimRef', {})
                if (ref.get('uid') != claim['metadata']['uid'] or ref.get('namespace') != ns or
                        ref.get('name') != claim['metadata']['name'] or
                        pv['spec'].get('persistentVolumeReclaimPolicy') not in ('Delete', 'Retain') or
                        pv['spec'].get('csi', {}).get('driver') != 'csi.vsphere.vmware.com'):
                    raise ValueError('PERSONAL_CLEANUP_VOLUME_SCOPE')
            volumes.append({'claim_name': claim['metadata']['name'], 'claim_uid': claim['metadata']['uid'],
                            'pv_name': name, 'pv_uid': pv['metadata']['uid'] if pv else None,
                            'pv_version': pv['metadata']['resourceVersion'] if pv else None,
                            'reclaim_policy': pv['spec']['persistentVolumeReclaimPolicy'] if pv else None})
        candidates.append({'namespace': ns, 'namespace_uid': namespace['metadata']['uid'],
                           'namespace_version': namespace['metadata']['resourceVersion'],
                           'binding_uid': binding['metadata']['uid'], 'binding_version': binding['metadata']['resourceVersion'],
                           'binding_digest': digest(binding['data']), 'subject': record['subject'],
                           'volumes': sorted(volumes, key=lambda v: v['claim_name'])})
    return {'realm_id': realm['id'], 'portal_config_uid': config['metadata']['uid'],
            'portal_config_digest': digest(config['data']), 'candidates': candidates}


def plan(admin, owned, kube, operation, now=None):
    created = int(time.time() if now is None else now)
    result = {'operation_id': operation, 'created_at': created, 'expires_at': created + 600,
              'scope': 'delete_data_for_missing_keycloak_users_only', **inventory(admin, owned, kube, operation)}
    result['plan_sha256'] = digest(result)
    return result


def apply(admin, owned, kube, operation, proposed, authorized_hash, approval_mode, now=None):
    if approval_mode != 'operator_exception_for_named_personal_cleanup' or not authorized_hash:
        raise ValueError('PERSONAL_CLEANUP_EXPLICIT_EXCEPTION_REQUIRED')
    current_time = int(time.time() if now is None else now)
    if (proposed.get('operation_id') != operation or proposed.get('plan_sha256') != authorized_hash or
            not proposed['created_at'] <= current_time < proposed['expires_at'] or
            proposed != plan(admin, owned, kube, operation, proposed['created_at'])):
        raise ValueError('PERSONAL_CLEANUP_STALE_OR_CHANGED_PLAN')
    if not proposed['candidates']:
        return {'deleted_slots': 0, 'deleted_claims': 0, 'deleted_pvs': 0, 'portal_stopped': False}
    owned('Deployment', 'arcia-portal', 'arcia-access', operation)
    kube('scale', 'deployment/arcia-portal', '-n', 'arcia-access', '--replicas=0')
    kube('wait', 'pods', '-l', 'app=arcia-portal', '-n', 'arcia-access', '--for=delete', '--timeout=90s', timeout=100)
    # Re-read all subjects and bindings after stopping allocation, before deleting anything.
    if inventory(admin, owned, kube, operation) != {k: proposed[k] for k in
            ('realm_id', 'portal_config_uid', 'portal_config_digest', 'candidates')}:
        raise ValueError('PERSONAL_CLEANUP_POST_STOP_DRIFT')
    for candidate in proposed['candidates']:
        for volume in candidate['volumes']:
            if volume['reclaim_policy'] == 'Retain':
                kube('patch', 'pv', volume['pv_name'], '--type=merge', '-p', json.dumps({
                    'metadata': {'uid': volume['pv_uid'], 'resourceVersion': volume['pv_version']},
                    'spec': {'persistentVolumeReclaimPolicy': 'Delete'}}))
        kube('delete', '--raw', '/api/v1/namespaces/' + candidate['namespace'], '-f', '-',
             document={'apiVersion': 'v1', 'kind': 'DeleteOptions', 'propagationPolicy': 'Foreground',
                       'preconditions': {'uid': candidate['namespace_uid'], 'resourceVersion': candidate['namespace_version']}})
    for candidate in proposed['candidates']:
        kube('wait', 'namespace/' + candidate['namespace'], '--for=delete', '--timeout=300s', timeout=320)
        for volume in candidate['volumes']:
            if volume['pv_name']:
                kube('wait', 'pv/' + volume['pv_name'], '--for=delete', '--timeout=300s', timeout=320)
    return {'deleted_slots': len(proposed['candidates']),
            'deleted_claims': sum(len(c['volumes']) for c in proposed['candidates']),
            'deleted_pvs': sum(bool(v['pv_name']) for c in proposed['candidates'] for v in c['volumes']),
            'portal_stopped': True, 'disabled_users_deleted': False, 'teams_approval_verified': False,
            'approval_mode': approval_mode}
