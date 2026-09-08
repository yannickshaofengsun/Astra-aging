"""Run with python3 -m unittest test_server. No model calls or dependencies."""
import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

import astra_bridge as bridge
from server import MAX_BODY, MAX_JSON_RESPONSE, Server
from simulation import Household


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = Server(0)
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.worker.join()

    def request(self, path, data=None, headers=None, raw=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        body = json.dumps(data) if data is not None else raw
        conn.request('POST' if body is not None else 'GET', path, body,
                     headers or {'Content-Type': 'application/json'})
        result = conn.getresponse()
        payload = result.read()
        conn.close()
        return result.status, json.loads(payload)

    def test_state_privacy_and_events(self):
        status, resident = self.request('/api/state?role=resident')
        self.assertEqual(status, 200)
        self.assertIn('reason', resident['appointment'])
        _, family = self.request('/api/state?role=family')
        self.assertNotIn('reason', family['appointment'])
        _, moved = self.request('/api/event', {'role': 'resident', 'action': 'reschedule', 'revision': resident['revision']})
        self.assertEqual(moved['transport']['status'], 'needs_confirmation')
        status, _ = self.request('/api/event', {'role': 'family', 'action': 'confirm_ride', 'revision': resident['revision']})
        self.assertEqual(status, 400)
        status, accepted = self.request('/api/event', {'role': 'family', 'action': 'confirm_ride', 'revision': moved['revision']})
        self.assertEqual(status, 200)
        self.assertEqual(accepted['transport']['status'], 'confirmed')
        self.assertNotIn('reason', accepted['appointment'])

    def test_malformed_requests(self):
        for raw in ('{', '[]', '{"role":"family","role":"resident"}', '{"role":NaN}'):
            self.assertEqual(self.request('/api/chat', raw=raw)[0], 400)
        for data in ({'role': []}, {'role': 'other'}, {'role': 'family', 'action': 'reset', 'revision': True}):
            self.assertEqual(self.request('/api/event', data)[0], 400)
        good = {'role': 'family', 'message': 'Hi', 'history': []}
        for changes in ({'message': ''}, {'message': 'a' * 2001}, {'history': [{}]},
                        {'history': [{'role': 'system', 'content': 'x'}]}, {'history': [None] * 13}):
            self.assertEqual(self.request('/api/chat', good | changes)[0], 400)
        self.assertEqual(self.request('/api/chat', raw='x' * (MAX_BODY + 1))[0], 413)
        self.assertEqual(self.request('/api/chat', good, {'Content-Type': 'text/plain'})[0], 415)
        self.assertEqual(self.request('/api/state?role=family&role=resident')[0], 400)
        self.assertEqual(self.request('/api/state?role=family', headers={'Host': 'evil.test'})[0], 403)
        self.assertEqual(self.request('/api/chat', good, {'Origin': 'https://evil.test', 'Content-Type': 'application/json'})[0], 403)

    def test_event_payload_boundary_and_forwarding(self):
        data = {'role': 'resident', 'action': 'week_example', 'revision': 7,
                'payload': {'choice': 'fictional', 'preferences': {'language': 'English'}}}
        with patch.object(self.server.household, 'event', return_value={'revision': 8}) as event:
            self.assertEqual(self.request('/api/event', data), (200, {'revision': 8}))
            event.assert_called_once_with('week_example', 'resident', 7, payload=data['payload'])
            event.reset_mock()
            for payload in (None, [], 'text', 1, True):
                self.assertEqual(self.request('/api/event', data | {'payload': payload})[0], 400)
            self.assertEqual(self.request('/api/event', data | {'extra': 1})[0], 400)
            self.assertEqual(self.request('/api/event', data | {'payload': {'text': 'x' * MAX_BODY}})[0], 413)
            event.assert_not_called()

    def test_comparison_read_only_boundary_and_size(self):
        before = self.server.household.view('resident')
        fixture = {'cases': [{'manual': {'decisions': 4}, 'assisted': {'decisions': 3}}]}
        with patch.object(self.server.household, 'comparison', return_value=fixture, create=True) as replay:
            self.assertEqual(self.request('/api/comparison'), (200, fixture))
            replay.assert_called_once_with()
            replay.reset_mock()
            for path, data, headers, status in (
                    ('/api/comparison', {}, None, 404),
                    ('/api/comparison?role=resident', None, None, 404),
                    ('/api/comparison', None, {'Host': 'evil.test'}, 403),
                    ('/api/comparison', None, {'Origin': 'https://evil.test'}, 403)):
                self.assertEqual(self.request(path, data, headers)[0], status)
            replay.assert_not_called()
        self.assertEqual(self.server.household.view('resident'), before)
        with patch.object(self.server.household, 'comparison', return_value={'large': 'x' * MAX_JSON_RESPONSE}, create=True):
            status, result = self.request('/api/comparison')
            self.assertEqual(status, 500)
            self.assertEqual(set(result), {'error'})

    def test_real_comparison_preserves_live_household(self):
        # A non-default live state must survive all six isolated replay runs.
        current = self.request('/api/state?role=resident')[1]
        status, _ = self.request('/api/event', {'role': 'resident', 'action': 'week_select_profile',
            'revision': current['revision'], 'payload': {'id': 'remote'}})
        self.assertEqual(status, 200)
        before = {role: self.request('/api/state?role=' + role)[1] for role in ('resident', 'family')}
        status, result = self.request('/api/comparison')
        self.assertEqual(status, 200)
        self.assertEqual(len(result['households']), 3)
        self.assertFalse(result['method']['time_measured'])
        self.assertLess(len(json.dumps(result).encode()), MAX_JSON_RESPONSE)
        for row in result['households']:
            self.assertIn('manual', row)
            self.assertIn('assisted', row)
        after = {role: self.request('/api/state?role=' + role)[1] for role in ('resident', 'family')}
        self.assertEqual(after, before)

    def test_week_revision_role_privacy_and_chat_context(self):
        _, state = self.request('/api/state?role=resident')
        def event(action, payload, role='resident', revision=None):
            current = self.request('/api/state?role=' + role)[1]
            return self.request('/api/event', {'role': role, 'action': action,
                'revision': current['revision'] if revision is None else revision, 'payload': payload})
        status, state = event('week_select_profile', {'id': 'nearby'})
        self.assertEqual(status, 200)
        self.assertEqual(state['week']['profile']['id'], 'nearby')
        revision = state['revision']
        status, state = event('week_inject', {'scenario': 'papers_moved'})
        self.assertEqual(status, 200)
        self.assertEqual(state['documents']['status'], 'last_known')
        for action, payload, role, version in (
                ('week_mode', {'mode': 'manual'}, 'resident', revision),
                ('week_permissions', {'paperwork': True}, 'family', state['revision']),
                ('week_permissions', {'paperwork': 'yes'}, 'resident', state['revision'])):
            self.assertEqual(event(action, payload, role, version)[0], 400)
            self.assertEqual(self.request('/api/state?role=resident')[1], state)
        private_reason = state['appointment']['reason']
        family = self.request('/api/state?role=family')[1]
        self.assertNotIn(private_reason, json.dumps(family, ensure_ascii=False))
        self.assertNotIn('reason', family['week']['commitments'][0])
        self.assertNotIn('Bedroom drawer', json.dumps(family))
        self.assertFalse(family['week']['controls']['decisions'])
        chat = {'role': 'family', 'message': 'Explain the shared week.', 'history': []}
        with patch.object(bridge, 'reply', return_value='The location is last known.') as model:
            self.assertEqual(self.request('/api/chat', chat)[0], 200)
            snapshot = model.call_args.args[0]
            self.assertEqual(snapshot, family)
            from real_world import NEEDS
            catalog = snapshot['public_discovery']
            self.assertEqual({group['need'] for group in catalog}, set(NEEDS))
            self.assertTrue(all(group['budget_cents'] is None for group in catalog))
            self.assertTrue(all(option['coordination_status'] == 'not_requested'
                                for group in catalog for option in group['options']))
            self.assertNotIn(private_reason, json.dumps(snapshot, ensure_ascii=False))
        def switch_profile(*_):
            with self.server.state_lock:
                current = self.server.household.view('resident')
                self.server.household.event('week_select_profile', 'resident', current['revision'], {'id': 'remote'})
            return 'Old household answer'
        with patch.object(bridge, 'reply', side_effect=switch_profile):
            self.assertEqual(self.request('/api/chat', chat)[0], 409)
        changed = self.request('/api/state?role=resident')[1]
        self.assertGreater(changed['context_revision'], state['context_revision'])
        self.assertEqual(changed['week']['profile']['id'], 'remote')
        self.assertEqual(changed['documents']['status'], 'confirmed')

    def test_real_options_query_trust_and_no_state_change(self):
        before = {role: self.request('/api/state?role=' + role)[1] for role in ('resident', 'family')}
        status, result = self.request('/api/real-options?need=home_storage&budget_cents=0')
        self.assertEqual(status, 200)
        self.assertEqual(result['need'], 'home_storage')
        self.assertEqual(result['budget_cents'], 0)
        self.assertIsInstance(result['options'], list)
        self.assertTrue(all(option['coordination_status'] == 'not_requested' for option in result['options']))
        for query in ('need=unknown', 'need=', 'need=home_storage&need=home_storage',
                      'other=x', 'budget_cents=-1', 'budget_cents=1.5', 'budget_cents=true',
                      'budget_cents=', 'budget_cents=%EF%BC%91', 'budget_cents=9007199254740992', 'budget_cents=1e3',
                      'budget_cents=1&budget_cents=2', 'need', 'need=home_storage&x=1&y=2'):
            self.assertEqual(self.request('/api/real-options?' + query)[0], 400)
        self.assertEqual(self.request('/api/real-options', {})[0], 404)
        self.assertEqual(self.request('/api/real-options', headers={'Host': 'evil.test'})[0], 403)
        self.assertEqual(self.request('/api/real-options', headers={'Origin': 'https://evil.test'})[0], 403)
        after = {role: self.request('/api/state?role=' + role)[1] for role in ('resident', 'family')}
        self.assertEqual(after, before)

    def test_static_allowlist(self):
        for path in ('/server.py', '/.codex/config.toml', '/assets/../server.py',
                     '/assets/%2e%2e/server.py', '/assets/home.png/../../server.py'):
            self.assertEqual(self.request(path)[0], 404)

    def test_chat_snapshot_failure_and_stale_reply(self):
        data = {'role': 'family', 'message': 'Hello', 'history': [{'role': 'user', 'content': 'family only'}]}
        with patch.object(bridge, 'reply', return_value='Reply') as mock:
            status, result = self.request('/api/chat', data)
            self.assertEqual(status, 200)
            self.assertEqual(result['engine'], 'gpt-6-astra')
            view, _, history = mock.call_args.args
            self.assertNotIn('reason', view['appointment'])
            self.assertNotIn('_actual_document_location', view)
            self.assertEqual(history, data['history'])
        def stale(*args):
            with self.server.state_lock:
                self.server.household.event('reset', 'resident')
            return 'OLD'
        with patch.object(bridge, 'reply', side_effect=stale):
            status, result = self.request('/api/chat', data)
            self.assertEqual(status, 409)
            self.assertNotIn('reply', result)
        for error, code in ((bridge.Busy('Busy'), 429), (bridge.BridgeError('Unavailable'), 503)):
            with patch.object(bridge, 'reply', side_effect=error):
                status, result = self.request('/api/chat', data)
                self.assertEqual(status, code)
                self.assertNotIn('reply', result)


class BridgeTests(unittest.TestCase):
    def test_command_and_private_prompt(self):
        def run(args, prompt, directory):
            self.assertEqual(args[:2], [bridge.CODEX, 'exec'])
            for flag in ('--ignore-user-config', '--ephemeral', '--skip-git-repo-check', '--output-schema'):
                self.assertIn(flag, args)
            self.assertEqual(args[args.index('--model') + 1], 'gpt-6-astra')
            self.assertEqual(args[args.index('--sandbox') + 1], 'read-only')
            self.assertIn('shell_tool', args)
            self.assertIn('unified_exec', args)
            payload = json.loads(prompt)
            self.assertNotIn('reason', payload['selected_role_state']['appointment'])
            self.assertTrue((directory / 'schema.json').is_file())
            return b'{"reply":"Current plan."}'
        with patch.object(bridge, '_run', side_effect=run):
            self.assertEqual(bridge.reply(Household().view('family'), 'Hi', []), 'Current plan.')
        with patch.object(bridge, '_run', return_value=b'not json'):
            with self.assertRaises(bridge.BridgeError):
                bridge.reply({}, 'Hi', [])
        bridge._GATE.acquire()
        try:
            with self.assertRaises(bridge.Busy):
                bridge.reply({}, 'Hi', [])
        finally:
            bridge._GATE.release()

    def test_process_output_and_timeout_limits(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(bridge, 'MAX_OUTPUT', 10):
                with self.assertRaises(bridge.BridgeError):
                    bridge._run([sys.executable, '-c', 'print("x" * 100)'], '', Path(directory))
            with patch.object(bridge, 'TIMEOUT', 0.1):
                with self.assertRaises(bridge.BridgeError):
                    bridge._run([sys.executable, '-c', 'import time; time.sleep(5)'], '', Path(directory))


if __name__ == '__main__':
    unittest.main()
