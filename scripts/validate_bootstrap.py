"""Public bootstrap coverage contract. Adding a component requires updating it."""
import json
import hashlib
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def validate(root=ROOT):
    definition=json.loads((root/'bootstrap/qualification.json').read_text(encoding='utf-8'))
    lock=json.loads((root/'versions.lock.yaml').read_text(encoding='utf-8'))
    tools=json.loads((root/'builder/tools.lock.json').read_text(encoding='utf-8'))
    coverage=definition['coverage']
    if lock.get('identity',{}).get('enabled'):
        contract=definition.get('configuration_contracts',{}).get('identity',{})
        if contract.get('default_provider')!='keycloak_local' or contract.get('local_accounts')!='permanent':
            raise ValueError('BOOTSTRAP_IDENTITY_DEFAULT_REQUIRED')
        identity_lock=json.loads((root/'bootstrap/identity.lock.json').read_text(encoding='utf-8'))
        if contract.get('state_selection')!='complete_scoped_identity_local_choice' or contract.get('admin_access_script')!='scripts/Show-IdentityAccess.ps1':
            raise ValueError('BOOTSTRAP_IDENTITY_ACCESS_CONTRACT')
        if not {'scripts/ProtectedState.ps1','scripts/Show-IdentityAccess.ps1'}<=set(identity_lock['files']):
            raise ValueError('BOOTSTRAP_IDENTITY_ACCESS_LOCK')
        for relative,digest in identity_lock['files'].items():
            content=(root/relative).read_text(encoding='utf-8').replace('\r\n','\n').encode('utf-8')
            if hashlib.sha256(content).hexdigest()!=digest:raise ValueError('BOOTSTRAP_IDENTITY_LOCK_HASH')
        required_identity=['install_identity','verify_identity','connect_identity','verify_identity_access','inspect_identity']
        required_identity += ['plan_identity_microsoft_egress', 'inspect_identity_microsoft_egress']
        required_identity.append('inspect_identity_access_policy')
        required_identity.append('install_identity_public_https_egress')
        required_identity.append('plan_personal_cleanup')
        cleanup = contract.get('personal_cleanup', {})
        if (cleanup.get('automatic_deletion') is not False or
                cleanup.get('eligible_users') != 'missing_subject_404_only_disabled_retained' or
                cleanup.get('apply_action') != 'apply_personal_cleanup' or
                'scripts/personal_cleanup.py' not in identity_lock['files']):
            raise ValueError('BOOTSTRAP_PERSONAL_CLEANUP_CONTRACT')
        if any('apply_personal_cleanup' in s.get('arguments', []) for s in definition['steps']):
            raise ValueError('BOOTSTRAP_PERSONAL_CLEANUP_AUTOMATIC_DELETE_REFUSED')
        public_https = contract.get('public_https', {})
        if (public_https.get('instance_option') != 'identity.https_egress_mode' or
                public_https.get('default') != 'disabled' or
                public_https.get('enabled_mode') != 'public_ipv4_443' or
                public_https.get('target') != 'keycloak_only' or
                public_https.get('installation_step') != 'install_identity_public_https_egress' or
                not {'schemas/bootstrap.schema.json', 'scripts/harness.py'} <= set(identity_lock['files'])):
            raise ValueError('BOOTSTRAP_IDENTITY_PUBLIC_HTTPS_CONTRACT')
        admission = contract.get('tenant_admission', {})
        if (admission.get('role') != 'ArcIA.User' or admission.get('automatic_privilege_repair') is not False or
                admission.get('inspection_step') != 'inspect_identity_access_policy' or
                'scripts/identity_access.py' not in identity_lock['files']):
            raise ValueError('BOOTSTRAP_IDENTITY_TENANT_ADMISSION_CONTRACT')
        if (contract.get('microsoft_egress', {}).get('automatic_deployment_enabled') is not False or
                contract['microsoft_egress'].get('planning_step') != 'plan_identity_microsoft_egress' or
                contract['microsoft_egress'].get('approval_required') != 'server_verified_teams' or
                'scripts/identity_egress.py' not in identity_lock['files']):
            raise ValueError('BOOTSTRAP_IDENTITY_EGRESS_CONTRACT')
        if lock['identity'].get('personal_portal_enabled'):
            required_identity+=['install_personal_portal','verify_personal_portal','inspect_personal_portal']
            if contract.get('automatic_first_login') is not True or contract.get('stable_ownership')!='issuer_subject_never_reassigned':
                raise ValueError('BOOTSTRAP_PERSONAL_PORTAL_CONTRACT')
            if not {'services/identity/portal.py','services/identity/slots.py','scripts/portal_deploy.py'}<=set(identity_lock['files']):
                raise ValueError('BOOTSTRAP_PERSONAL_PORTAL_LOCK')
        if not set(required_identity)<={step['id'] for step in definition['steps']}:
            raise ValueError('BOOTSTRAP_IDENTITY_STEPS_REQUIRED')
    m365=definition.get('configuration_contracts',{}).get('microsoft365',{})
    if m365.get('lock')!='bootstrap/microsoft365.lock.json' or m365.get('runtime_implemented') is not False:
        raise ValueError('BOOTSTRAP_M365_CONTRACT')
    m365_lock=json.loads((root/m365['lock']).read_text(encoding='utf-8'))
    if lock.get('microsoft365',{}).get('contract_lock')!=m365['lock'] or lock['microsoft365'].get('enabled') is not False:
        raise ValueError('BOOTSTRAP_M365_RUNTIME_GATE')
    required_m365={'schemas/microsoft365.schema.json','examples/microsoft365/microsoft365.yaml',
                   'scripts/microsoft365_config.py','docs/annexes/integration-microsoft365.md'}
    if set(m365_lock.get('files',{}))!=required_m365:
        raise ValueError('BOOTSTRAP_M365_LOCK_COVERAGE')
    for relative,digest in m365_lock['files'].items():
        # Hash normalized text, independent of Git's checkout line ending policy.
        content=(root/relative).read_text(encoding='utf-8').replace('\r\n','\n').encode('utf-8')
        if hashlib.sha256(content).hexdigest()!=digest:raise ValueError('BOOTSTRAP_M365_LOCK_HASH')
    import microsoft365_config
    microsoft365_config.validate(microsoft365_config.load_config(root/'examples/microsoft365/microsoft365.yaml'))
    catalogue=definition.get('catalogue_contract',{})
    if lock.get('skills_catalog',{}).get('enabled'):
        for key,expected_step in (('installation_step','install_hermes_tools_base'),('verification_step','verify_hermes_tools'),('secondary_runtime_step','install_multiuser')):
            if catalogue.get(key)!=expected_step:raise ValueError('BOOTSTRAP_SKILLS_CONTRACT')
        if catalogue.get('lock')!='builder/skills.lock.json' or not (root/catalogue['lock']).is_file():raise ValueError('BOOTSTRAP_SKILLS_LOCK')
    expected={
        'components':set(lock['components']),
        'tools':set(tools['tools']),
        'services':{p.name for p in (root/'services').iterdir() if p.is_dir() and not p.name.startswith(('.', '__'))},
        'features':{k for k,v in lock.items() if isinstance(v,dict) and v.get('enabled') is True}}
    for key,names in expected.items():
        if set(coverage[key])!=names:raise ValueError('BOOTSTRAP_COVERAGE_'+key.upper())
    seen=set()
    for step in definition['steps']:
        if step['id'] in seen or not set(step['after'])<=seen:raise ValueError('BOOTSTRAP_DEPENDENCIES')
        if not (root/step['script']).is_file():raise ValueError('BOOTSTRAP_MISSING_SCRIPT')
        if step['status_file'] and not step['success_codes']:raise ValueError('BOOTSTRAP_MISSING_SUCCESS_CONTRACT')
        if step['script']=='scripts/Invoke-ClusterFoundation.ps1':
            action=step['arguments'][1]
            for source in ('scripts/Invoke-ClusterFoundation.ps1','scripts/cluster_foundation.py'):
                if "'"+action+"'" not in (root/source).read_text(encoding='utf-8'):raise ValueError('BOOTSTRAP_ACTION_MISSING')
        seen.add(step['id'])
    order=[s['id'] for s in definition['steps']]
    required=['qualify_ports','install_vip','qualify_vip','preinstallation_gates','install_k3s','inspect_cluster',
              'install_vmware','qualify_storage','install_postgres','public_tls','install_hermes_base',
              'install_knowledge','install_privacy','install_hermes_tools_base','connect_knowledge','install_hermes',
              'install_multiuser','qualify_apps','qualify_live_vip','verify_knowledge','verify_hermes_tools','verify_privacy','verify_multiuser','https_auth']
    if [order.index(k) for k in required]!=sorted(order.index(k) for k in required):raise ValueError('BOOTSTRAP_INSTALL_ORDER')
    audit=[s for s in definition['steps'] if 'audit' in s['profiles']]
    if any(s['id'].startswith(('install_', 'qualify_', 'verify_knowledge','connect_')) for s in audit):raise ValueError('BOOTSTRAP_AUDIT_MUTATES_WORKLOADS')
    return {'status':'verified','code':'BOOTSTRAP_COVERAGE_VERIFIED','steps':len(order),
            'components':len(expected['components']),'tools_and_catalogs':len(expected['tools']),
            'fresh_cluster_tested':False}


if __name__=='__main__':print(json.dumps(validate()))
