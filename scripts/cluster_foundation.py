"""Typed foundation worker. Never invoke directly with inherited tool stdout."""
import json
from pathlib import Path
import re
import sys
import traceback
import uuid
import secrets
import time
import ipaddress
import subprocess
import harness
from ssh_transport import transport, guest

ROOT = Path(__file__).resolve().parents[1]


def install_k3s(payload,target,nodes,base):
    instance=payload['instance'];lock=json.loads((ROOT/'versions.lock.yaml').read_text())
    config=harness.validate(instance['config'])
    blockers=harness.installation_blockers(config,lock)
    if blockers: raise ValueError('PREINSTALL_QUALIFICATIONS_REQUIRED')
    inventory=harness.render(config,instance['k3s_token'],lock)
    root=Path(payload['private_root']).resolve()
    identity=Path(target['ssh_public_key_path']).resolve().with_suffix('')
    files={str(p.relative_to(ROOT)).replace('\\','/'):p.read_text() for p in (ROOT/'infra/ansible').rglob('*') if p.is_file()}
    files['scripts/node_probe.py']=(ROOT/'scripts/node_probe.py').read_text()
    data={'files':files,'inventory':inventory,'identity':identity.read_text(),
          'known_hosts':(root/'known_hosts.arcia').read_text()}
    process=subprocess.run(['wsl.exe','-e','/bin/sh','-c',
        'exec "$HOME/.local/share/arcia-validation/bin/python" -c "$1"','arcia-controller',
        (ROOT/'scripts/wsl_ansible.py').read_text()],input=json.dumps(data).encode(),capture_output=True,timeout=5100)
    if process.returncode: raise ValueError('PROTECTED_LINUX_CONTROLLER_FAILED')
    result=json.loads(process.stdout)
    passed=result['returncode']==0 and len(result['stats'])==3 and all(s['failures']==0 and s['unreachable']==0 for s in result['stats'])
    return {'private':{'operation_id':payload['operation_id'],'ansible':result},
        'safe':{'status':'installed' if passed else 'blocked','code':'K3S_THREE_SERVERS_INSTALLED' if passed else 'K3S_INSTALLATION_FAILED',
                'k3s_installed':passed,'server_count':len(result['stats']),'k3s_version':lock['components']['k3s']['version'],
                'secrets_encryption_verified':passed,'production_failover_qualified':False,'csi_qualified':False}}


def vip_operation(payload,target,nodes,base):
    operation=payload['operation_id']
    instance=payload['instance']
    if instance['endpoint_design']['method']!='node_vip': raise ValueError('NODE_VIP_DESIGN_REQUIRED')
    if payload['vip_journal']['operation_id']!=operation: raise ValueError('VIP_JOURNAL_SCOPE')
    script=(ROOT/'scripts/node_vip.py').read_bytes()
    addresses=[n['address'] for n in nodes]
    subnet=str(ipaddress.ip_interface(target['addresses'][0]).network)
    common={'operation_id':operation,'nodes':addresses,'subnet':subnet,'gateway':target['gateway'],
        'vips':[instance['endpoint_design']['api_ip'],instance['endpoint_design']['https_ip']],
        'vrid':payload['vip_journal']['vrid'],'password':payload['vip_journal']['password'],
        'health_source':(ROOT/'scripts/vip_health.py').read_text(),
        'packages':json.loads((ROOT/'versions.lock.yaml').read_text())['node_vip']['packages']}
    def call(index,action,**extra):
        return guest(target,nodes[index-1],base,script,{**common,'node':index,'action':action,**extra},root=True,timeout=420)
    if payload['action']=='install_vip':
        preflight=[call(i,'preflight_vip') for i in (1,2,3)]
        installed=[call(i,'install_vip') for i in (1,2,3)]
        return {'private':{'operation_id':operation,'preflight':preflight,'installed':installed},
            'safe':{'status':'installed','code':'NODE_VIP_INSTALLED_NOT_YET_QUALIFIED','node_count':3,
                    'configuration_valid':all(r['configuration_valid'] for r in installed),'firewall_modified':False,
                    'vmac_used':False,'k3s_installed':False}}
    if payload['action']=='inspect_vip':
        states=[call(i,'vip_state') for i in (1,2,3)]
        return {'private':{'operation_id':operation,'states':states},
            'safe':{'status':'inspected','code':'NODE_VIP_STATE_INSPECTED','active_service_count':sum(s['active'] for s in states),
                    'vip_owner_count':sum(s['owns_any_vip'] for s in states)}}
    if payload['action']=='qualify_live_vip':
        config=instance['config'];phases=[];stopped=None
        def single_owner(exclude=None):
            deadline=time.monotonic()+25
            while time.monotonic()<deadline:
                states=[call(i,'vip_state') for i in (1,2,3)]
                owners=[i for i,s in enumerate(states,1) if s['owns_all_vips']]
                if sum(s['owns_any_vip'] for s in states)>1: raise ValueError('MULTIPLE_LIVE_VIP_OWNERS')
                if len(owners)==1 and owners[0]!=exclude: return owners[0]
                time.sleep(1)
            raise ValueError('LIVE_VIP_OWNER_NOT_READY')
        def check(phase,owner):
            probes=[guest(target,node,base,(ROOT/'scripts/node_kubernetes.py').read_bytes(),{
                'action':'probe_live_endpoints','api_endpoint':config['network']['api_endpoint'],
                'https_ip':instance['endpoint_design']['https_ip'],'hostname':config['network']['public_hostname'],
                'certificate':payload['pilot']['tls_certificate']},root=True,timeout=60) for node in nodes]
            phases.append({'phase':phase,'owner':owner,'probes':probes})
            if not all(p['api_ready'] and p['https_ready'] for p in probes): raise ValueError('LIVE_ENDPOINT_PROBE_FAILED')
        try:
            initial=single_owner();check('initial',initial)
            stopped=initial;call(initial,'stop_vip')
            replacement=single_owner(exclude=initial);check('after_failover',replacement)
        finally:
            if stopped is not None: call(stopped,'start_vip')
        final=single_owner();check('after_owner_return',final)
        passed=final==replacement
        return {'private':{'operation_id':operation,'phases':phases},'safe':{
            'status':'verified' if passed else 'blocked','code':'LIVE_API_HTTPS_VIP_FAILOVER_VERIFIED' if passed else 'LIVE_VIP_PREEMPTION_FAILED',
            'api_checks':sum(p['api_ready'] for phase in phases for p in phase['probes']),
            'https_checks':sum(p['https_ready'] for phase in phases for p in phase['probes']),
            'single_owner_failover':passed,'returning_owner_did_not_preempt':passed,
            'abrupt_node_loss_qualified':False,'public_access_enabled':False}}
    if payload['action']!='qualify_vip': raise ValueError('UNKNOWN_VIP_ACTION')
    listener=(ROOT/'scripts/node_foundation.py').read_bytes()
    challenge=secrets.token_hex(32)
    lease={'operation_id':operation,'nodes':addresses,'challenge':challenge,'expires_at':time.time()+300}
    started=[];cleanup=[];phases=[];stopped=None;passed=False
    def owner(exclude=None):
        expires=time.monotonic()+20
        while time.monotonic()<expires:
            states=[call(i,'vip_state') for i in (1,2,3)]
            owners=[i for i,s in enumerate(states,1) if s['owns_all_vips']]
            if sum(s['owns_any_vip'] for s in states)>1: raise ValueError('MULTIPLE_VIP_OWNERS')
            if len(owners)==1 and owners[0]!=exclude: return owners[0]
            time.sleep(1)
        raise ValueError('SINGLE_VIP_OWNER_NOT_READY')
    try:
        for index,node in enumerate(nodes,1):
            started.append(node)
            guest(target,node,base,listener,{**lease,'node':index,'action':'start_listeners',
                'listener_source':(ROOT/'scripts/network_listener.py').read_text()},root=True)
        first=owner()
        for phase,expected in (('initial',first),('after_failover',None)):
            if expected is None:
                stopped=first;call(first,'stop_vip');expected=owner(exclude=first)
            checks=[call(i,'probe_vip',challenge=challenge,expected_owner=expected) for i in (1,2,3)]
            phases.append({'phase':phase,'owner':expected,'checks':checks})
            if not all(c['passed'] for c in checks): raise ValueError('VIP_TRANSPORT_PROBE_FAILED')
        call(first,'start_vip');stopped=None
        final=owner()
        passed=final==phases[-1]['owner'] # nopreempt: returning node must not steal the VIP.
    finally:
        if stopped is not None:
            try: call(stopped,'start_vip')
            except Exception: cleanup.append(False)
        for node in started:
            try: cleanup.append(guest(target,node,base,listener,{'action':'stop_listeners','operation_id':operation},root=True)['stopped'])
            except Exception: cleanup.append(False)
        # The synthetic health lease is gone; no production API has been started yet.
        time.sleep(4)
        states=[call(i,'vip_state') for i in (1,2,3)]
        withdrawn=not any(s['owns_any_vip'] for s in states)
        passed=passed and len(cleanup)==3 and all(cleanup) and withdrawn
        if not passed:
            for i in (1,2,3):
                try: call(i,'stop_vip')
                except Exception: pass
    return {'private':{'operation_id':operation,'phases':phases,'cleanup':cleanup,'states_after':states},
        'safe':{'status':'verified' if passed else 'blocked','code':'NODE_VIP_TRANSPORT_FAILOVER_VERIFIED' if passed else 'NODE_VIP_QUALIFICATION_FAILED',
            'node_count':3,'api_and_https_checked':True,'transport_checks':sum(len(c['checks']) for p in phases for c in p['checks']),
            'single_owner_failover':passed,'returning_node_did_not_preempt':passed,'temporary_listeners_stopped':all(cleanup),
            'vip_withdrawn_without_healthy_api':withdrawn,'production_k3s_failover_verified':False,'k3s_installed':False}}


def collect(payload):
    operation = str(uuid.UUID(payload['operation_id']))
    if payload['instance']['operation_id'] != operation: raise ValueError('INSTANCE_SCOPE_MISMATCH')
    action = payload['action']
    if action in ('plan_personal_cleanup', 'apply_personal_cleanup'):
        if payload['identity']['operation_id'] != operation:
            raise ValueError('PERSONAL_CLEANUP_IDENTITY_SCOPE')
        target, nodes, base = transport(payload)
        values = {'action': action, 'operation_id': operation, 'credentials': payload['identity'],
                  'hostname': payload['pilot']['hostname'],
                  'cleanup_source': (ROOT/'scripts/personal_cleanup.py').read_text(encoding='utf-8')}
        if action == 'apply_personal_cleanup':
            values.update(cleanup_plan=payload['cleanup_plan']['plan'],
                          authorized_plan_sha256=payload['authorized_plan_sha256'],
                          approval_mode='operator_exception_for_named_personal_cleanup')
        result = guest(target, nodes[0], base, (ROOT/'scripts/node_identity.py').read_bytes(), values, root=True, timeout=1800)
        if action == 'plan_personal_cleanup':
            return {'private': {'operation_id': operation, **result}, 'safe': {
                'status': 'planned', 'code': 'PERSONAL_CLEANUP_PLANNED',
                'candidate_count': len(result['plan']['candidates']),
                'claim_count': sum(len(c['volumes']) for c in result['plan']['candidates']),
                'plan_sha256': result['plan']['plan_sha256'], 'resources_modified': False}}
        # Recreate fresh empty slots through the normal installer, preserving all
        # remaining bindings/PVCs. A failed reconciliation leaves a protected result.
        try:
            restored = collect({**payload, 'action': 'install_personal_portal'})
        except Exception as exc:
            return {'private': {'operation_id': operation, 'cleanup': result, 'failure': traceback.format_exc(),
                                'guest_failure': getattr(exc, 'private_output', None)},
                    'safe': {'status': 'blocked', 'code': 'PERSONAL_CLEANUP_RECONCILE_FAILED',
                             **result, 'portal_reconciled': False}}
        return {'private': {'operation_id': operation, 'cleanup': result, 'reconcile': restored['private']},
                'safe': {'status': restored['safe']['status'],
                         'code': 'PERSONAL_CLEANUP_VERIFIED' if restored['safe']['status'] == 'verified' else 'PERSONAL_CLEANUP_RECONCILE_FAILED',
                         **result, 'portal_reconciled': restored['safe']['status'] == 'verified',
                         'capacity': restored['safe'].get('capacity'),
                         'remaining_bindings_preserved': restored['safe'].get('existing_bindings_preserved'),
                         'remaining_pvcs_preserved': restored['safe'].get('existing_pvcs_preserved')}}
    if action == 'install_identity_public_https_egress':
        config = harness.validate(payload['instance']['config'])
        if config.get('identity', {}).get('https_egress_mode', 'disabled') == 'disabled':
            return {'safe': {'status': 'verified', 'code': 'IDENTITY_PUBLIC_HTTPS_EGRESS_NOT_REQUESTED',
                             'configured': False, 'resources_modified': False}}
        target, nodes, base = transport(payload)
        result = guest(target, nodes[0], base, (ROOT/'scripts/node_identity.py').read_bytes(),
                       {'action': action, 'operation_id': operation, 'network': config['network'],
                        'https_egress_mode': config.get('identity', {}).get('https_egress_mode', 'disabled'),
                        'egress_source': (ROOT/'scripts/identity_egress.py').read_text(encoding='utf-8')}, root=True)
        return {'private': {'operation_id': operation, **result}, 'safe': {
            'status': 'verified', 'code': 'IDENTITY_PUBLIC_HTTPS_EGRESS_VERIFIED',
            'approval_mode': 'explicit_operator_public_https_configuration', **result}}
    if action == 'inspect_identity_access_policy':
        policy = payload.get('access_policy')
        if not policy:
            return {'safe': {'status': 'inspected', 'code': 'IDENTITY_ACCESS_POLICY_INSPECTED',
                             'configured': False, 'resources_modified': False}}
        if policy['operation_id'] != operation or payload['identity']['operation_id'] != operation:
            raise ValueError('IDENTITY_ACCESS_POLICY_SCOPE')
        target, nodes, base = transport(payload)
        result = guest(target, nodes[0], base, (ROOT/'scripts/node_identity.py').read_bytes(),
                       {'action': action, 'operation_id': operation, 'credentials': payload['identity'],
                        'hostname': payload['pilot']['hostname'], 'policy': policy,
                        'access_source': (ROOT/'scripts/identity_access.py').read_text(encoding='utf-8')}, root=True)
        passed = not result['mapper_change_required']
        return {'private': {'operation_id': operation, **result}, 'safe': {
            'status': 'inspected' if passed else 'blocked', 'configured': True,
            'code': 'IDENTITY_ACCESS_POLICY_INSPECTED' if passed else 'IDENTITY_ACCESS_POLICY_DRIFT',
            'resources_modified': False, **result}}
    if action in ('plan_identity_access_repair', 'apply_identity_access_repair'):
        if payload['identity']['operation_id'] != operation:
            raise ValueError('IDENTITY_ACCESS_REPAIR_SCOPE')
        target, nodes, base = transport(payload)
        values = {'action': action, 'operation_id': operation, 'credentials': payload['identity'],
                  'hostname': payload['pilot']['hostname'],
                  'access_source': (ROOT/'scripts/identity_access.py').read_text(encoding='utf-8')}
        if action == 'plan_identity_access_repair':
            values['recovery_username'] = payload['recovery_username']
        else:
            if payload['access_repair']['operation_id'] != operation:
                raise ValueError('IDENTITY_ACCESS_REPAIR_PLAN_SCOPE')
            values.update(repair_plan=payload['access_repair']['plan'], authorized_plan_sha256=payload['authorized_plan_sha256'])
        result = guest(target, nodes[0], base, (ROOT/'scripts/node_identity.py').read_bytes(), values, root=True)
        safe = {'status': 'planned' if action == 'plan_identity_access_repair' else 'verified',
                'code': 'IDENTITY_ACCESS_REPAIR_PLANNED' if action == 'plan_identity_access_repair' else 'IDENTITY_ACCESS_REPAIR_VERIFIED',
                'secrets_disclosed': False, 'full_browser_login_verified': False}
        if 'plan' in result:
            safe.update(plan_sha256=result['plan']['plan_sha256'], resources_modified=False)
        else:
            safe.update({k:v for k,v in result.items() if k != 'policy'})
        return {'private': {'operation_id': operation, **result}, 'safe': safe}
    if action == 'inspect_identity_microsoft_egress':
        target, nodes, base = transport(payload)
        result = guest(target, nodes[0], base, (ROOT/'scripts/node_identity.py').read_bytes(),
                       {'action': action, 'operation_id': operation,
                        'network': payload['instance']['config']['network'],
                        'https_egress_mode': payload['instance']['config'].get('identity', {}).get('https_egress_mode', 'disabled'),
                        'egress_source': (ROOT/'scripts/identity_egress.py').read_text(encoding='utf-8')}, root=True)
        passed = not result['configured'] or (result['bounded_rule'] and result['current_dns_covered'])
        return {'private': {'operation_id': operation, **result}, 'safe': {
            'status': 'inspected' if passed else 'blocked',
            'code': 'IDENTITY_MICROSOFT_EGRESS_INSPECTED' if passed else 'IDENTITY_MICROSOFT_EGRESS_REPLAN_REQUIRED',
            **result}}
    if action == 'apply_identity_microsoft_egress_repair':
        target, nodes, base = transport(payload)
        repair = payload['repair']
        if repair['operation_id'] != operation:
            raise ValueError('IDENTITY_EGRESS_REPAIR_SCOPE')
        result = guest(target, nodes[0], base, (ROOT/'scripts/node_identity.py').read_bytes(),
                       {'action': action, 'operation_id': operation, 'repair_plan': repair['plan'],
                        'authorized_plan_sha256': payload['authorized_plan_sha256'],
                        'approval_mode': 'operator_exception_for_named_repair',
                        'egress_source': (ROOT/'scripts/identity_egress.py').read_text(encoding='utf-8')}, root=True)
        return {'private': {'operation_id': operation, **result}, 'safe': {
            'status': 'installed', 'code': 'IDENTITY_MICROSOFT_EGRESS_REPAIR_INSTALLED',
            **{k: result[k] for k in ('plan_sha256', 'approval_mode', 'teams_approval_verified',
                                     'keycloak_rollout_triggered', 'credentials_modified',
                                     'volumes_modified', 'address_count')},
            'authentication_restored': False}}
    if action == 'plan_identity_microsoft_egress':
        target, nodes, base = transport(payload)
        egress_source = (ROOT/'scripts/identity_egress.py').read_text(encoding='utf-8')
        resolutions = []
        for node in nodes:
            resolved = guest(target, node, base, (ROOT/'scripts/node_identity.py').read_bytes(),
                             {'action': 'resolve_identity_microsoft_egress', 'egress_source': egress_source}, root=True)
            resolutions.extend(resolved['resolutions'])
        result = guest(target, nodes[0], base, (ROOT/'scripts/node_identity.py').read_bytes(),
                       {'action': action, 'operation_id': operation,
                        'egress_source': egress_source, 'resolutions': resolutions}, root=True)
        return {'private': {'operation_id': operation, **result}, 'safe': {
            'status': 'planned', 'code': 'IDENTITY_MICROSOFT_EGRESS_PLANNED',
            'plan_sha256': result['plan']['plan_sha256'], 'address_count': result['address_count'],
            'port': 443, 'protocol': 'TCP', 'target': 'keycloak_only',
            'approval_required': 'server_verified_teams', 'resources_modified': False,
            'authentication_restored': False}}
    if action=='inspect_personal_portal':
        target,nodes,base=transport(payload)
        result=guest(target,nodes[0],base,(ROOT/'scripts/node_identity.py').read_bytes(),
            {'action':action,'operation_id':operation},root=True)
        return {'private':{'operation_id':operation,'result':result},'safe':{'status':'inspected',
            'code':'PERSONAL_PORTAL_INSPECTED',**result}}
    if action=='verify_personal_portal':
        from identity_login import Browser
        target,nodes,base=transport(payload)
        common={'operation_id':operation,'hostname':payload['pilot']['hostname'],'credentials':payload['identity'],
            'pilot':payload['pilot'],'https_ip':payload['instance']['endpoint_design']['https_ip']}
        prepared=guest(target,nodes[0],base,(ROOT/'scripts/node_identity.py').read_bytes(),
            {**common,'action':'prepare_portal_fixtures','fixtures':payload['portal_fixtures']['fixtures']},root=True)
        fixtures=prepared['fixtures'];checks={};sessions=[];browsers=[]
        try:
            for index,fixture in enumerate(fixtures):
                browser=Browser(payload['pilot'],common['https_ip']);csrf=browser.portal_login(fixture['username'],fixture['password'])
                checks[str(index)+'_portal_oidc_login']=True;deadline=time.monotonic()+1500;prefix=None
                while time.monotonic()<deadline:
                    status,body,_=browser.request('POST','/portal/provision',extra_headers={'X-ArcIA-CSRF':csrf})
                    result=json.loads(body)
                    if status!=200:raise ValueError('PERSONAL_PORTAL_PROVISION_REFUSED')
                    phase=result.get('phase')
                    if phase not in ('installing','starting','ready'):raise ValueError('PERSONAL_PORTAL_INSTALL_FAILED')
                    Path(payload['private_root'],'personal-portal-progress.json').write_text(json.dumps({'fixture':index+1,'phase':phase}))
                    if phase=='ready':prefix=result['prefix'];break
                    time.sleep(4)
                if not prefix:raise ValueError('PERSONAL_PORTAL_START_TIMEOUT')
                if not re.fullmatch(r'/u/p[0-9]{2}',prefix):raise ValueError('PERSONAL_PORTAL_PREFIX_REFUSED')
                browser.follow(prefix+'/auth/login?provider=arcia')
                checks[str(index)+'_personal_hermes_login']=browser.request('GET',prefix+'/api/config')[0]==200
                status,body,_=browser.request('GET',prefix+'/api/sessions')
                data=json.loads(body) if status==200 else None
                # No prior chats are imported. Repeated qualification may keep its own synthetic state.
                checks[str(index)+'_sessions_api_access']=status==200
                session_list=data if isinstance(data,list) else data.get('sessions') if isinstance(data,dict) else None
                checks[str(index)+'_empty_personal_history']=isinstance(session_list,list) and len(session_list)==0
                checks[str(index)+'_no_legacy_qualification_session']=b'arcia-multiuser-qualification-' not in body
                status,body,_=browser.request('POST','/portal/provision',extra_headers={'X-ArcIA-CSRF':csrf})
                checks[str(index)+'_repeated_login_same_space']=status==200 and json.loads(body).get('prefix')==prefix
                browsers.append(browser)
                sessions.append({'subject':fixture['subject'],'prefix':prefix,'namespace':'arcia-user-'+prefix.rsplit('/',1)[1],
                    'cookie':'; '.join(k+'='+v.coded_value for k,v in browser.native.items())})
            for index,browser in enumerate(browsers):
                anonymous=Browser(payload['pilot'],common['https_ip'])
                checks[str(index)+'_anonymous_api_denied']=anonymous.request('GET',sessions[index]['prefix']+'/api/config')[0]==401
                checks[str(index)+'_other_space_cookie_denied']=browser.request('GET',sessions[1-index]['prefix']+'/api/config')[0]==401
                checks[str(index)+'_csrf_spoof_denied']=browser.request('POST','/portal/provision',extra_headers={'X-ArcIA-CSRF':'invalid-synthetic'})[0]==403
            finished=guest(target,nodes[0],base,(ROOT/'scripts/node_identity.py').read_bytes(),
                {**common,'action':'finish_portal_qualification','sessions':sessions},root=True)
            checks.update(finished['checks']);passed=all(checks.values())
            return {'private':{'operation_id':operation,'checks':checks,'fixtures':fixtures},'safe':{
                'status':'verified' if passed else 'blocked','code':'PERSONAL_PORTAL_VERIFIED' if passed else 'PERSONAL_PORTAL_FAILED',
                'checks':checks,'synthetic_only':True,'fixture_accounts_disabled':True,'fresh_cluster_rebuilt':False,'ha_qualified':False}}
        finally:
            guest(target,nodes[0],base,(ROOT/'scripts/node_identity.py').read_bytes(),
                {**common,'action':'disable_portal_fixtures','fixtures':fixtures},root=True)
    if action=='install_personal_portal':
        import portal_deploy
        target,nodes,base=transport(payload)
        prepared=guest(target,nodes[0],base,(ROOT/'scripts/node_identity.py').read_bytes(),
            {'action':'prepare_personal_portal','operation_id':operation},root=True)
        lock=json.loads((ROOT/'versions.lock.yaml').read_text(encoding='utf-8'))
        rendered=portal_deploy.payload(lock,payload['instance']['config'],payload['pilot'],operation,
            prepared['dns_ip'],payload['instance']['endpoint_design']['https_ip'])
        result=guest(target,nodes[0],base,(ROOT/'scripts/node_identity.py').read_bytes(),
            {'action':action,'operation_id':operation,'hostname':payload['pilot']['hostname'],
             'credentials':payload['identity'],**rendered},root=True,timeout=2400)
        return {'private':{'operation_id':operation,'result':result},'safe':{'status':'verified' if result['passed'] else 'blocked',
            'code':'PERSONAL_PORTAL_INSTALLED' if result['passed'] else 'PERSONAL_PORTAL_FAILED',**result}}
    if action=='verify_identity_access':
        from identity_login import Browser
        target,nodes,base=transport(payload)
        values={'operation_id':operation,'credentials':payload['identity'],'pilot':payload['pilot'],
                'hostname':payload['pilot']['hostname'],'https_ip':payload['instance']['endpoint_design']['https_ip']}
        checks={};browser=Browser(payload['pilot'],values['https_ip'])
        checks['admin_portal_https']=browser.follow('/admin/users')[0]==200
        checks['master_realm_public_denied']=browser.request('GET','/identity/realms/master/.well-known/openid-configuration')[0]==404
        for who,identity in [('A',payload['pilot']),('B',payload['second_pilot'])]:
            browser=Browser(payload['pilot'],values['https_ip']);prefix='/qualification-b' if who=='B' else ''
            cookies=browser.login(prefix,'qualification-'+who.lower(),identity['password'])
            checks[who+'_oidc_login']=browser.request('GET',prefix+'/api/config')[0]==200
            denied=browser.request('GET',('/qualification-b' if who=='A' else '')+'/api/config')[0]
            checks[who+'_other_owner_denied']=denied==401
            session_cookie='; '.join(k+'='+v.coded_value for k,v in cookies.items())
            revoked=guest(target,nodes[0],base,(ROOT/'scripts/node_identity.py').read_bytes(),
                          {**values,'action':'qualify_identity_revocation','who':who,'session_cookie':session_cookie},root=True)
            checks[who+'_disabled_session_refused']=revoked['passed']
            checks[who+'_revoked_session_refused']=browser.request('GET',prefix+'/api/config')[0]==401
            browser=Browser(payload['pilot'],values['https_ip'])
            browser.login(prefix,'qualification-'+who.lower(),identity['password'])
            checks[who+'_account_restored_without_reset']=browser.request('GET',prefix+'/api/config')[0]==200
        passed=all(checks.values())
        return {'private':{'operation_id':operation,'checks':checks},'safe':{
            'status':'verified' if passed else 'blocked','code':'IDENTITY_ACCESS_VERIFIED' if passed else 'IDENTITY_ACCESS_FAILED',
            'checks':checks,'hermes_oidc_qualified':passed,'sso_provider_enabled':False,'ha_qualified':False}}
    if action in ('install_identity','verify_identity','inspect_identity','connect_identity','cleanup_identity_fixture'):
        if payload['identity']['operation_id'] != operation:raise ValueError('IDENTITY_OPERATION_SCOPE')
        target,nodes,base=transport(payload)
        import identity_deploy
        lock=json.loads((ROOT/'versions.lock.yaml').read_text(encoding='utf-8'))
        values={'action':action,'operation_id':operation,
                **identity_deploy.payload(lock,payload['instance']['config'],payload['identity'],payload['pilot'])}
        if action=='connect_identity':
            prepared=guest(target,nodes[0],base,(ROOT/'scripts/node_identity.py').read_bytes(),
                           {'action':'prepare_identity','operation_id':operation},root=True)
            values.update(prepared=prepared,pilot=payload['pilot'],second_pilot=payload['second_pilot'],
                          https_ip=payload['instance']['endpoint_design']['https_ip'])
            values['runtime_updates']=identity_deploy.runtime_updates(prepared,payload['instance']['config'],values['https_ip'])
        result=guest(target,nodes[0],base,(ROOT/'scripts/node_identity.py').read_bytes(),values,root=True,timeout=2400)
        passed=result.get('passed',result.get('database_ready') and result.get('keycloak_ready'))
        return {'private':{'operation_id':operation,'result':result},'safe':{
            'status':'inspected' if action=='inspect_identity' else ('verified' if passed else 'blocked'),
            'code':('IDENTITY_INSPECTED' if action=='inspect_identity' else
                    ('IDENTITY_RUNTIMES_CONNECTED' if action=='connect_identity' else ('IDENTITY_PORTAL_DEPLOYED' if action=='install_identity' else 'IDENTITY_PORTAL_VERIFIED'))) if passed else 'IDENTITY_PORTAL_FAILED',
            'checks':result.get('checks',{}),'runtime_probes':result.get('runtime_probes',[]),
            'runtime_client_checks':result.get('runtime_client_checks',[]),
            'recent_auth_events':result.get('recent_auth_events',[]),'ha_qualified':False,'hermes_oidc_qualified':False,
            'sso_provider_enabled':False,'secrets_disclosed':False}}
    if action not in ('inspect','qualify_ports','install_vip','qualify_vip','inspect_vip','install_k3s','inspect_k3s','pause_k3s','inspect_cluster','install_vmware','inspect_vmware','qualify_storage','install_postgres','install_hermes','install_hermes_base','inspect_apps','qualify_apps','qualify_live_vip','inspect_hermes_tools','install_hermes_tools','install_hermes_tools_base','verify_hermes_tools','cleanup_failed_hermes_tools','install_knowledge','verify_knowledge','inspect_knowledge','connect_knowledge','install_privacy','verify_privacy','inspect_privacy','install_multiuser','verify_multiuser'): raise ValueError('UNKNOWN_FOUNDATION_ACTION')
    target, nodes, base = transport(payload)
    if action in ('install_multiuser','verify_multiuser'):
        import multiuser_deploy
        lock=json.loads((ROOT/'versions.lock.yaml').read_text(encoding='utf-8'))
        values={'action':action,'operation_id':operation,**multiuser_deploy.payload(lock,payload['instance']['config'],payload['pilot'],payload['second_pilot'])}
        result=guest(target,nodes[0],base,(ROOT/'scripts/node_multiuser.py').read_bytes(),values,root=True,timeout=2500)
        if action=='verify_multiuser':
            import verify_multiuser_access
            http_result=verify_multiuser_access.verify(payload)
            result['checks'].update(http_result['checks'])
            result['passed']=all(result['checks'].values())
        return {'private':{'operation_id':operation,'result':result},'safe':{'status':'verified' if result.get('passed') else 'blocked',
            'code':'MULTIUSER_DEPLOYED' if action=='install_multiuser' and result.get('passed') else ('MULTIUSER_VERIFIED' if result.get('passed') else 'MULTIUSER_QUALIFICATION_FAILED'),'result':result}}
    if action in ('install_privacy','verify_privacy','inspect_privacy'):
        import privacy_deploy
        values={'action':action,'operation_id':operation,**privacy_deploy.payload(),'hermes_policy':privacy_deploy.hermes_policy()}
        if action=='install_privacy':values['api_key']=payload.get('cloud_api_key')
        result=guest(target,nodes[0],base,(ROOT/'scripts/node_privacy.py').read_bytes(),values,root=True,timeout=3600)
        return {'private':{'operation_id':operation,'result':result},'safe':{
            'status':'inspected' if action=='inspect_privacy' else ('verified' if result.get('passed') else 'blocked'),
            'code':'PRIVACY_INSPECTED' if action=='inspect_privacy' else ('PRIVACY_DEPLOYED' if action=='install_privacy' and result.get('passed') else ('PRIVACY_VERIFIED' if result.get('passed') else 'PRIVACY_QUALIFICATION_FAILED')),'result':result}}
    if action in ('install_knowledge','verify_knowledge','inspect_knowledge','connect_knowledge'):
        import knowledge_deploy
        values={'action':action,'operation_id':operation,**knowledge_deploy.payload()}
        result=guest(target,nodes[0],base,(ROOT/'scripts/node_knowledge.py').read_bytes(),values,root=True,timeout=3600)
        return {'private':{'operation_id':operation,'result':result},'safe':{
            'status':'inspected' if action=='inspect_knowledge' else ('verified' if result.get('passed') else 'blocked'),
            'code':'KNOWLEDGE_INSPECTED' if action=='inspect_knowledge' else ('KNOWLEDGE_VERIFIED' if result.get('passed') else 'KNOWLEDGE_QUALIFICATION_FAILED'),'result':result}}
    if action in ('inspect_hermes_tools','install_hermes_tools','install_hermes_tools_base','verify_hermes_tools','cleanup_failed_hermes_tools'):
        values={'action':'install_hermes_tools' if action=='install_hermes_tools_base' else action,'operation_id':operation,
                'require_knowledge':action!='install_hermes_tools_base'}
        if action in ('install_hermes_tools','install_hermes_tools_base','verify_hermes_tools','inspect_hermes_tools'):
            import hermes_tools
            values.update(hermes_tools.payload())
        if action=='inspect_hermes_tools':
            values['benchmark_source']=(ROOT/'scripts/benchmark_token_tools.py').read_text(encoding='utf-8')
        if action in ('install_hermes_tools','install_hermes_tools_base'):
            import copy,hashlib,yaml
            prepared=guest(target,nodes[0],base,(ROOT/'scripts/node_hermes_tools.py').read_bytes(),
                           {'action':'prepare_hermes_tools_config','operation_id':operation},root=True,timeout=180)
            current=yaml.safe_load(prepared['config']);desired=copy.deepcopy(values['settings'])
            current.setdefault('mcp_servers',{}).update(desired.pop('mcp_servers'));current.update(desired)
            values['merged_config']=yaml.safe_dump(current,sort_keys=False)
            values['original_config_sha256']=hashlib.sha256(prepared['config'].encode()).hexdigest()
        result=guest(target,nodes[0],base,(ROOT/'scripts/node_hermes_tools.py').read_bytes(),values,root=True,timeout=1500)
        return {'private':{'operation_id':operation,'result':result},'safe':{
            'status':'inspected' if action=='inspect_hermes_tools' else ('verified' if result.get('passed') else 'blocked'),
            'code':'HERMES_TOOLS_'+('INSPECTED' if action=='inspect_hermes_tools' else ('FAILED_JOBS_REMOVED' if action=='cleanup_failed_hermes_tools' else ('VERIFIED' if result.get('passed') else 'QUALIFICATION_FAILED'))),
            'result':result}}
    if action=='qualify_apps':
        result=guest(target,nodes[0],base,(ROOT/'scripts/node_kubernetes.py').read_bytes(),
            {'action':action,'operation_id':operation},root=True,timeout=900)
        passed=bool(result['checks']) and all(result['checks'].values())
        return {'private':{'operation_id':operation,'result':result},'safe':{
            'status':'verified' if passed else 'blocked','code':'APPLICATION_PERSISTENCE_SWITCHOVER_ISOLATION_VERIFIED' if passed else 'APPLICATION_QUALIFICATION_FAILED',
            'checks':result['checks'],'abrupt_node_fencing_qualified':False,'cloud_calls_enabled':False}}
    if action in ('install_postgres','install_hermes','install_hermes_base','inspect_apps'):
        import kubernetes_apps
        lock=json.loads((ROOT/'versions.lock.yaml').read_text())
        values={'action':'install_hermes' if action=='install_hermes_base' else action,'operation_id':operation}
        if action!='inspect_apps':
            qualification=payload['storage_qualification']
            if qualification['operation_id']!=operation or len(qualification['result']['checks'])!=5 or not all(qualification['result']['checks'].values()):
                raise ValueError('VERIFIED_STORAGE_REQUIRED')
        if action=='install_postgres':
            values.update(operator=kubernetes_apps.operator(lock),database=kubernetes_apps.postgres(lock,payload['instance']['config']))
        if action in ('install_hermes','install_hermes_base'):
            if action=='install_hermes_base':
                import copy
                lock=copy.deepcopy(lock)
                lock['hermes_tools']['enabled']=False
                lock['knowledge']['enabled']=False
                lock['privacy']['enabled']=False
                values['bootstrap_base']=True
            values.update(hermes=kubernetes_apps.hermes(lock,payload['instance']['config'],payload['pilot']),
                          ingress=kubernetes_apps.ingress(lock,payload['instance']['config'],payload['pilot']))
        result=guest(target,nodes[0],base,(ROOT/'scripts/node_kubernetes.py').read_bytes(),values,root=True,timeout=1200)
        counts={}
        for namespace in ('cnpg-system','arcia-data','arcia-hermes','arcia-ingress'):
            subset=[p for p in result['pods'] if p['metadata']['namespace']==namespace]
            counts[namespace]={'pod_count':len(subset),'ready_pod_count':sum(any(c['type']=='Ready' and c['status']=='True' for c in p.get('status',{}).get('conditions',[])) for p in subset)}
        patterns={'Permission denied':'FILESYSTEM_PERMISSION_DENIED','Read-only file system':'READ_ONLY_FILESYSTEM',
            'ModuleNotFoundError':'PYTHON_MODULE_MISSING','CrashLoopBackOff':'CRASH_LOOP','ImagePullBackOff':'IMAGE_PULL_FAILED',
            'FailedScheduling':'POD_SCHEDULING_FAILED','FailedMount':'VOLUME_MOUNT_FAILED','FailedAttachVolume':'VOLUME_ATTACH_FAILED',
            'FATAL':'APPLICATION_FATAL','connection refused':'CONNECTION_REFUSED','i/o timeout':'NETWORK_TIMEOUT'}
        diagnostics=json.dumps(result)
        passed=result.get('ready',True)
        return {'private':{'operation_id':operation,'result':result},'safe':{'status':('inspected' if action=='inspect_apps' else 'verified') if passed else 'blocked',
            'code':'QUALIFICATION_APPLICATIONS_INSPECTED' if action=='inspect_apps' else ('QUALIFICATION_APPLICATION_DEPLOYED' if passed else 'QUALIFICATION_APPLICATION_NOT_READY'),
            'workloads':counts,'known_error_codes':[code for pattern,code in patterns.items() if pattern.casefold() in diagnostics.casefold()],
            'cloud_calls_enabled':bool(action=='install_hermes' and lock.get('privacy',{}).get('enabled')),'business_integrations_enabled':False}}
    if action=='inspect_vmware':
        result=guest(target,nodes[0],base,(ROOT/'scripts/node_kubernetes.py').read_bytes(),
            {'action':action,'nodes':[v['name'] for v in payload['instance']['config']['nodes']],
             'api_endpoint':payload['instance']['config']['network']['api_endpoint']},root=True)
        allowed_reasons={'CrashLoopBackOff','ImagePullBackOff','ErrImagePull','ContainerCreating','Pending','Running','Succeeded','Failed'}
        reasons={c.get('state',{}).get('waiting',{}).get('reason','') for p in result['workloads'] for c in p.get('status',{}).get('containerStatuses',[])}
        logs=json.dumps(result['diagnostics'])+json.dumps(result.get('storage_diagnostics',{}))
        patterns={'x509':'VMWARE_TLS_FAILED','NoPermission':'VMWARE_PERMISSION_DENIED','InvalidLogin':'VMWARE_AUTHENTICATION_FAILED',
            'not found':'VMWARE_OBJECT_NOT_FOUND','connection refused':'CONNECTION_REFUSED','timed out':'OPERATION_TIMEOUT',
            'failed to parse':'CONFIGURATION_PARSE_FAILED','failed to read':'CONFIGURATION_READ_FAILED',
            'VirtualCenterIP is empty':'VCENTER_CONFIG_EMPTY','invalid parameter':'INVALID_STORAGE_PARAMETER',
            'Permission denied':'FILESYSTEM_PERMISSION_DENIED','FailedMount':'VOLUME_MOUNT_FAILED',
            'FailedAttachVolume':'VOLUME_ATTACH_FAILED','FailedScheduling':'POD_SCHEDULING_FAILED',
            'ProvisioningFailed':'VOLUME_PROVISIONING_FAILED','does not exist':'OBJECT_DOES_NOT_EXIST',
            'no shared datastores':'NO_SHARED_DATASTORES','not authorized':'NOT_AUTHORIZED'}
        return {'private':{'operation_id':operation,'result':result},'safe':{'status':'inspected',
            'code':'VMWARE_KUBERNETES_STATE_INSPECTED','initialized_node_count':sum(n['provider_id_present'] and not n['uninitialized'] for n in result['nodes']),
            'pod_count':result['pod_count'],'ready_pod_count':result['ready_pod_count'],'pending_pod_count':result['pending_pod_count'],
            'container_waiting_reasons':sorted(reasons & allowed_reasons),
            'known_error_codes':[code for pattern,code in patterns.items() if pattern.casefold() in logs.casefold()]}}
    if action=='qualify_storage':
        lock=json.loads((ROOT/'versions.lock.yaml').read_text())
        result=guest(target,nodes[0],base,(ROOT/'scripts/node_kubernetes.py').read_bytes(),
            {'action':action,'operation_id':operation,'image':lock['qualification_image']['pinned'],
             'nodes':[v['name'] for v in payload['instance']['config']['nodes']],
             'api_endpoint':payload['instance']['config']['network']['api_endpoint']},root=True,timeout=1200)
        passed=len(result['checks'])==5 and all(result['checks'].values()) and not result.get('failure')
        return {'private':{'operation_id':operation,'result':result},'safe':{'status':'verified' if passed else 'blocked',
            'code':'CSI_RWOP_PERSISTENCE_VERIFIED' if passed else 'CSI_STORAGE_QUALIFICATION_FAILED',
            'checks':result['checks'],'abrupt_node_fencing_qualified':False,'rwx_qualified':False}}
    if action=='install_vmware':
        import kubernetes_vmware
        lock=json.loads((ROOT/'versions.lock.yaml').read_text())
        documents=kubernetes_vmware.prepare(payload,lock)
        result=guest(target,nodes[0],base,(ROOT/'scripts/node_kubernetes.py').read_bytes(),
            {'action':action,'operation_id':operation,'documents':documents,
             'nodes':[v['name'] for v in payload['instance']['config']['nodes']],
             'api_endpoint':payload['instance']['config']['network']['api_endpoint']},root=True,timeout=900)
        initialized=sum(n['provider_id_present'] and not n['uninitialized'] for n in result['nodes'])
        passed=all(result['rollouts']) and initialized==3
        diagnostic_text=json.dumps(result['diagnostics'])
        patterns={'x509':'VMWARE_TLS_FAILED','NoPermission':'VMWARE_PERMISSION_DENIED','InvalidLogin':'VMWARE_AUTHENTICATION_FAILED',
            'not found':'VMWARE_OBJECT_NOT_FOUND','connection refused':'CONNECTION_REFUSED','timed out':'OPERATION_TIMEOUT'}
        return {'private':{'operation_id':operation,'result':result},'safe':{'status':'verified' if passed else 'blocked',
            'code':'VMWARE_CPI_CSI_ROLLOUTS_VERIFIED' if passed else 'VMWARE_FOUNDATION_NOT_READY',
            'rollouts':result['rollouts'],'initialized_node_count':initialized,
            'known_error_codes':[code for pattern,code in patterns.items() if pattern.casefold() in diagnostic_text.casefold()],
            'cpi_version':lock['components']['vsphere_cpi']['version'],'csi_version':lock['components']['vsphere_csi']['version'],
            'storage_class_count':len(result['storage_classes']),'storage_qualified':False}}
    if action=='inspect_cluster':
        script=(ROOT/'scripts/node_kubernetes.py').read_bytes()
        results=[guest(target,n,base,script,{'action':action,'nodes':[v['name'] for v in payload['instance']['config']['nodes']],
            'api_endpoint':payload['instance']['config']['network']['api_endpoint']},root=True) for n in nodes]
        expected=json.loads((ROOT/'versions.lock.yaml').read_text())['components']['k3s']['version']
        passed=all(r['ready'] and r['vip_ready'] and r['encryption_enabled'] and r['encryption_hashes_match'] and
            len(r['nodes'])==3 and all(n['ready'] and n['control_plane'] and n['etcd'] and n['version']==expected for n in r['nodes']) for r in results)
        return {'private':{'operation_id':operation,'results':results},'safe':{'status':'verified' if passed else 'blocked',
            'code':'K3S_API_VIP_ENCRYPTION_VERIFIED' if passed else 'K3S_CLUSTER_HEALTH_FAILED',
            'node_count':3,'ready_node_count':sum(n['ready'] for n in results[0]['nodes']),
            'provider_id_count':sum(n['provider_id_present'] for n in results[0]['nodes']),
            'uninitialized_node_count':sum(n['uninitialized'] for n in results[0]['nodes']),
            'api_checks':sum(r['ready'] for r in results),'vip_api_checks':sum(r['vip_ready'] for r in results),
            'encryption_checks':sum(r['encryption_enabled'] and r['encryption_hashes_match'] for r in results),
            'pod_count':results[0]['pod_count'],'pending_pod_count':results[0]['pending_pod_count'],
            'storage_class_count':len(results[0]['storage_classes']),'k3s_version':expected,
            'production_failover_qualified':False,'csi_qualified':False}}
    if action=='install_k3s': return install_k3s(payload,target,nodes,base)
    if action in ('install_vip','qualify_vip','inspect_vip','qualify_live_vip'): return vip_operation(payload,target,nodes,base)
    script = (ROOT/'scripts/node_foundation.py').read_bytes()
    if action=='pause_k3s':
        lock=json.loads((ROOT/'versions.lock.yaml').read_text())
        inventory=harness.render(payload['instance']['config'],payload['instance']['k3s_token'],lock)
        hosts=inventory['all']['children']['k3s_servers']['hosts']
        results=[guest(target,n,base,script,{'action':'stop_owned_k3s','version':lock['components']['k3s']['version'],
            'config':list(hosts.values())[i]['hermes_k3s_config']},root=True) for i,n in enumerate(nodes)]
        passed=all(r['stopped'] for r in results)
        return {'private':{'operation_id':operation,'nodes':results},'safe':{'status':'paused' if passed else 'blocked',
            'code':'OWNED_K3S_STOPPED_FOR_HANDOFF' if passed else 'K3S_PAUSE_FAILED','active_service_count':0 if passed else None,
            'owned_installation_count':sum(r['owned_installation_present'] for r in results),'data_removed':False}}
    if action=='inspect_k3s':
        results=[guest(target,n,base,script,{'action':'inspect_k3s'},root=True) for n in nodes]
        patterns={'flag provided but not defined':'UNSUPPORTED_FLAG','failed to find memory cgroup':'MEMORY_CGROUP_MISSING',
            'failed to validate server configuration':'CONFIGURATION_INVALID','address already in use':'PORT_ALREADY_BOUND',
            'failed to get CA certs':'JOIN_CA_UNREACHABLE','no space left':'DISK_FULL','permission denied':'PERMISSION_DENIED',
            'invalid CIDR':'CIDR_INVALID','failed to resolve':'DNS_RESOLUTION_FAILED','datastore':'DATASTORE_RELATED',
            'incorrect cluster flag':'CLUSTER_FLAG_MISMATCH','not found':'FILE_OR_COMMAND_NOT_FOUND',
            'not permitted':'OPERATION_NOT_PERMITTED','unknown flag':'UNSUPPORTED_FLAG'}
        safe=[]
        for index,r in enumerate(results,1):
            safe.append({'node':'N'+str(index),'binary_present':r['binary_present'],'config_present':r['config_present'],
                'asset_layout':r['asset_layout'],
                'active':'ActiveState=active' in r['unit'],'known_error_codes':sorted({code for pattern,code in patterns.items() if pattern.casefold() in r['journal'].casefold()}),
                'exit_status':int(re.search(r'^ExecMainStatus=(\d+)$',r['unit'],re.M)[1]) if re.search(r'^ExecMainStatus=(\d+)$',r['unit'],re.M) else None,
                'binary_version_matches':json.loads((ROOT/'versions.lock.yaml').read_text())['components']['k3s']['version'] in r['version'],
                'missing_standard_commands':[name for name in ('sh','bash','iptables','ip6tables','ip','nft','tar','gzip','zstd','pigz','mount','umount','nsenter','unshare','modprobe','lsmod','which','hostname','getent','find','awk','sed','grep','containerd','runc','containerd-shim-runc-v2','k3s-server','file','touch','k3s')
                    if re.search(r'exec:.*?[\\"]'+re.escape(name)+r'[\\"].*?(?:not found|PATH)',r['journal'])],
                'failure_components':[term for term in ('iptables','ip6tables','modprobe','containerd','cgroup','etcd','flannel','zstd','pigz','kubelet','127.0.0.1','systemd','token-file','config.yaml','cluster-init','PATH','swap')
                    if any(term.casefold() in line.casefold() for line in r['journal'].splitlines() if any(level in line.casefold() for level in ('fatal','error','not found','failed')))]})
        return {'private':{'operation_id':operation,'nodes':results},'safe':{'status':'inspected','code':'K3S_SERVICES_INSPECTED','nodes':safe}}
    if action == 'qualify_ports':
        challenge=secrets.token_hex(32)
        common={'operation_id':operation,'nodes':[n['address'] for n in nodes],
                'challenge':challenge,'expires_at':time.time()+300}
        results=[];cleanup=[];started=[]
        try:
            for index,node in enumerate(nodes,1):
                started.append(node)
                values={**common,'action':'start_listeners','node':index,
                        'listener_source':(ROOT/'scripts/network_listener.py').read_text()}
                if not guest(target,node,base,script,values,root=True)['started']: raise ValueError('TEMPORARY_LISTENER_NOT_STARTED')
            for node in nodes:
                results.append(guest(target,node,base,script,{**common,'action':'probe_listeners'},root=True))
        finally:
            for node in started:
                try: cleanup.append(guest(target,node,base,script,{'action':'stop_listeners','operation_id':operation},root=True)['stopped'])
                except Exception: cleanup.append(False)
        passed=len(results)==3 and all(r['passed'] for r in results) and len(cleanup)==3 and all(cleanup)
        return {'private':{'operation_id':operation,'nodes':results,'cleanup':cleanup},
            'safe':{'status':'verified' if passed else 'blocked','code':'UNDERLAY_K3S_PORTS_VERIFIED' if passed else 'UNDERLAY_K3S_PORTS_FAILED',
                    'node_count':len(results),'tcp_ports':[443,6443,2379,2380,10250],'udp_ports':[8472],
                    'directional_checks':sum(len(r['checks']) for r in results),
                    'passed_check_count':sum(sum(c['passed'] for c in r['checks']) for r in results),
                    'temporary_listeners_stopped':len(cleanup)==3 and all(cleanup),'firewall_modified':False,'k3s_installed':False}}
    results = []
    for node in nodes:
        values = {'action': action, 'operation_id': operation, 'address': node['address'],
                  'peers': [n['address'] for n in nodes if n != node]}
        results.append(guest(target, node, base, script, values, root=True))
    candidates = [r['package_candidates'] for r in results]
    coherent = all(value == candidates[0] for value in candidates)
    safe_versions = {k: v if isinstance(v,str) and re.fullmatch(r'[0-9][A-Za-z0-9.+:~_-]{0,59}',v) else 'unavailable'
                     for k,v in candidates[0].items()}
    return {'private': {'operation_id': operation, 'nodes': results},
        'safe': {'status': 'inspected', 'code': 'NODE_FOUNDATION_INSPECTED', 'node_count': len(results),
            'package_candidates_consistent': coherent, 'package_candidates': safe_versions,
            'package_sha256':{k:v if isinstance(v,str) and re.fullmatch(r'[a-f0-9]{64}',v) else None for k,v in results[0]['package_sha256'].items()},
            'k3s_present_count': sum(r['k3s_present'] for r in results),
            'existing_keepalived_configuration_count': sum(r['keepalived_configuration_present'] for r in results),
            'occupied_listener_count': sum(sum(r['ports_occupied'].values()) for r in results), 'mutations_performed': False}}


def main():
    try: result = collect(json.load(sys.stdin))
    except Exception as exc:
        result = {'private': {'failure': traceback.format_exc(), 'guest_failure':getattr(exc,'private_output',None)},
                  'safe': {'status': 'blocked', 'code': 'CLUSTER_FOUNDATION_ACTION_FAILED', 'k3s_installed': False}}
    print(json.dumps(result))
    return 2 if result['safe']['status'] == 'blocked' else 0


if __name__ == '__main__': sys.exit(main())
