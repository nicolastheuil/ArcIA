import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import microsoft365_config as m365


class Microsoft365PreparationTests(unittest.TestCase):
    def setUp(self):
        self.config = m365.load_config(m365.ROOT / 'examples/microsoft365/microsoft365.yaml')

    def test_draft_is_offline_inactive_and_not_ready(self):
        result = m365.validate(self.config)
        self.assertGreater(result['missing_admin_inputs'], 0)
        self.assertFalse(result['tenant_contacted'])
        self.assertFalse(result['runtime_enabled'])
        with self.assertRaisesRegex(m365.ContractError, 'M365_ADMIN_INPUTS_REQUIRED'):
            m365.validate(self.config, require_ready=True)

    def test_plaintext_credentials_and_unknown_settings_are_rejected(self):
        for field in ('client_secret', 'private_key', 'access_token', 'password', 'tenant_override'):
            with self.subTest(field=field):
                config = copy.deepcopy(self.config)
                config['applications']['web'][field] = 'sensitive-fixture'
                with self.assertRaisesRegex(m365.ContractError, 'M365_SCHEMA_INVALID'):
                    m365.validate(config)

    def test_global_permissions_and_writes_cannot_be_introduced(self):
        for app, permission in (('sharepoint', 'Sites.Read.All'), ('bot', 'Chat.Read.All'),
                                ('outlook_application', 'Mail.Read'), ('meetings', 'CallTranscripts.Read.All')):
            with self.subTest(app=app):
                config = copy.deepcopy(self.config)
                config['applications'][app]['application_permissions'] = [permission]
                with self.assertRaisesRegex(m365.ContractError, 'M365_SCHEMA_INVALID'):
                    m365.validate(config)
        self.config['applications']['outlook_delegated']['delegated_permissions'].append('Mail.Send')
        with self.assertRaisesRegex(m365.ContractError, 'M365_SCHEMA_INVALID'):
            m365.validate(self.config)

    def test_instance_claim_cannot_enable_missing_runtime(self):
        for section in ('identity', 'teams', 'meetings', 'sharepoint'):
            config = copy.deepcopy(self.config)
            config[section]['enabled'] = True
            with self.assertRaisesRegex(m365.ContractError, 'M365_RUNTIME_NOT_IMPLEMENTED'):
                m365.validate(config)
        self.config['governance']['runtime_qualification_verified'] = True
        with self.assertRaisesRegex(m365.ContractError, 'M365_RUNTIME_NOT_IMPLEMENTED'):
            m365.validate(self.config)

    def test_bot_binding_and_separate_identities(self):
        appid = '12345678-1234-1234-1234-123456789abc'
        self.config['applications']['bot']['client_id'] = appid
        self.config['teams']['api_uri'] = 'api://botid-' + appid
        m365.validate(self.config)
        self.config['teams']['api_uri'] = 'api://botid-12345678-1234-1234-1234-123456789abd'
        with self.assertRaisesRegex(m365.ContractError, 'M365_BOT_API_ID_MISMATCH'):
            m365.validate(self.config)
        self.config['teams']['api_uri'] = None
        self.config['applications']['web']['client_id'] = appid.upper()
        with self.assertRaisesRegex(m365.ContractError, 'M365_APPLICATION_IDENTITIES_MUST_BE_SEPARATE'):
            m365.validate(self.config)

    def test_yaml_duplicates_aliases_tags_and_size_are_rejected(self):
        for value in ('enabled: false\nenabled: true\n', 'x: &a []\ny: *a\n',
                      'x: !!python/object/apply:os.system [echo unsafe]\n', 'x' * (m365.MAX_BYTES + 1)):
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'input.yaml'
                path.write_text(value, encoding='utf-8')
                with self.assertRaises(m365.ContractError):
                    m365.load_config(path)

    def test_report_and_failure_never_echo_input(self):
        self.config['applications']['web']['client_secret'] = 'secret-fixture-never-print'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'input.yaml'
            path.write_text(json.dumps(self.config), encoding='utf-8')
            process = subprocess.run([sys.executable, str(m365.ROOT / 'scripts/microsoft365_config.py'),
                                      'validate', '--config', str(path)], capture_output=True, text=True)
            self.assertEqual(process.returncode, 2)
            self.assertNotIn('secret-fixture-never-print', process.stdout + process.stderr)
            self.assertNotIn(str(path), process.stdout + process.stderr)
            self.assertEqual(json.loads(process.stdout)['code'], 'M365_SCHEMA_INVALID')

    def test_unknown_speaker_policy_cannot_authorize_named_vtt(self):
        self.config['meetings']['transcript_format'] = 'text/vtt'
        with self.assertRaisesRegex(m365.ContractError, 'M365_SPEAKER_FORMAT_NOT_AUTHORIZED'):
            m365.validate(self.config)

    def test_missing_resource_ids_cannot_form_an_allowlist(self):
        for section, key in (('meetings', 'organizer_object_ids'), ('outlook', 'mailbox_object_ids')):
            config = copy.deepcopy(self.config)
            config[section][key] = [None]
            with self.assertRaisesRegex(m365.ContractError, 'M365_SCHEMA_INVALID'):
                m365.validate(config)


if __name__ == '__main__':
    unittest.main()
