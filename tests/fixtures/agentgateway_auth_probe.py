"""Sonde HTTP : seuls les codes et booléens quittent le namespace synthétique."""
import json
import sys
import urllib.error
import urllib.request


def probe(payload):
    def call(token=None, tenant='tenant-a', user='alice', forged=False):
        headers = {'X-ArcIA-Tenant': tenant, 'X-ArcIA-User': user}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        if forged:
            headers.update({'X-OpenWebUI-User-Role': 'admin', 'X-OpenWebUI-User-Id': 'alice'})
        req = urllib.request.Request('http://agentgateway:3000/', headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.status
        except urllib.error.HTTPError as error:
            return error.code
        except OSError:
            return 0

    if payload['mode'] == 'closed':
        return {'bootstrap_closed': call() == 403}
    tokens = payload['tokens']
    statuses = {'valid_a': call(tokens['valid_a']), 'valid_b': call(tokens['valid_b'], 'tenant-b', 'bob'),
        'wrong_tenant': call(tokens['valid_a'], 'tenant-b'), 'wrong_user': call(tokens['valid_a'], user='bob'),
        'missing_grant': call(tokens['missing_grant']), 'anonymous': call(), 'forged_headers': call(forged=True)}
    for name in ('invalid_signature', 'expired', 'wrong_audience', 'wrong_issuer', 'missing_exp', 'missing_sub'):
        statuses[name] = call(tokens[name])
    expected = {'valid_a': 200, 'valid_b': 200, 'wrong_tenant': 403, 'wrong_user': 403, 'missing_grant': 403}
    return {'checks': {name: code == expected.get(name, 401) for name, code in statuses.items()}, 'statuses': statuses}


if __name__ == '__main__':
    print('ARCIA_AGENTGATEWAY=' + json.dumps(probe(json.load(sys.stdin))))
