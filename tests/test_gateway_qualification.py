"""Témoin A2A synthétique : authentification, contexte et absence de rétention du prompt."""
import importlib.util
import json
from pathlib import Path
import threading
import unittest
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def load_fixture():
    spec = importlib.util.spec_from_file_location('a2a_synthetic', ROOT / 'tests/fixtures/a2a_synthetic_agent.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module




class SyntheticAgentTests(unittest.TestCase):
    def setUp(self):
        self.fixture = load_fixture()
        self.server = self.fixture.make_server(('127.0.0.1', 0), 'synthetic-test-only')
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = 'http://127.0.0.1:' + str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def call(self, method, params, token='synthetic-test-only', stream=False):
        body = json.dumps({'jsonrpc': '2.0', 'id': 'test', 'method': method, 'params': params}).encode()
        req = urllib.request.Request(self.url, data=body, headers={'Authorization': 'Bearer ' + token,
                                                                  'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=3) as response:
            return response.read().decode() if stream else json.load(response)

    def message(self, context='context-a', message_id='message-a'):
        return {'message': {'kind': 'message', 'role': 'user', 'messageId': message_id,
                            'contextId': context, 'parts': [{'kind': 'text', 'text': 'Synthetic only'}]}}

    def test_unauthenticated_requests_leave_no_observation(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.call('message/send', self.message(), token='wrong')
        self.assertEqual(error.exception.code, 401)
        self.assertEqual(self.server.observations, [])

    def test_task_contexts_stay_separate_and_are_queryable(self):
        first = self.call('message/send', self.message())['result']
        second = self.call('message/send', self.message('context-b', 'message-b'))['result']
        restored = self.call('tasks/get', {'id': first['id']})['result']
        self.assertEqual(restored['contextId'], 'context-a')
        self.assertNotEqual(first['id'], second['id'])
        self.assertEqual(second['contextId'], 'context-b')

    def test_probe_records_structure_without_retaining_prompt(self):
        params = self.message()
        params['message']['parts'][0]['text'] = 'sensitive synthetic marker'
        self.call('message/send', params)
        stored = json.dumps(self.server.observations)
        self.assertNotIn('sensitive synthetic marker', stored)
        self.assertEqual(self.server.observations[0]['context_id'], 'context-a')

    def test_stream_contains_status_and_completed_task(self):
        stream = self.call('message/stream', self.message(), stream=True)
        events = [json.loads(line[6:]) for line in stream.splitlines() if line.startswith('data: ')]
        self.assertEqual(events[-1]['result']['status']['state'], 'completed')
        self.assertEqual(events[-1]['result']['contextId'], 'context-a')

    def test_unknown_task_is_an_explicit_protocol_error(self):
        response = self.call('tasks/get', {'id': 'absent'})
        self.assertEqual(response['error']['code'], -32001)


if __name__ == '__main__':
    unittest.main()
