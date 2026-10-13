"""MCP stdio catalogue inside each Hermes Pod. No network, credentials or writes."""
import json
import sys
from catalog import Catalog

TOOLS = [
    {'name': 'catalog_search', 'description': 'Search the complete local skill catalogue before specialized work. Query may be French or English. Returns metadata; use catalog_load for selected instructions.',
     'inputSchema': {'type': 'object', 'properties': {'query': {'type': 'string'}, 'provider': {'type': 'string'}, 'limit': {'type': 'integer', 'minimum': 1, 'maximum': 30}}, 'additionalProperties': False}},
    {'name': 'catalog_load', 'description': 'Load a skill or one of its reference/script files as text. Does not install dependencies or execute scripts. Exact id from catalog_search required.',
     'inputSchema': {'type': 'object', 'properties': {'id': {'type': 'string'}, 'file_path': {'type': 'string'}, 'offset': {'type': 'integer', 'minimum': 0}}, 'required': ['id'], 'additionalProperties': False}},
    {'name': 'catalog_sources', 'description': 'List source revisions, credits, licences, counts and the authoritative owner of memory, delegation, compression and model routing.',
     'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False}},
]


def dispatch(request, catalog):
    method = request.get('method')
    if method == 'initialize':
        return {'protocolVersion': request.get('params', {}).get('protocolVersion', '2024-11-05'),
                'capabilities': {'tools': {}}, 'serverInfo': {'name': 'arcia-skills', 'version': '1.0.0'}}
    if method == 'ping':
        return {}
    if method == 'tools/list':
        return {'tools': TOOLS}
    if method != 'tools/call':
        raise ValueError('MCP_METHOD_UNSUPPORTED')
    params = request.get('params', {})
    name, args = params.get('name'), params.get('arguments', {})
    if not isinstance(args, dict):
        raise ValueError('MCP_ARGUMENTS_INVALID')
    schema = next((t['inputSchema'] for t in TOOLS if t['name'] == name), None)
    if schema is None or set(args)-set(schema['properties']) or not set(schema.get('required', [])) <= set(args):
        raise ValueError('MCP_ARGUMENTS_INVALID')
    if name == 'catalog_search':
        result = catalog.search(**args)
    elif name == 'catalog_load':
        result = catalog.load(args['id'], args.get('file_path', 'SKILL.md'), args.get('offset', 0))
    else:
        result = catalog.sources()
    return {'content': [{'type': 'text', 'text': json.dumps(result, ensure_ascii=False)}], 'isError': False}


def main():
    catalog = Catalog()
    for line in sys.stdin.buffer:
        if len(line) > 16384:
            continue
        request = None
        try:
            request = json.loads(line)
            if not isinstance(request, dict) or 'id' not in request:
                continue
            result = {'jsonrpc': '2.0', 'id': request['id'], 'result': dispatch(request, catalog)}
        except Exception:
            result = {'jsonrpc': '2.0', 'id': request.get('id') if isinstance(request, dict) else None,
                      'error': {'code': -32602, 'message': 'SKILLS_REQUEST_REFUSED'}}
        sys.stdout.write(json.dumps(result, ensure_ascii=False)+'\n')
        sys.stdout.flush()


if __name__ == '__main__':
    main()
