"""Témoin A2A 0.3 déterministe, sans LLM, stockage métier ni accès extérieur.

Il mesure la structure envoyée par le pont Chat Completions de LiteLLM ; ce
serveur de test n'est pas un runtime de production et ne qualifie pas Hermes.
"""
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import threading
import uuid


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def send_json(self, value, status=200):
        data = json.dumps(value).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def authenticated(self):
        return hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + self.server.token)

    def do_GET(self):
        if self.path == '/health':
            self.send_json({'ready': True})
        elif not self.authenticated():
            self.send_json({'error': 'unauthorized'}, 401)
        elif self.path in ('/.well-known/agent-card.json', '/.well-known/agent.json'):
            self.send_json({'name': 'ArcIA synthetic witness', 'description': 'Synthetic only',
                            'version': '1.0.0', 'protocolVersion': '0.3.0',
                            'url': 'http://a2a-synthetic:9900/', 'capabilities': {'streaming': True},
                            'defaultInputModes': ['text/plain'], 'defaultOutputModes': ['text/plain'],
                            'skills': []})
        elif self.path == '/observations':
            with self.server.lock:
                self.send_json(list(self.server.observations))
        else:
            self.send_json({'error': 'not found'}, 404)

    def do_POST(self):
        if not self.authenticated():
            self.send_json({'error': 'unauthorized'}, 401)
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 65536:
                self.send_json({'error': 'invalid size'}, 413)
                return
            body = json.loads(self.rfile.read(length))
            request_id, method, params = body['id'], body['method'], body.get('params', {})
            if not isinstance(params, dict):
                raise ValueError('params')
        except (ValueError, KeyError, TypeError):
            self.send_json({'error': 'invalid request'}, 400)
            return
        with self.server.lock:
            if method in ('message/send', 'message/stream'):
                message = params.get('message', {})
                if not isinstance(message, dict) or not isinstance(message.get('parts'), list):
                    self.send_json({'jsonrpc': '2.0', 'id': request_id,
                                    'error': {'code': -32602, 'message': 'Invalid message'}})
                    return
                context = message.get('contextId') or uuid.uuid4().hex
                self.server.observations.append({'method': method, 'message_id': message.get('messageId'),
                    'context_id': message.get('contextId'), 'parts_count': len(message['parts']),
                    'message_fields': sorted(message.keys()), 'metadata_present': bool(params.get('metadata'))})
                task = {'kind': 'task', 'id': uuid.uuid4().hex, 'contextId': context,
                        'status': {'state': 'completed'}, 'artifacts': [{'artifactId': 'synthetic-text',
                        'parts': [{'kind': 'text', 'text': 'ARCIA_A2A_SYNTHETIC_OK'}]}]}
                self.server.tasks[task['id']] = task
                result = {'jsonrpc': '2.0', 'id': request_id, 'result': task}
            elif method in ('tasks/get', 'tasks/cancel') and params.get('id') in self.server.tasks:
                task = self.server.tasks[params['id']]
                if method == 'tasks/cancel':
                    self.send_json({'jsonrpc': '2.0', 'id': request_id,
                                    'error': {'code': -32002, 'message': 'Task already completed'}})
                    return
                result = {'jsonrpc': '2.0', 'id': request_id, 'result': task}
            else:
                result = {'jsonrpc': '2.0', 'id': request_id,
                          'error': {'code': -32001, 'message': 'Task or method not found'}}
        if method == 'message/stream':
            data = ('data: ' + json.dumps(result) + '\n\n').encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_json(result)


def make_server(address, token):
    if not token:
        raise ValueError('A fixture token is required')
    server = ThreadingHTTPServer(address, Handler)
    server.token, server.observations, server.tasks, server.lock = token, [], {}, threading.Lock()
    return server


if __name__ == '__main__':
    make_server(('0.0.0.0', 9900), os.environ['A2A_SYNTHETIC_TOKEN']).serve_forever()
