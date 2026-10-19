"""Migration idempotente de l'ancienne clé statique du portail ArcIA."""
import hashlib
import json
import os
import sys
import urllib.parse
import urllib.request

LEGACY_KEY_ALIAS = 'openwebui-direct-simple'
# Identité publique du bootstrap historique, jamais utilisée pour créer une clé.
LEGACY_KEY_HASH = hashlib.sha256(b'sk-arcia-openwebui-direct-token').hexdigest()


def consumer_safe(env):
    """Ne retirer la clé que si le portail utilise la connexion serveur actuelle."""
    master = env.get('LITELLM_MASTER_KEY', '')
    keys = env.get('OPENAI_API_KEYS', '').split(';')
    return bool(master and keys[0] == master
                and env.get('ENABLE_PERSISTENT_CONFIG') == 'false'
                and not any(hashlib.sha256(v.encode()).hexdigest() == LEGACY_KEY_HASH
                            for v in env.values()))


def retire(request):
    path = '/key/list?' + urllib.parse.urlencode({
        'return_full_object': 'true', 'key_hash': LEGACY_KEY_HASH})

    def matches():
        data = request(path)
        if not isinstance(data, dict) or not isinstance(data.get('keys'), list):
            raise RuntimeError('Réponse de migration LiteLLM invalide.')
        return [key for key in data['keys'] if isinstance(key, dict)
                and key.get('token') == LEGACY_KEY_HASH
                and key.get('key_alias') == LEGACY_KEY_ALIAS]

    if not matches():
        return {'retired': False, 'verified_absent': True}
    request('/key/delete', {'keys': [LEGACY_KEY_HASH]})
    if matches():
        raise RuntimeError('Retrait de la clé historique non confirmé.')
    return {'retired': True, 'verified_absent': True}


def main():
    if '--check-consumer' in sys.argv:
        print('ARCIA_LEGACY_CONSUMER_SAFE=' + json.dumps(consumer_safe(os.environ)))
        return

    def request(path, payload=None):
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request('http://127.0.0.1:4000' + path, data=data, headers={
            'Authorization': 'Bearer ' + os.environ['LITELLM_MASTER_KEY'],
            'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=15) as response:
            return json.load(response)

    try:
        print('ARCIA_LEGACY_KEY_RESULT=' + json.dumps(retire(request)))
    except Exception:
        # Les exceptions HTTP peuvent contenir des identifiants : sortie bornée.
        print('ARCIA_LEGACY_KEY_ERROR=migration_failed', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
