"""One opt-in watcher for changed fictional hospital notices; existing tasks own execution."""
from copy import deepcopy
import threading


class VisitWatcher:
    def __init__(self, server):
        self.server = server
        self.generation = 0
        self.status = 'watching' if self.enabled else 'disabled'
        self.detail = 'Checking the saved visit-monitoring choice.'
        self.request_id = ''
        self.gate = threading.Lock()

    @property
    def enabled(self):
        return self.server.household.coordination.state['watch_visit_changes']

    def view(self):
        with self.server.state_lock:
            if self.server.household.mission_persistence['status'] == 'save_error':
                return {'enabled': self.enabled, 'status': 'blocked', 'request_id': self.request_id,
                        'detail': 'The household could not be saved. Automatic coordination is stopped. Save again before restarting; the previous saved choice may otherwise return.'}
            if not self.enabled:
                return {'enabled': False, 'status': 'disabled', 'request_id': '',
                        'detail': 'Visit monitoring is off. Existing responsibilities are unchanged.'}
            if self.enabled and self.request_id:
                request = next((r for r in self.server.household.coordination.state['requests']
                                if r['id'] == self.request_id), None)
                if request:
                    self.status = {'interpreting': 'coordinating', 'running': 'coordinating',
                        'ready': 'coordinating', 'waiting_physical': 'waiting_helper',
                        'needs_clarification': 'blocked', 'paused': 'blocked',
                        'cancelled': 'blocked', 'superseded': 'blocked'}.get(request['status'], request['status'])
                    self.detail = request['question'] or request['error'] or request['summary']
            return {'enabled': self.enabled, 'status': self.status,
                    'detail': self.detail, 'request_id': self.request_id}

    def set_enabled(self, enabled):
        if type(enabled) is not bool:
            raise ValueError('Choose whether to watch visit changes.')
        with self.server.state_lock:
            if enabled != self.enabled:
                self.generation += 1
                host = self.server.household
                host.event('coordination_watch_visits', 'resident', host.revision, {'enabled': enabled})
            self.status = 'watching' if enabled else 'disabled'
            self.detail = ('Watching the fictional hospital for changes to an existing visit plan.' if enabled else
                           'Visit monitoring is off. Existing responsibilities are unchanged.')
            return self.view()

    def _event(self):
        host = self.server.household
        hospital = host.hospital
        self.request_id = ''
        if not (hospital.state['permissions']['retrieve_records']
                and hospital.state['permissions']['visit_requests']
                and host.coordination.state['permissions']['notify']):
            self.status, self.detail = 'waiting_permission', 'Allow hospital retrieval, visit requests and household updates to monitor this visit.'
            return None
        existing = [r for r in hospital.state['requests'].values()
                    if r['intent'] == 'hospital_coordination' and r['status'] != 'cancelled']
        if not existing or hospital.state['retrieved_visit'] is None:
            self.status, self.detail = 'watching', 'Arrange a fictional visit once; then changes to that plan can be handled automatically.'
            return None
        # Authorized connector read. Project only logistics; never send medical purpose to the model.
        source = hospital.state['provider_visit']
        identity = 'proactive-visit-v' + str(source['source_version'])
        old = next((r for r in host.coordination.state['requests'] if r['id'] == identity), None)
        if old:
            self.request_id = identity
            return None  # Persisted request identity prevents duplicate inference, including after restart.
        if source['source_version'] == hospital.state['reconciled_version']:
            self.status, self.detail = 'watching', 'No new hospital notice. Existing responsibilities remain tracked.'
            return None
        if source['appointment']['date'] < host.coordination.state['date']:
            self.status, self.detail = 'blocked', 'The supplied visit is in the past; no new family requests were made.'
            return None
        availability = {actor: host.coordination.availability_for(actor, source['appointment']['date'])
                        for actor in ('alex', 'morgan')}
        if all(value is False for value in availability.values()):
            self.status, self.detail = 'blocked', 'Both helpers reported being unavailable for the new date. The visit needs another arrangement.'
            return None
        return {'request_id': identity, 'revision': host.revision, 'generation': self.generation,
                'notice': {key: deepcopy(source[key]) for key in ('id', 'source_id', 'source_version', 'source_timestamp', 'provenance')}
                    | {'appointment': {key: source['appointment'][key] for key in ('date', 'time', 'pickup', 'location')}},
                'availability_on_visit_date': availability,
                'previous_helpers': hospital.context()['current_visit_helpers']}

    def validate(self, proposal, event):
        """Recheck authority and helper constraints after model latency, before effects."""
        host = self.server.household
        if not self.enabled or self.generation != event['generation']:
            raise ValueError('Visit monitoring changed while planning; no automatic actions were started.')
        permissions = host.hospital.state['permissions']
        source = host.hospital.state['provider_visit']
        if any(source[key] != event['notice'][key] for key in ('id', 'source_id', 'source_version')):
            raise ValueError('The hospital notice changed while planning; no automatic actions were started.')
        if not (permissions['retrieve_records'] and permissions['visit_requests']
                and host.coordination.state['permissions']['notify']):
            raise ValueError('Permission changed while planning; no automatic actions were started.')
        if (not isinstance(proposal, dict) or proposal.get('intent') != 'hospital_coordination'
                or proposal.get('item') != 'visit-001'):
            raise ValueError('The monitor may only coordinate the existing hospital visit.')
        assignments = proposal.get('visit_helpers') or {}
        if not isinstance(assignments, dict):
            raise ValueError('Use named visit responsibilities.')
        for kind in ('driver', 'companion', 'return'):
            actor = assignments.get(kind) or proposal.get('helper')
            if actor not in ('alex', 'morgan') or host.coordination.availability_for(
                    actor, event['notice']['appointment']['date']) is False:
                raise ValueError('A proposed helper is unavailable for the changed visit date.')
            if (event['previous_helpers'] and actor != event['previous_helpers'][kind]
                    and not permissions['backup_requests']):
                raise ValueError('Permission to ask an alternative helper is required.')

    def step(self):
        if not self.gate.acquire(blocking=False):
            return self.view()
        try:
            with self.server.state_lock:
                if not self.enabled or self.server.household.mission_persistence['status'] == 'save_error':
                    return self.view()
                event = self._event()
                if event is None:
                    return self.view()
                self.request_id = event['request_id']
                self.status, self.detail = 'coordinating', 'A changed hospital notice was detected. Checking the family plan.'
            before = self.server.message_snapshot()
            self.server.coordinate({'role': 'resident', 'revision': event['revision'],
                'request_id': event['request_id'], 'message':
                'Automatic hospital notice check: coordinate visit-001 using the newly observed notice and availability on its date. '
                'Preserve each previous helper where possible; replace a known unavailable helper with an eligible named backup. '
                'Use visit_helpers for separate driver, companion and return requests. Notify Alex and Morgan of the changed plan. '
                'No person has accepted a new responsibility yet.'}, proactive=event)
            self.server.send_changed_updates(before)
            return self.view()
        finally:
            self.gate.release()

    def run(self, stop):
        # ponytail: one household, one changed-notice check every three seconds; no idle model calls.
        while not stop.wait(3):
            try:
                self.step()
            except Exception:
                with self.server.state_lock:
                    self.status, self.detail = 'failed', 'The visit check could not finish. Review the task before retrying.'
