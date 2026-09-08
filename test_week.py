"""Run: python3 test_week.py — integrated permission, evidence and privacy checks."""
import json
from simulation import Household, InvalidAction


def check():
    home = Household()
    def act(action, payload=None, role='resident'):
        return home.event(action, role, home.revision, payload)
    def rejects(action, payload=None, role='resident', revision=None):
        before = home.view('resident')
        try:
            home.event(action, role, home.revision if revision is None else revision, payload)
        except InvalidAction:
            assert home.view('resident') == before, 'Rejected action changed state'
        else:
            raise AssertionError('Invalid action accepted: ' + action)
    def control(action, role='resident'):
        groups = home.view(role)['week']['controls']
        return next((item for group in groups.values() for item in group if item['action'] == action), None)
    def available(action, role='resident'):
        item = control(action, role)
        assert item, ('Missing action', action, home.view(role)['week']['controls'])
        return act(action, item.get('payload'), role)

    assert len(home.view('resident')['week']['profiles']) == 3
    initial_tasks = {task['id']: task for task in home.view('resident')['week']['tasks']}
    assert initial_tasks['paperwork']['status'] != 'prepared', 'Known location is not staged papers'
    assert initial_tasks['transport']['status'] != 'confirmed', 'Pickup alone is not round-trip confirmation'
    assert 'Private follow-up' not in json.dumps(home.view('family'))
    rejects('week_permissions', {'supplies': True}, 'family')
    rejects('week_permissions', {'supplies': True, 'supply_cap': -1})
    rejects('week_configure', {'setting': 'urban', 'age_band': 'child'})
    rejects('week_inject', {'scenario': 'papers_moved'}, revision=home.revision + 1)
    rejects('week_fake_real_purchase')

    if home.view('resident')['week']['mode'] != 'assisted':
        act('week_mode', {'mode': 'assisted'})
    act('week_permissions', {'calendar': True, 'backup_transport': True,
        'paperwork': True, 'supplies': True, 'home_help': True, 'supply_cap': 30})
    act('week_inject', {'scenario': 'appointment_conflict'})
    act('week_choose_slot', {'slot': 'keep_activity'})
    available('week_run')
    assert home.transport['status'] != 'confirmed', 'Clinic acknowledgment cannot confirm a driver'
    assert 'reason' not in home.view('family')['appointment']
    assert 'Private follow-up' not in json.dumps(home.view('family'))

    act('week_inject', {'scenario': 'driver_decline'})
    if control('week_run'):
        available('week_run')
    old_revision = home.revision
    available('week_accept_backup', 'family')
    assert home.transport['status'] == 'confirmed'
    rejects('week_accept_backup', role='family', revision=old_revision)
    rejects('week_accept_backup', role='family')
    ride_before = dict(home.transport)

    act('week_inject', {'scenario': 'papers_moved'})
    assert home.documents['status'] == 'last_known'
    assert home.documents['location'] != home._actual_document_location
    available('week_run')
    available('week_stage_papers', 'family')
    assert home.documents['status'] == 'confirmed', 'Authorized helper report must be reused'
    rejects('week_stage_papers', role='family')

    act('join_activity')
    act('game_invitation')
    practice_before = home.view('resident')['outing']
    act('week_inject', {'scenario': 'event_cancelled'})
    available('week_run')
    act('week_choose_activity', {'choice': 'free'})
    assert home.transport == ride_before, 'Community cancellation changed unrelated clinic travel'
    assert home.view('resident')['outing'] == practice_before, 'Weekly cancellation reset independent practice'

    act('week_inject', {'scenario': 'supply_unavailable'})
    available('week_run')
    assert control('week_deliver_supplies', 'family'), 'Ordering must still require delivery evidence'
    assert not control('week_place_supplies', 'family'), 'Ordering is not placement'
    available('week_deliver_supplies', 'family')
    available('week_place_supplies', 'family')
    rejects('week_place_supplies', role='family')

    act('week_inject', {'scenario': 'home_comfort'})
    act('week_choose_comfort', {'choice': 'equipment'})
    assert not control('week_comfort_feedback'), 'Proposed equipment has not helped yet'
    available('week_run')
    available('week_report_home_help', 'family')
    act('week_comfort_feedback', {'helped': True})
    assert 'Private follow-up' not in json.dumps(home.view('family'))

    before_context = home.context_revision
    profiles = home.view('resident')['week']['profiles']
    act('week_select_profile', {'id': profiles[-1]['id']})
    assert home.context_revision > before_context
    assert home.documents['status'] == 'confirmed'
    assert not control('week_place_supplies', 'family')
    home = Household()
    act('week_permissions', {'supplies': True, 'supply_cap': 25, 'backup_transport': True})
    act('week_inject', {'scenario': 'supply_unavailable'})
    act('week_permissions', {'supplies': False})
    assert not control('week_run'), 'Revoked permission still allows routine ordering'
    rejects('week_order_supplies')
    act('week_inject', {'scenario': 'driver_decline'})
    available('week_run')
    act('week_helper_availability', {'available': False}, 'family')
    rejects('week_accept_backup', role='family')
    available('week_decline_backup', 'family')
    assert home.transport['status'] == 'declined'
    assert not control('week_request_backup'), 'Helper refusal triggered duplicate requests'
    print('PASS: week privacy, atomic rejection, current-version acceptance, shared dependencies, '
          'helper evidence, delivery/placement separation, equipment lifecycle and profile isolation.')


if __name__ == '__main__':
    check()
