#!/usr/bin/env python3
"""Read-only foundation inventory. Private stdout must be captured by the wrapper."""
import http.cookies
import json
import re
import ssl
import sys

from vmware_inventory import PinnedTLSContext, safe_error_code, validate_connection
from vmware_deploy import NAMES, validate_target


def numeric_version(value):
    return value if isinstance(value, str) and re.fullmatch(r'\d+(?:\.\d+){1,3}', value) else 'UNKNOWN'


def summarize(private):
    """Explicit allowlist: never forward names, identifiers, URLs or fault text."""
    return {
        'status': 'inventoried', 'code': 'FOUNDATION_INVENTORY_COLLECTED',
        'vcenter_version': numeric_version(private['vcenter_version']),
        'esxi_versions': sorted({numeric_version(n['version']) for n in private['hosts']}),
        'scoped_node_count': len(private['nodes']),
        'shared_datastore_accessible': private['shared_datastore_accessible'] is True,
        'capacity_1tib_available': private['capacity_1tib_available'] is True,
        'datastore_type': private['datastore_type'] if private['datastore_type'] in
            ('vsan', 'VMFS', 'NFS', 'NFS41', 'VVOL') else 'OTHER',
        'storage_policy_query_succeeded': private['policy_query_succeeded'] is True,
        'compatible_policy_count': sum(p['compatible'] is True for p in private['policies']),
        'policy_query_code': private['policy_query_code'] if private['policy_query_code'] in
            ('POLICIES_READ', 'VCENTER_PERMISSION_DENIED', 'POLICY_API_FAILED') else 'POLICY_API_FAILED',
        'csi_qualified': False, 'k3s_installed': False,
    }


def read_policies(session, connection, context, datastore_id):
    import pyVmomi
    from pyVmomi import pbm, VmomiSupport
    cookie = http.cookies.SimpleCookie(session._stub.cookie)
    session_cookie = cookie['vmware_soap_session'].value
    http_context = VmomiSupport.GetHttpContext()
    previous_cookies = http_context.get('cookies')
    request_context = VmomiSupport.GetRequestContext()
    previous_session = request_context.get('vcSessionCookie')
    try:
        http_context['cookies'] = cookie
        request_context['vcSessionCookie'] = session_cookie
        stub = pyVmomi.SoapStubAdapter(host=connection['server'], port=connection['port'],
            version='pbm.version.version1', path='/pbm/sdk', poolSize=0, sslContext=context,
            httpConnectionTimeout=30)
        content = pbm.ServiceInstance('ServiceInstance', stub).RetrieveContent()
        manager = content.profileManager
        ids = manager.PbmQueryProfile(resourceType=pbm.profile.ResourceType(resourceType='STORAGE'),
                                      profileCategory='REQUIREMENT')
        profiles = manager.PbmRetrieveContent(profileIds=ids) if ids else []
        hub = pbm.placement.PlacementHub(hubType='Datastore', hubId=datastore_id)
        result = []
        for profile in profiles:
            matches = content.placementSolver.PbmCheckCompatibility(hubsToSearch=[hub],
                                                                    profile=profile.profileId)
            compatible = any(m.hub.hubId == datastore_id and not m.error for m in matches)
            result.append({'id': profile.profileId.uniqueId, 'name': profile.name,
                           'compatible': compatible})
        return result
    finally:
        if previous_cookies is None: http_context.pop('cookies', None)
        else: http_context['cookies'] = previous_cookies
        if previous_session is None: request_context.pop('vcSessionCookie', None)
        else: request_context['vcSessionCookie'] = previous_session


def collect(payload):
    from pyVim.connect import SmartConnect, Disconnect
    from pyVmomi import vim
    connection = validate_connection(payload['connection'])
    target = validate_target(payload['target'])
    context = (PinnedTLSContext(connection['certificate_sha256']) if connection.get('certificate_sha256')
               else ssl.create_default_context(cafile=connection['ca_file'] or None))
    session = SmartConnect(host=connection['server'], port=connection['port'], user=connection['username'],
        pwd=connection['password'], sslContext=context, httpConnectionTimeout=30)
    view = None
    try:
        content = session.RetrieveContent()
        if content.about.apiType != 'VirtualCenter': raise ValueError('VCENTER_REQUIRED')
        cluster = vim.ClusterComputeResource(target['cluster_id'], session._stub)
        ds = vim.Datastore(target['datastore_id'], session._stub)
        view = content.viewManager.CreateContainerView(content.rootFolder, [vim.VirtualMachine], True)
        nodes = [vm for vm in view.view if vm.name in NAMES and vm.config and
                 vm.config.annotation == 'ArcIA harness operation '+payload['operation_id']]
        if len(nodes) != 3 or any(vm.runtime.host not in cluster.host for vm in nodes):
            raise ValueError('TARGET_SCOPE_MISMATCH')
        hosts = {vm.runtime.host._moId: vm.runtime.host for vm in nodes}
        mounted = {mount.key._moId for mount in ds.host if mount.mountInfo.mounted and
                   mount.mountInfo.accessible and mount.mountInfo.accessMode == 'readWrite'}
        private = {
            'operation_id': payload['operation_id'], 'vcenter_version': content.about.version,
            'vcenter_build': content.about.build,
            'hosts': [{'id': h._moId, 'version': h.config.product.version,
                       'build': h.config.product.build} for h in hosts.values()],
            'nodes': [{'name': vm.name, 'id': vm._moId, 'host_id': vm.runtime.host._moId}
                      for vm in nodes],
            'datastore_id': ds._moId, 'datastore_type': ds.summary.type,
            'shared_datastore_accessible': ds.summary.accessible and set(hosts) <= mounted,
            'capacity_1tib_available': ds.summary.freeSpace >= 1024**4,
            'policy_query_succeeded': False, 'policy_query_code': 'POLICY_API_FAILED', 'policies': [],
        }
        # This account is used for discovery only. Never install its credentials in Kubernetes.
        try:
            private['policies'] = read_policies(session, connection, context, ds._moId)
            private.update(policy_query_succeeded=True, policy_query_code='POLICIES_READ')
        except Exception as exc:
            private['policy_query_code'] = ('VCENTER_PERMISSION_DENIED' if
                safe_error_code(exc) == 'VCENTER_PERMISSION_DENIED' else 'POLICY_API_FAILED')
        return {'private': private, 'safe': summarize(private)}
    finally:
        try:
            if view is not None: view.Destroy()
        finally: Disconnect(session)


def main():
    try:
        result = collect(json.load(sys.stdin))
    except Exception as exc:
        result = {'safe': {'status': 'blocked', 'code': safe_error_code(exc),
                           'k3s_installed': False, 'csi_qualified': False}}
    print(json.dumps(result))
    return 0 if result['safe']['status'] == 'inventoried' else 2


if __name__ == '__main__': sys.exit(main())
