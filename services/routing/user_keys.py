"""Owner-bound, encrypted provider configuration. No provider call or activation."""
import base64
import json
import secrets
import threading
import time
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ROLE = 'ArcIA.ProviderSelfService'
SECRET = 'personal-provider-keys'
PROVIDERS = {'openrouter': 'OpenRouter', 'openai': 'OpenAI',
             'anthropic': 'Anthropic', 'gemini': 'Google Gemini'}


class KeyConfigError(Exception):
    pass


class UserKeys:
    def __init__(self, slots, encryption_key, enabled=False):
        if len(encryption_key) != 32:
            raise KeyConfigError('KEY_ENCRYPTION_KEY_INVALID')
        self.slots = slots
        self.cipher = AESGCM(encryption_key)
        self.enabled = enabled
        self.lock = threading.Lock()

    def authorize(self, identity):
        if (not self.enabled or identity.get('iss') != self.slots.issuer
                or not isinstance(identity.get('sub'), str) or not identity['sub']
                or not {'ArcIA.User', ROLE} <= set(identity.get('arcia_roles', []))):
            raise PermissionError('PERSONAL_PROVIDER_ROLE_REQUIRED')

    def aad(self, identity):
        return json.dumps([self.slots.operation, identity['iss'], identity['sub']],
                          separators=(',', ':')).encode()

    def record(self, identity, create=False):
        slot = None
        for candidate in self.slots.slots:
            _, _, binding = self.slots.binding(candidate)
            if binding == {'issuer': identity['iss'], 'subject': identity['sub']}:
                if slot is not None:
                    raise KeyConfigError('DUPLICATE_KEY_OWNER')
                slot = candidate
        if slot is None and create:
            slot = self.slots.allocate(identity['sub'])
        if slot is None:
            return None, None, {}
        path = self.slots.resource(slot, 'secrets', SECRET)
        doc = self.slots.api('GET', path)
        if doc['metadata'].get('annotations', {}).get('arcia.io/operation-id') != self.slots.operation:
            raise KeyConfigError('FOREIGN_KEY_STORAGE')
        data = doc.get('data', {})
        if set(data) - {'sealed'}:
            raise KeyConfigError('KEY_STORAGE_FORMAT_REFUSED')
        if not data.get('sealed'):
            return path, doc, {}
        try:
            sealed = base64.b64decode(data['sealed'], validate=True)
            value = json.loads(self.cipher.decrypt(sealed[:12], sealed[12:], self.aad(identity)))
            if value['version'] != 1 or not set(value['keys']) <= set(PROVIDERS):
                raise ValueError()
            return path, doc, value['keys']
        except Exception:
            raise KeyConfigError('KEY_STORAGE_AUTHENTICATION_REFUSED') from None

    @staticmethod
    def metadata(keys):
        return [{'provider': name, 'configured': True, 'updated_at': item['updated_at'],
                 'status': 'stored_not_active'} for name, item in sorted(keys.items())]

    def list(self, identity):
        self.authorize(identity)
        with self.lock:
            _, _, keys = self.record(identity)
            return self.metadata(keys)

    def change(self, identity, value, remove=False):
        self.authorize(identity)
        expected = {'provider'} if remove else {'provider', 'api_key'}
        if not isinstance(value, dict) or set(value) != expected:
            raise ValueError('KEY_CONFIG_FIELDS_REFUSED')
        provider = value['provider']
        if not isinstance(provider, str) or provider not in PROVIDERS:
            raise ValueError('PROVIDER_REFUSED')
        if not remove:
            key = value['api_key']
            if (not isinstance(key, str) or not 8 <= len(key) <= 8192
                    or any(ord(c) < 33 or ord(c) > 126 for c in key)):
                raise ValueError('KEY_FORMAT_REFUSED')
        with self.lock:
            path, doc, keys = self.record(identity, create=not remove)
            if path is None:
                return []
            if remove:
                keys.pop(provider, None)
            else:
                keys[provider] = {'api_key': key, 'updated_at': int(time.time())}
            nonce = secrets.token_bytes(12)
            body = json.dumps({'version': 1, 'keys': keys}, separators=(',', ':')).encode()
            sealed = base64.b64encode(nonce + self.cipher.encrypt(nonce, body, self.aad(identity))).decode()
            # Optimistic concurrency: no retry can overwrite another successful edit.
            self.slots.api('PATCH', path, {'metadata': {'resourceVersion': doc['metadata']['resourceVersion']},
                                          'data': {'sealed': sealed}})
            return self.metadata(keys)
