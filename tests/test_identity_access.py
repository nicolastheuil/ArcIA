from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import identity_access as access


class FakeAdmin:
    def __init__(self):
        self.writes = []
        self.roles = []
        self.user = {'id': 'synthetic-user', 'username': 'synthetic-admin', 'enabled': True}
        self.tenant = '00000000-0000-4000-8000-000000000001'
        self.provider = {'alias': 'synthetic-microsoft', 'providerId': 'microsoft', 'enabled': True,
                         'config': {'tenantId': self.tenant}}
        self.mappers = []
        self.realm = {'id': 'synthetic-realm', 'attributes': {'arcia.operation-id': 'synthetic-operation'}}
    def client(self, name):
        assert name == 'realm-management'
        return {'id': 'realm-client'}
    def resource(self, path='', method='GET', data=None):
        if method != 'GET':
            self.writes.append((path, method, data))
            if path.endswith('/mappers'):
                self.mappers = [{**data, 'id': 'synthetic-mapper'}]
            elif path.endswith('/mappers/synthetic-mapper'):
                self.mappers = [data]
            else:
                self.roles = data
            return None
        if not path: return self.realm
        if path == '/users/synthetic-user': return self.user
        if path.startswith('/users?'): return [self.user]
        if path == '/clients?clientId=ArcIA': return []
        if path.endswith('/roles/realm-admin'):
            return {'id': 'realm-admin-role', 'name': 'realm-admin', 'clientRole': True, 'containerId': 'realm-client'}
        if path == '/roles/ArcIA.User': return {'name': 'ArcIA.User', 'clientRole': False, 'composite': False}
        if path.endswith('/mappers'): return self.mappers
        if path.startswith('/identity-provider/instances/'): return self.provider
        return self.roles


class IdentityAccessTests(unittest.TestCase):
    def test_recovery_changes_only_existing_users_client_role(self):
        admin = FakeAdmin()
        result = access.recover_admin(admin, 'synthetic-operation', 'synthetic-user', 'synthetic-admin')
        self.assertTrue(result['realm_admin_restored'])
        self.assertEqual(len(admin.writes), 1)
        self.assertEqual(admin.writes[0][0], '/users/synthetic-user/role-mappings/clients/realm-client')
        self.assertFalse(result['password_modified'])
        self.assertFalse(result['mfa_modified'])
        access.recover_admin(admin, 'synthetic-operation', 'synthetic-user', 'synthetic-admin')
        self.assertEqual(len(admin.writes), 1)
    def test_recovery_refuses_wrong_deleted_disabled_or_service_identity(self):
        for change in ({'id': 'other'}, {'username': 'other'}, {'enabled': False}, {'serviceAccountClientId': 'technical'}):
            admin = FakeAdmin(); admin.user.update(change)
            with self.assertRaises(ValueError): access.recover_admin(admin, 'synthetic-operation', 'synthetic-user', 'synthetic-admin')
            self.assertEqual(admin.writes, [])
    def test_role_importer_grants_user_only_and_is_idempotent(self):
        admin = FakeAdmin()
        access.tenant_mapper(admin, 'synthetic-operation', admin.provider['alias'], admin.tenant, apply=True)
        self.assertEqual(admin.writes[0][2]['config'], {'syncMode': 'FORCE', 'role': 'ArcIA.User'})
        access.tenant_mapper(admin, 'synthetic-operation', admin.provider['alias'], admin.tenant, apply=True)
        self.assertEqual(len(admin.writes), 1)
    def test_planning_cannot_create_mapper(self):
        admin = FakeAdmin()
        result = access.tenant_mapper(admin, 'synthetic-operation', admin.provider['alias'], admin.tenant)
        self.assertFalse(result['tenant_user_admission_configured'])
        self.assertEqual(admin.writes, [])
    def test_other_tenant_disabled_provider_and_link_only_are_refused(self):
        for change in ({'config': {'tenantId': 'common'}}, {'enabled': False}, {'linkOnly': True}, {'providerId': 'oidc'}):
            admin = FakeAdmin(); admin.provider.update(change)
            with self.assertRaises(ValueError): access.tenant_mapper(admin, 'synthetic-operation', admin.provider['alias'], admin.tenant, apply=True)
            self.assertEqual(admin.writes, [])
    def test_foreign_realm_and_privileged_mapper_collision_are_refused(self):
        admin = FakeAdmin(); admin.realm = {'attributes': {'arcia.operation-id': 'other'}}
        with self.assertRaises(ValueError): access.recover_admin(admin, 'synthetic-operation', 'synthetic-user', 'synthetic-admin')
        admin = FakeAdmin(); admin.mappers = [{'name': access.MAPPER_NAME, 'config': {'role': 'ArcIA.Admin'}}]
        with self.assertRaises(ValueError): access.tenant_mapper(admin, 'synthetic-operation', admin.provider['alias'], admin.tenant, apply=True)
        self.assertEqual(admin.writes, [])
    def test_repair_plan_is_bound_to_exact_identity_tenant_role_and_time(self):
        admin = FakeAdmin()
        plan = access.repair_plan(admin, 'synthetic-operation', 'synthetic-admin', admin.provider['alias'], admin.tenant, now=1000)
        self.assertEqual(admin.writes, [])
        for now in (999, 1600):
            with self.assertRaises(ValueError): access.apply_repair(admin, 'synthetic-operation', plan, plan['plan_sha256'], now=now)
        admin.user['id'] = 'new-user-same-name'
        with self.assertRaises(ValueError): access.apply_repair(admin, 'synthetic-operation', plan, plan['plan_sha256'], now=1001)
        self.assertEqual(admin.writes, [])
    def test_named_exception_grants_only_requested_admin_and_basic_federated_user_role(self):
        admin = FakeAdmin()
        plan = access.repair_plan(admin, 'synthetic-operation', 'synthetic-admin', admin.provider['alias'], admin.tenant, now=1000)
        with self.assertRaises(ValueError): access.apply_repair(admin, 'synthetic-operation', plan, '', now=1001)
        self.assertEqual(admin.writes, [])
        result = access.apply_repair(admin, 'synthetic-operation', plan, plan['plan_sha256'], now=1001)
        self.assertTrue(result['realm_admin_restored'])
        self.assertTrue(result['tenant_user_admission_configured'])
        self.assertFalse(result['tenant_admission_admin_roles_granted'])
        self.assertFalse(result['teams_approval_verified'])
        self.assertEqual(len(admin.writes), 2)


if __name__ == '__main__': unittest.main()
