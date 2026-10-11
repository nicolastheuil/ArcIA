"""Apply narrow operation-owned roles; private stdin/stdout only via PS wrapper."""
import json
from pathlib import Path
import ssl
import sys
import traceback
import uuid
from vmware_inventory import PinnedTLSContext, safe_error_code, validate_connection
from vmware_deploy import NAMES, validate_target

ROOT = Path(__file__).resolve().parents[1]
SYSTEM = {'System.Read', 'System.View', 'System.Anonymous'}


def same_principal(left, right):
    def canonical(value):
        value = value.casefold()
        if '\\' in value:
            domain, name = value.split('\\', 1)
            return name + '@' + domain
        return value
    return canonical(left) == canonical(right)


def check_existing_permission(existing, principal, role_id):
    matches = [p for p in existing if same_principal(p.principal, principal) and p.group is False]
    if not matches: return False
    if len(matches) != 1 or matches[0].roleId != role_id or matches[0].propagate is not False:
        raise ValueError('EXISTING_PERMISSION_CONFLICT')
    return True


def permission_entities(content, target, owned, session, vim):
    entities = {content.rootFolder._moId: (content.rootFolder, 'vcenter_root'),
                target['datastore_id']: (vim.Datastore(target['datastore_id'], session._stub), 'selected_datastore')}
    for vm in owned: entities[vm._moId] = (vm, 'three_owned_node_vms')
    readers = [vim.ClusterComputeResource(target['cluster_id'], session._stub)]
    readers += [vm.runtime.host for vm in owned]
    for vm in owned:
        current = vm.parent
        while current is not None:
            # Datacenter's top-level folders are complex-entity permission
            # aliases. Assign on Datacenter, never independently on vmFolder.
            parent = getattr(current, 'parent', None)
            if not (isinstance(parent, vim.Datacenter) and current in
                    (parent.vmFolder, parent.hostFolder, parent.datastoreFolder, parent.networkFolder)):
                readers.append(current)
            current = parent
    for entity in readers:
        entities.setdefault(entity._moId, (entity, 'designated_inventory_objects_and_ancestors'))
    return entities


def collect(payload):
    from pyVim.connect import SmartConnect, Disconnect
    from pyVmomi import vim
    connection = validate_connection(payload['connection'])
    target = validate_target(payload['target'])
    operation = str(uuid.UUID(payload['operation_id']))
    intent = payload['intent']
    if intent['operation_id'] != operation or intent['target'] != target or intent['principal'] != payload['service']['username']:
        raise ValueError('PERMISSION_INTENT_SCOPE_MISMATCH')
    context = (PinnedTLSContext(connection['certificate_sha256']) if connection.get('certificate_sha256')
               else ssl.create_default_context(cafile=connection['ca_file'] or None))
    session = SmartConnect(host=connection['server'], port=connection['port'], user=connection['username'],
        pwd=connection['password'], sslContext=context, httpConnectionTimeout=30)
    view = None
    stage = 'READ_DESIGNATED_INVENTORY'
    created = applied = 0
    try:
        content = session.RetrieveContent()
        manager = content.authorizationManager
        view = content.viewManager.CreateContainerView(content.rootFolder, [vim.VirtualMachine], True)
        owned = [vm for vm in view.view if vm.name in NAMES and vm.config and
                 vm.config.annotation == 'ArcIA harness operation '+operation]
        if len(owned) != 3: raise ValueError('THREE_OWNED_VMS_REQUIRED')
        plan = json.loads((ROOT/'infra/vmware/csi-permissions.plan.json').read_text())
        available = {p.privId for p in manager.privilegeList}
        principal = payload['service']['username']
        if payload.get('read_only'):
            roles = [r for r in manager.roleList if any(r.name == 'ArcIA-'+p['scope']+'-'+operation for p in plan['roles'])]
            permissions = [p for r in roles for p in manager.RetrieveRolePermissions(r.roleId)]
            return {'private': {'operation_id': operation, 'role_permissions': [
                {'role': r.name, 'privileges': list(r.privilege), 'permissions': [
                    {'principal': p.principal, 'group': p.group, 'propagate': p.propagate, 'entity_id': p.entity._moId}
                    for p in manager.RetrieveRolePermissions(r.roleId)]} for r in roles]},
                'safe': {'status': 'inspected', 'code': 'SCOPED_ROLES_INSPECTED',
                'role_count': len(roles), 'grant_count': len(permissions),
                'foreign_grant_count': sum(not same_principal(p.principal, principal) or p.group for p in permissions),
                'service_grant_count': sum(same_principal(p.principal, principal) and not p.group for p in permissions),
                'group_grant_count': sum(p.group for p in permissions),
                'propagating_grant_count': sum(p.propagate for p in permissions),
                'csi_storage_operations_qualified': False, 'mutations_performed': False}}
        stage = 'RECONCILE_ROLE_DEFINITIONS'
        role_ids, created, foreign_role_grants = {}, 0, 0
        for role in plan['roles']:
            privileges = set(role['privileges']) | SYSTEM
            if not privileges <= available: raise ValueError('REQUIRED_PRIVILEGE_UNAVAILABLE')
            # Unique operation suffix prevents adoption of an unrelated generic role.
            name = 'ArcIA-'+role['scope']+'-'+operation
            matches = [r for r in manager.roleList if r.name == name]
            if matches:
                if len(matches) != 1 or set(matches[0].privilege) != privileges:
                    raise ValueError('EXISTING_ROLE_CONFLICT')
                role_id = matches[0].roleId
                # Existing roles are never edited/deleted. Other assignments cannot
                # change this account's scope; preserve them and verify effective
                # privileges, including negative checks, after our narrow grants.
                foreign_role_grants += sum(not same_principal(p.principal, principal) or p.group
                    for p in manager.RetrieveRolePermissions(role_id))
            else:
                if payload.get('verify_only'): raise ValueError('EXISTING_SERVICE_ROLE_MISSING')
                role_id = manager.AddAuthorizationRole(name=name, privIds=sorted(privileges))
                created += 1
            role_ids[role['scope']] = role_id
        entities = permission_entities(content, target, owned, session, vim)
        stage = 'RECONCILE_ENTITY_GRANTS'
        applied = 0
        for entity, scope in entities.values():
            role_id = role_ids[scope]
            if check_existing_permission(manager.RetrieveEntityPermissions(entity, inherited=False), principal, role_id):
                continue
            if payload.get('verify_only'): raise ValueError('EXISTING_SERVICE_GRANT_MISSING')
            permission = vim.AuthorizationManager.Permission(principal=principal, group=False,
                                                            roleId=role_id, propagate=False)
            manager.SetEntityPermissions(entity=entity, permission=[permission])
            applied += 1
        # Reconnect as the service account: a role assignment alone is not verification.
        stage = 'VERIFY_EFFECTIVE_PRIVILEGES'
        service = SmartConnect(host=connection['server'], port=connection['port'], user=principal,
            pwd=payload['service']['password'], sslContext=context, httpConnectionTimeout=30)
        try:
            sc = service.RetrieveContent()
            sid = sc.sessionManager.currentSession.key
            checks = []
            for entity, scope in entities.values():
                expected = next(r['privileges'] for r in plan['roles'] if r['scope'] == scope)
                checks.append(all(manager.HasPrivilegeOnEntity(entity, sid, expected)))
            cannot_power = all(not any(manager.HasPrivilegeOnEntity(vm, sid,
                ['VirtualMachine.Interact.PowerOff', 'VirtualMachine.Inventory.Delete'])) for vm in owned)
            outsiders = [vm for vm in view.view if vm not in owned]
            outside_denied = None
            if outsiders:
                outside_denied = not any(manager.HasPrivilegeOnEntity(outsiders[0], sid,
                    ['VirtualMachine.Config.AddExistingDisk', 'VirtualMachine.Config.AddRemoveDevice']))
            passed = all(checks) and cannot_power and outside_denied is not False
        finally: Disconnect(service)
        return {'private': {'operation_id': operation, 'principal': principal, 'roles': role_ids,
                            'entity_ids': list(entities)},
            'safe': {'status': 'verified' if passed else 'blocked',
                'code': 'SCOPED_SERVICE_PRIVILEGES_VERIFIED' if passed else 'SERVICE_PRIVILEGES_CHECK_FAILED',
                'role_count': len(role_ids), 'roles_created_count': created, 'grants_applied_count': applied,
                'foreign_role_grants_preserved_count': foreign_role_grants,
                'scoped_entity_count': len(entities), 'required_privileges_present': all(checks),
                'vm_power_and_deletion_denied': cannot_power, 'outside_vm_disk_change_denied': outside_denied,
                'permissions_propagate': False, 'csi_storage_operations_qualified': False, 'k3s_installed': False}}
    except Exception as exc:
        exc.arcia_stage = stage
        exc.arcia_created = created
        exc.arcia_applied = applied
        raise
    finally:
        try:
            if view is not None: view.Destroy()
        finally: Disconnect(session)


def main():
    try: result = collect(json.load(sys.stdin))
    except Exception as exc:
        code = str(exc) if str(exc) in ('EXISTING_PERMISSION_CONFLICT', 'EXISTING_ROLE_CONFLICT',
            'ROLE_USED_OUTSIDE_OPERATION', 'REQUIRED_PRIVILEGE_UNAVAILABLE', 'PERMISSION_INTENT_SCOPE_MISMATCH',
            'EXISTING_SERVICE_ROLE_MISSING', 'EXISTING_SERVICE_GRANT_MISSING') else safe_error_code(exc)
        frames = traceback.extract_tb(exc.__traceback__)
        line = next((f.lineno for f in reversed(frames) if Path(f.filename).name == Path(__file__).name), 0)
        result = {'private': {'failure': traceback.format_exc()},
                  'safe': {'status': 'blocked', 'code': code, 'failure_line': line,
                           'stage': getattr(exc, 'arcia_stage', 'CONNECT_OR_VALIDATE'),
                           'roles_created_count': getattr(exc, 'arcia_created', 0),
                           'grants_applied_count': getattr(exc, 'arcia_applied', 0),
                           'reconcile_before_retry': True, 'k3s_installed': False}}
    print(json.dumps(result))
    return 0 if result['safe']['status'] in ('verified', 'inspected') else 2


if __name__ == '__main__': sys.exit(main())
