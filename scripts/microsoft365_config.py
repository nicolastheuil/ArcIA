"""Offline preparation only. Never print configuration values or resolve secrets."""
import argparse
import json
from pathlib import Path
import sys

import yaml
from yaml.events import AliasEvent
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 131072


class ContractError(ValueError):
    pass


class UniqueLoader(yaml.SafeLoader):
    pass


def unique_mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if not isinstance(key, str) or key in result:
            raise ContractError('M365_YAML_DUPLICATE_OR_INVALID_KEY')
        result[key] = loader.construct_object(value_node)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def load_config(path):
    with Path(path).open('rb') as handle:
        content = handle.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise ContractError('M365_CONFIG_TOO_LARGE')
    try:
        text = content.decode('utf-8')
        if any(isinstance(event, AliasEvent) or getattr(event, 'anchor', None)
               for event in yaml.parse(text)):
            raise ContractError('M365_YAML_ALIASES_FORBIDDEN')
        # Keep ISO dates as strings, as required by JSON Schema.
        return yaml.load(text, Loader=UniqueLoader)
    except ContractError:
        raise
    except (yaml.YAMLError, UnicodeError, TypeError):
        raise ContractError('M365_YAML_INVALID') from None


# Do not modify SafeLoader globally: other harness YAML readers retain their semantics.
UniqueLoader.yaml_implicit_resolvers = {
    key: [(tag, regex) for tag, regex in resolvers if tag != 'tag:yaml.org,2002:timestamp']
    for key, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def validate(config, require_ready=False):
    schema = json.loads((ROOT / 'schemas/microsoft365.schema.json').read_text(encoding='utf-8'))
    Draft202012Validator.check_schema(schema)
    if next(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(config), None):
        raise ContractError('M365_SCHEMA_INVALID')
    apps = config['applications']
    ids = [app['client_id'] for app in apps.values() if app['client_id']]
    if len(set(value.lower() for value in ids)) != len(ids):
        raise ContractError('M365_APPLICATION_IDENTITIES_MUST_BE_SEPARATE')
    if config['endpoints']['portal_base_url'] and config['endpoints']['portal_base_url'] == config['endpoints']['bot_base_url']:
        raise ContractError('M365_DISTINCT_ENDPOINTS_REQUIRED')
    if apps['sharepoint']['application_permissions'] != ['Sites.Selected']:
        raise ContractError('M365_SELECTED_PERMISSION_REQUIRED')
    if 'OnlineMeetingTranscript.Read.All' not in apps['meetings']['application_permissions']:
        raise ContractError('M365_TRANSCRIPT_PERMISSION_REQUIRED')
    for app in ('web', 'bot', 'outlook_delegated'):
        if not {'openid', 'profile'} <= set(apps[app]['delegated_permissions']):
            raise ContractError('M365_LOGIN_SCOPES_REQUIRED')
    bot_id = apps['bot']['client_id']
    if config['teams']['api_uri'] and (not bot_id or config['teams']['api_uri'].lower() != 'api://botid-' + bot_id.lower()):
        raise ContractError('M365_BOT_API_ID_MISMATCH')
    if config['meetings']['speaker_attribution'] != 'allowed' and config['meetings']['transcript_format'] == 'text/vtt':
        raise ContractError('M365_SPEAKER_FORMAT_NOT_AUTHORIZED')
    if (config['meetings']['trigger'] == 'organizer_webhooks') != config['webhooks']['enabled']:
        raise ContractError('M365_WEBHOOK_TRIGGER_MISMATCH')
    if config['webhooks']['include_resource_data'] and not all(config['webhooks'][key] for key in ('encryption_private_key_reference', 'encryption_certificate_id')):
        raise ContractError('M365_WEBHOOK_ENCRYPTION_REQUIRED')
    # This contract describes an integration that does not exist in the current runtime.
    # No boolean or claimed qualification in an instance file can override that fact.
    active = config['enabled'] or any(config[key]['enabled'] for key in ('identity', 'teams', 'meetings', 'sharepoint', 'webhooks'))
    active = active or any(config['outlook'][key] for key in ('delegated_enabled', 'application_enabled', 'writes_enabled'))
    if active or config['governance']['runtime_qualification_verified']:
        raise ContractError('M365_RUNTIME_NOT_IMPLEMENTED')
    report = preparation_report(config)
    if require_ready:
        raise ContractError('M365_ADMIN_INPUTS_REQUIRED' if report['missing_admin_inputs'] else 'M365_RUNTIME_NOT_IMPLEMENTED')
    return report


def preparation_report(config):
    # Values, names, IDs, paths and source error text must never enter this report.
    missing = int(not config['tenant_id'])
    missing += sum(not config['endpoints'][key] for key in ('portal_base_url', 'bot_base_url'))
    required_apps = ('web', 'bot', 'meetings', 'sharepoint', 'outlook_delegated')
    for key in required_apps:
        app = config['applications'][key]
        missing += sum(not app[name] for name in ('client_id', 'registration_object_id', 'service_principal_object_id'))
        missing += int(not app['credential']['expires_on']) + int(app['admin_consent'] == 'pending')
    missing += sum(not value for key in ('role_group_ids', 'web_role_ids', 'bot_role_ids') for value in config['identity'][key].values())
    missing += int(not config['identity']['conditional_access_verified'])
    missing += sum(not config['teams'][key] for key in ('azure_bot_resource_id', 'package_app_id', 'catalog_object_id', 'manifest_version', 'api_uri', 'pilot_group_id', 'publication_verified'))
    missing += sum(not config['meetings'][key] for key in ('application_access_policy_name', 'organizer_object_ids', 'transcription_policy_name', 'transcription_verified', 'graph_transcript_access_verified'))
    missing += int(not config['sharepoint']['sites'])
    missing += sum(not site['grant_verified'] for site in config['sharepoint']['sites'])
    missing += int(not config['outlook']['pilot_group_id'])
    missing += int(not config['governance']['retention_days']) + int(not config['governance']['evidence_reference'])
    return {'code': 'M365_PREPARATION_VALID', 'status': 'draft', 'missing_admin_inputs': missing,
            'runtime_implemented': False, 'runtime_enabled': False, 'tenant_contacted': False,
            'secrets_resolved': False, 'fresh_cluster_tested': False,
            'remaining_gates': ['ADMIN_TENANT_SETUP', 'PROTECTED_CREDENTIAL_ENROLLMENT',
                                'ADAPTER_AND_WIZARD_IMPLEMENTATION', 'SERVER_IAM_ACL_APPROVALS',
                                'SYNTHETIC_END_TO_END_QUALIFICATION', 'EXPLICIT_DATA_OPENING']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('validate', 'plan'))
    parser.add_argument('--config', required=True)
    parser.add_argument('--require-ready', action='store_true')
    args = parser.parse_args()
    try:
        report = validate(load_config(args.config), args.require_ready)
        if args.command == 'plan':
            report['code'] = 'M365_OFFLINE_PLAN'
        print(json.dumps(report))
        return 0
    except ContractError as exc:
        print(json.dumps({'status': 'blocked', 'code': str(exc)}))
    except Exception:
        print(json.dumps({'status': 'blocked', 'code': 'M365_CONFIG_UNREADABLE'}))
    return 2


if __name__ == '__main__':
    sys.exit(main())
