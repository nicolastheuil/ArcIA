"""Named realm-admin recovery and tenant-specific user admission; protected I/O only."""
from urllib.parse import quote
from uuid import UUID
import hashlib
import json
import time

MAPPER_NAME = 'arcia-tenant-users'
MAPPER_TYPE = 'oidc-hardcoded-role-idp-mapper'


def plan_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def owned_realm(admin, operation):
    realm = admin.resource()
    if realm.get('attributes', {}).get('arcia.operation-id') != operation:
        raise ValueError('IDENTITY_ACCESS_FOREIGN_REALM')
    return realm


def recover_admin(admin, operation, user_id, username):
    owned_realm(admin, operation)
    user = admin.resource('/users/' + quote(user_id, safe=''))
    if (user.get('id') != user_id or user.get('username') != username or
            user.get('enabled') is not True or user.get('serviceAccountClientId')):
        raise ValueError('IDENTITY_ACCESS_RECOVERY_TARGET_REFUSED')
    client = admin.client('realm-management')
    path = '/users/' + quote(user_id, safe='') + '/role-mappings/clients/' + quote(client['id'], safe='')
    role = admin.resource('/clients/' + quote(client['id'], safe='') + '/roles/realm-admin')
    if role.get('name') != 'realm-admin' or role.get('clientRole') is not True or role.get('containerId') != client['id']:
        raise ValueError('IDENTITY_ACCESS_RECOVERY_ROLE_REFUSED')
    before = admin.resource(path)
    changed = not any(r.get('id') == role['id'] for r in before)
    if changed:
        admin.resource(path, 'POST', [role])
    effective = admin.resource(path + '/composite')
    if not any(r.get('id') == role['id'] for r in effective):
        raise ValueError('IDENTITY_ACCESS_RECOVERY_READBACK_FAILED')
    after = admin.resource('/users/' + quote(user_id, safe=''))
    if after.get('id') != user_id or after.get('username') != username:
        raise ValueError('IDENTITY_ACCESS_RECOVERY_IDENTITY_CHANGED')
    return {'realm_admin_restored': True, 'role_mapping_changed': changed,
            'password_modified': False, 'mfa_modified': False, 'user_recreated': False}


def tenant_mapper(admin, operation, alias, expected_tenant, apply=False):
    owned_realm(admin, operation)
    tenant = str(UUID(expected_tenant))
    path = '/identity-provider/instances/' + quote(alias, safe='')
    provider = admin.resource(path)
    if (provider.get('alias') != alias or provider.get('providerId') != 'microsoft' or
            provider.get('enabled') is not True or provider.get('linkOnly') or
            provider.get('config', {}).get('tenantId', '').lower() != tenant):
        raise ValueError('IDENTITY_ACCESS_TENANT_PROVIDER_REFUSED')
    role = admin.resource('/roles/ArcIA.User')
    if role.get('name') != 'ArcIA.User' or role.get('clientRole') or role.get('composite'):
        raise ValueError('IDENTITY_ACCESS_USER_ROLE_REFUSED')
    # Keycloak resolves a dotted mapper role against a matching client first.
    # Refuse a client named ArcIA rather than granting a similarly named client role.
    if admin.resource('/clients?clientId=ArcIA'):
        raise ValueError('IDENTITY_ACCESS_ROLE_NAMESPACE_COLLISION')
    desired = {'name': MAPPER_NAME, 'identityProviderAlias': alias,
               'identityProviderMapper': MAPPER_TYPE, 'config': {'syncMode': 'FORCE', 'role': 'ArcIA.User'}}
    matches = [m for m in admin.resource(path + '/mappers') if m.get('name') == MAPPER_NAME]
    if len(matches) > 1:
        raise ValueError('IDENTITY_ACCESS_MAPPER_AMBIGUOUS')
    existing = matches[0] if matches else None
    if existing and (existing.get('identityProviderAlias') != alias or
                     existing.get('identityProviderMapper') != MAPPER_TYPE or
                     existing.get('config', {}).get('role') != 'ArcIA.User'):
        raise ValueError('IDENTITY_ACCESS_FOREIGN_MAPPER')
    changed = not existing or any(existing.get(k) != v for k, v in desired.items())
    if apply and changed:
        if existing:
            admin.resource(path + '/mappers/' + quote(existing['id'], safe=''), 'PUT', {**desired, 'id': existing['id']})
        else:
            admin.resource(path + '/mappers', 'POST', desired)
    if apply:
        current = [m for m in admin.resource(path + '/mappers') if m.get('name') == MAPPER_NAME]
        if len(current) != 1 or any(current[0].get(k) != v for k, v in desired.items()):
            raise ValueError('IDENTITY_ACCESS_MAPPER_READBACK_FAILED')
    return {'tenant_user_admission_configured': bool(apply or not changed), 'mapper_change_required': changed,
            'mapper_changed': bool(apply and changed),
            'assigned_role': 'ArcIA.User', 'tenant_admission_admin_roles_granted': False,
            'local_registration_changed': False, 'automatic_email_linking_enabled': False}


def repair_plan(admin, operation, username, alias, expected_tenant, now=None):
    realm = owned_realm(admin, operation)
    if not isinstance(username, str) or not username.strip() or len(username) > 128:
        raise ValueError('IDENTITY_ACCESS_USERNAME_REQUIRED')
    users = admin.resource('/users?username=' + quote(username, safe='') + '&exact=true')
    if len(users) != 1 or users[0].get('username') != username or not users[0].get('enabled') or users[0].get('serviceAccountClientId'):
        raise ValueError('IDENTITY_ACCESS_RECOVERY_TARGET_REFUSED')
    tenant_mapper(admin, operation, alias, expected_tenant)
    created = int(time.time() if now is None else now)
    value = {'schema_version': 1, 'operation_id': operation, 'realm_id': realm['id'],
             'created_at': created, 'expires_at': created + 600,
             'admin_user_id': users[0]['id'], 'admin_username': username,
             'admin_role': 'realm-management.realm-admin', 'provider_alias': alias,
             'tenant_id': str(UUID(expected_tenant)), 'user_role': 'ArcIA.User',
             'mapper_type': MAPPER_TYPE, 'mapper_sync_mode': 'FORCE',
             'scope': 'named_admin_recovery_and_verified_tenant_user_admission'}
    value['plan_sha256'] = plan_digest(value)
    return value


def apply_repair(admin, operation, plan, authorized_hash, now=None):
    now = int(time.time() if now is None else now)
    if not authorized_hash or authorized_hash != plan.get('plan_sha256'):
        raise ValueError('IDENTITY_ACCESS_EXPLICIT_NAMED_EXCEPTION_REQUIRED')
    expected = repair_plan(admin, operation, plan['admin_username'], plan['provider_alias'],
                           plan['tenant_id'], plan['created_at'])
    if expected != plan or not plan['created_at'] <= now < plan['expires_at']:
        raise ValueError('IDENTITY_ACCESS_PLAN_STALE_OR_TARGET_CHANGED')
    recovery = recover_admin(admin, operation, plan['admin_user_id'], plan['admin_username'])
    admission = tenant_mapper(admin, operation, plan['provider_alias'], plan['tenant_id'], apply=True)
    return {**recovery, **admission, 'approval_mode': 'operator_exception_for_named_identity_access_repair',
            'teams_approval_verified': False}
