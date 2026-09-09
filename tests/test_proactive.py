"""Behavior checks for automatic fictional-visit coordination. No Messages or model network."""
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from careanchor import astra_bridge
from careanchor.coordination import PROPOSAL_FIELDS, Coordination
from careanchor.hospital import PERMISSIONS
from careanchor.server import Server
from .test_hospital import request as seed_request


def proposal():
    return dict.fromkeys(PROPOSAL_FIELDS, '') | {
        'intent': 'hospital_coordination', 'item': 'visit-001', 'quantity': 1,
        'recipients': ['alex', 'morgan'], 'summary': 'Coordinate the changed fictional visit.',
        'visit_helpers': dict.fromkeys(('driver', 'companion', 'return'), 'morgan')}


def setup_changed_visit(server, *, publish=True):
    host = server.household
    def act(action, payload, actor='resident'):
        return host.event(action, 'resident' if actor == 'resident' else 'family', host.revision,
                          payload, **({'actor_id': actor} if actor != 'resident' else {}))
    act('hospital_permissions', dict.fromkeys(PERMISSIONS, True))
    act('coordination_permissions', host.coordination.state['permissions'] | {'notify': True})
    seed_request(host, 'existing-visit', visit_helpers={'driver': 'alex', 'companion': 'morgan', 'return': 'alex'})
    for duty in list(host.hospital.state['commitments']):
        act('coordination_reply', {'message_id': duty['message_id'], 'actor_id': duty['actor_id'], 'status': 'accepted'}, duty['actor_id'])
    for actor, available in (('alex', False), ('morgan', True)):
        act('coordination_set_availability', {'actor_id': actor, 'start_date': '2026-09-18',
                                            'end_date': '2026-09-18', 'available': available}, actor)
    if publish:
        act('hospital_publish_visit', {'fixture': 'time_location_change'})
    return act


class ProactiveTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / 'household.json'
        self.server = Server(0, save_path=self.path)
        self.act = setup_changed_visit(self.server)

    def tearDown(self):
        self.server.server_close()
        self.directory.cleanup()

    def test_saved_watching_continues_after_restart_and_a_late_reply(self):
        self.server.proactive.set_enabled(True)
        with patch.object(astra_bridge, 'interpret_request', return_value=proposal()) as model:
            with Server(0, save_path=self.path) as restarted:
                self.assertTrue(restarted.proactive.view()['enabled'])
                self.assertEqual(restarted.proactive.step()['status'], 'waiting_helper')
                host = restarted.household
                duties = [d for d in host.hospital.state['commitments'] if d['status'] == 'requested']
                host.event('coordination_schedule_reminder', 'resident', host.revision,
                           {'message_id': duties[0]['message_id'], 'hours': 3})
                request_count = len(host.coordination.state['requests'])
            with Server(0, save_path=self.path) as continued:
                host = continued.household
                self.assertEqual(continued.proactive.step()['status'], 'waiting_helper')
                host.event('coordination_advance_clock', 'resident', host.revision, {'minutes': 180})
                self.assertEqual(host.coordination.state['reminders'][0]['status'], 'issued')
                reply = {'role': 'family', 'actor_id': 'morgan', 'revision': host.revision,
                         'reply_id': 'late-morgan', 'message': 'Yes, I can cover all three arrangements.'}
                decisions = {'decisions': [{'message_id': d['message_id'], 'status': 'accepted'} for d in duties],
                             'question': ''}
                with patch.object(astra_bridge, 'interpret_helper_reply', return_value=decisions) as reply_model:
                    self.assertEqual(continued.recipient_reply(reply)[0], 200)
                    self.assertEqual(continued.proactive.view()['status'], 'completed')
                    before = host.coordination.dump()
                    self.assertEqual(continued.recipient_reply(reply)[0], 200)
                    self.assertEqual(host.coordination.dump(), before)
                    reply_model.assert_called_once()
                self.assertEqual(len(host.coordination.state['requests']), request_count)
                self.assertIn('Attendance and physical paperwork preparation remain unreported',
                              continued.proactive.view()['detail'])
            with Server(0, save_path=self.path) as completed:
                self.assertTrue(completed.proactive.view()['enabled'])
                self.assertEqual(completed.proactive.step()['status'], 'completed')
                self.assertEqual(completed.household.coordination.state['messages'], before['messages'])
            model.assert_called_once()

    def test_saved_monitoring_choice_is_resident_controlled_and_defaults_off_for_old_saves(self):
        host = self.server.household
        with self.assertRaises(ValueError):
            host.event('coordination_watch_visits', 'family', host.revision, {'enabled': True}, actor_id='alex')
        self.server.proactive.set_enabled(True)
        self.server.proactive.set_enabled(False)
        with Server(0, save_path=self.path) as restarted:
            self.assertFalse(restarted.proactive.view()['enabled'])
        old = host.coordination.dump()
        old.pop('watch_visit_changes', None)
        self.assertFalse(Coordination.restore(host, old).state['watch_visit_changes'])
        with self.assertRaises(ValueError):
            Coordination.restore(host, old | {'watch_visit_changes': 'true'})

    def test_unsaved_monitoring_choice_cannot_start_automatic_work(self):
        with patch('careanchor.persistence.save_household', side_effect=OSError('Local save unavailable')):
            result = self.server.proactive.set_enabled(True)
            self.assertEqual(result['status'], 'blocked')
            with patch.object(astra_bridge, 'interpret_request') as model:
                self.server.proactive.step()
                model.assert_not_called()
        with Server(0, save_path=self.path) as restarted:
            self.assertFalse(restarted.proactive.view()['enabled'])

    def test_changed_notice_plans_once_then_waits_for_own_acceptance(self):
        watcher, host = self.server.proactive, self.server.household
        with patch.object(astra_bridge, 'interpret_request', return_value=proposal()) as model:
            self.assertEqual(watcher.step()['status'], 'disabled')
            self.assertFalse(model.called)
            watcher.set_enabled(True)
            count = host.coordination.state['human_interactions']['resident']
            result = watcher.step()
            self.assertEqual(result['status'], 'waiting_helper')
            context = model.call_args.args[0]['proactive_notice']
            self.assertEqual(context['availability_on_visit_date'], {'alex': False, 'morgan': True})
            self.assertNotIn('purpose', context['notice']['appointment'])
            self.assertEqual(host.appointment['date'], '2026-09-18')
            duties = [d for d in host.hospital.state['commitments'] if d['status'] == 'requested']
            self.assertEqual(len(duties), 3)
            self.assertTrue(all(d['actor_id'] == 'morgan' for d in duties))
            self.assertEqual(host.coordination.state['human_interactions']['resident'], count)
            self.assertTrue(any(e['event'] == 'proactive_request' and e['actor'] == 'coordinator'
                                for e in host.coordination.state['history']))
            watcher.step()
            self.assertEqual(model.call_count, 1)
            for duty in duties:
                self.act('coordination_reply', {'message_id': duty['message_id'], 'actor_id': 'morgan',
                                               'status': 'accepted'}, 'morgan')
            self.assertEqual(watcher.view()['status'], 'completed')
            self.assertIn('Attendance and physical paperwork preparation remain unreported', watcher.view()['detail'])
            with Server(0, save_path=self.path) as restarted:
                restarted.proactive.set_enabled(True)
                self.assertEqual(restarted.proactive.step()['status'], 'completed')
            self.assertEqual(model.call_count, 1)

    def test_permission_missing_and_no_available_helper_do_not_call_model(self):
        watcher, host = self.server.proactive, self.server.household
        watcher.set_enabled(True)
        with patch.object(astra_bridge, 'interpret_request') as model:
            self.act('coordination_permissions', host.coordination.state['permissions'] | {'notify': False})
            self.assertEqual(watcher.step()['status'], 'waiting_permission')
            self.act('coordination_permissions', host.coordination.state['permissions'] | {'notify': True})
            self.act('coordination_set_availability', {'actor_id': 'morgan', 'start_date': '2026-09-18',
                     'end_date': '2026-09-18', 'available': False}, 'morgan')
            self.assertEqual(watcher.step()['status'], 'blocked')
            self.assertFalse(model.called)

    def test_wrong_intent_or_unavailable_helper_cannot_execute(self):
        watcher, host = self.server.proactive, self.server.household
        watcher.set_enabled(True)
        bad = proposal() | {'intent': 'order_supply'}
        with patch.object(astra_bridge, 'interpret_request', return_value=bad) as model:
            self.assertEqual(watcher.step()['status'], 'failed')
            watcher.step()
            self.assertEqual(model.call_count, 1)
        self.assertEqual(host.coordination.state['orders'], [])
        self.assertFalse(any(d['request_id'].startswith('proactive-') for d in host.hospital.state['commitments']))

    def test_disabling_during_inference_prevents_effects(self):
        watcher, host = self.server.proactive, self.server.household
        watcher.set_enabled(True)
        def decide(*_):
            watcher.set_enabled(False)
            return proposal()
        with patch.object(astra_bridge, 'interpret_request', side_effect=decide):
            self.assertEqual(watcher.step()['status'], 'disabled')
        self.assertFalse(any(d['request_id'].startswith('proactive-') for d in host.hospital.state['commitments']))

    def test_failed_claim_save_prevents_model_and_domain_effects(self):
        watcher, host = self.server.proactive, self.server.household
        watcher.set_enabled(True)
        before = host.hospital.dump()
        with patch('careanchor.persistence.save_household', side_effect=OSError('Supplied local save failure')):
            with patch.object(astra_bridge, 'interpret_request') as model:
                self.assertEqual(watcher.step()['status'], 'blocked')
                self.assertEqual(host.mission_persistence['status'], 'save_error')
                watcher.step()
                model.assert_not_called()
        self.assertEqual(host.hospital.dump(), before)
        self.assertEqual(host.coordination.state['orders'], [])
        self.assertNotIn('proactive-visit-v2', self.path.read_text())

    def test_known_unavailable_proposed_helper_is_rejected(self):
        watcher, host = self.server.proactive, self.server.household
        watcher.set_enabled(True)
        before = host.hospital.dump()
        bad = proposal() | {'visit_helpers': dict.fromkeys(('driver', 'companion', 'return'), 'alex')}
        with patch.object(astra_bridge, 'interpret_request', return_value=bad) as model:
            result = watcher.step()
            self.assertEqual(result['status'], 'failed')
            self.assertIn('unavailable', result['detail'])
            watcher.step()
            self.assertEqual(model.call_count, 1)
        self.assertEqual(host.hospital.dump(), before)

    def test_alternative_helper_requires_backup_permission(self):
        watcher, host = self.server.proactive, self.server.household
        self.act('hospital_permissions', {'backup_requests': False})
        watcher.set_enabled(True)
        before = host.hospital.dump()
        with patch.object(astra_bridge, 'interpret_request', return_value=proposal()):
            result = watcher.step()
            self.assertEqual(result['status'], 'failed')
            self.assertIn('alternative helper', result['detail'])
        self.assertEqual(host.hospital.dump(), before)

    def test_new_notice_during_inference_rejects_stale_plan(self):
        watcher, host = self.server.proactive, self.server.household
        watcher.set_enabled(True)
        def decide(*_):
            self.act('hospital_publish_visit', {'fixture': 'time_location_change'})
            return proposal()
        with patch.object(astra_bridge, 'interpret_request', side_effect=decide):
            self.assertEqual(watcher.step()['status'], 'failed')
        self.assertFalse(any(d['request_id'].startswith('proactive-') for d in host.hospital.state['commitments']))

    def test_background_watcher_starts_without_resident_request(self):
        watcher, host = self.server.proactive, self.server.household
        stop, called = threading.Event(), threading.Event()
        def decide(*_):
            called.set()
            return proposal()
        watcher.set_enabled(True)
        with patch.object(astra_bridge, 'interpret_request', side_effect=decide):
            worker = threading.Thread(target=watcher.run, args=(stop,))
            worker.start()
            try:
                self.assertTrue(called.wait(8), 'The background watcher never initiated coordination.')
            finally:
                stop.set()
                worker.join(5)
            self.assertFalse(worker.is_alive())
        self.assertEqual(watcher.view()['status'], 'waiting_helper')


if __name__ == '__main__':
    unittest.main()
