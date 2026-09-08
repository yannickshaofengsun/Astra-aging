"""Runnable acceptance scenarios for the symbolic outing mission."""

from copy import deepcopy
import json
from mission import Mission, PERMISSIONS, BACKUP
from simulation import Household


def fixture():
    host = Household()
    mission = Mission(host)
    return host, mission


def act(mission, action, role="resident", **payload):
    return mission.apply(action, role, payload)


def reject(mission, action, role="resident", **payload):
    before = mission.dump()
    try:
        act(mission, action, role, **payload)
    except ValueError:
        assert before == mission.dump(), action + " mutated state on rejection"
    else:
        raise AssertionError(action + " unexpectedly accepted")


def start(mission):
    act(mission, "mission_start")
    act(mission, "mission_opt_in")
    act(mission, "mission_permissions", **dict.fromkeys(PERMISSIONS, True))


def requests(mission, accept=True):
    act(mission, "mission_request_primary", "coordinator")
    reject(mission, "mission_backup_accept", "family")
    act(mission, "mission_primary_decline", "family")
    reject(mission, "mission_request_primary", "coordinator")
    act(mission, "mission_request_backup", "coordinator")
    act(mission, "mission_backup_accept" if accept else "mission_backup_decline", "family")
    if accept:
        act(mission, "mission_confirm_travel", "family")
    act(mission, "mission_request_search", "coordinator")


def locate(mission):
    for item in ("bag", "documents"):
        reject(mission, "mission_observe_" + item)
        text = act(mission, "mission_check_" + item)
        assert "not found" in text
        assert mission.view("resident")["known"][item]["location"] is None
        act(mission, "mission_observe_" + item)
    assert not mission.view("resident")["known"]["documents_staged"]


def load(mission):
    act(mission, "mission_request_loading", "coordinator")
    reject(mission, "mission_load_robot", "coordinator")
    reject(mission, "mission_load_robot", "family")
    act(mission, "mission_stage_documents", "family")
    reject(mission, "mission_stage_documents", "family")
    assert mission.state["robot"]["status"] == "empty"
    act(mission, "mission_load_robot", "family")
    reject(mission, "mission_load_robot", "family")


def block(mission):
    act(mission, "mission_dispatch_main", "coordinator")
    reject(mission, "mission_dispatch_main", "coordinator")
    act(mission, "mission_move_robot", "coordinator")
    assert mission.state["robot"]["position"] == "Hall"
    act(mission, "mission_move_robot", "coordinator")
    assert mission.state["robot"]["status"] == "blocked"
    assert mission.state["world"]["bag_zone"] == "Robot"
    assert mission.state["status"] == "preparing"
    reject(mission, "mission_move_robot", "coordinator")
    reject(mission, "mission_dispatch_main", "coordinator")
    reject(mission, "mission_dispatch_alternate", "coordinator")


def recover(mission):
    act(mission, "mission_observe_alternate", usable=True)
    act(mission, "mission_dispatch_alternate", "coordinator")
    act(mission, "mission_move_robot", "coordinator")
    act(mission, "mission_move_robot", "coordinator")


def test_success_and_shared_facts():
    host, mission = fixture()
    community = deepcopy(host.week.community)
    old = deepcopy(host.appointment)
    start(mission)
    assert host.appointment != old and host.week.community == community
    assert host.transport["status"] != "confirmed" and host.week.return_status != "confirmed"
    assert mission.state["world"]["primary_available"] is False
    assert mission.state["world"]["main_blocked"] is True
    assert all(mission.state["known"][item]["last_known"] != mission.state["world"][item + "_zone"] for item in ("bag", "documents"))
    requests(mission)
    assert host.transport["person"] == BACKUP and host.week.return_status == "confirmed"
    assert host.week.return_version == mission.state["appointment_version"] and host.week.return_person == BACKUP
    locate(mission)
    load(mission)
    block(mission)
    recover(mission)
    view = mission.coordinator_view()
    assert view["status"] == "ready_to_leave" and view["unresolved"] == []
    assert view["clock_minutes"] == 20 and view["robot"]["position"] == "Departure"
    assert host.documents["location"] == "Inside bag at Departure" and host.week.papers_staged
    assert "reason" not in view["appointment"] and host.week.community == community
    reject(mission, "mission_move_robot", "coordinator")
    reject(mission, "mission_confirm_travel", "family")


def test_hidden_truth_and_actor_boundaries():
    host, mission = fixture()
    start(mission)
    view = mission.coordinator_view()
    assert "world" not in view and "primary_available" not in json.dumps(view)
    assert view["known"]["main_route"] == "unknown" and view["known"]["backup"] == "not_requested"
    assert view["known"]["documents"]["location"] is None
    assert view["controls"]["resident"] == view["controls"]["family"] == []
    # A different hidden current location cannot change any coordinator-visible fact or valid action.
    before = mission.coordinator_view()
    mission.state["world"]["documents_zone"] = "Storage"
    mission.state["world"]["bag_zone"] = "R1"
    assert mission.coordinator_view() == before
    reject(mission, "mission_backup_accept", "coordinator")
    reject(mission, "mission_opt_in", "family")
    reject(mission, "mission_request_primary", "resident")
    reject(mission, "mission_permissions", "family", coordinator=True)
    reject(mission, "mission_permissions", mystery=True)
    reject(mission, "mission_permissions", coordinator=1)
    reject(mission, "mission_advance_time", minutes=True)
    reject(mission, "mission_set_deadline", deadline_minutes=0)


def test_refusal_wait_and_no_alternate():
    host, mission = fixture()
    start(mission)
    requests(mission, accept=False)
    locate(mission)
    reject(mission, "mission_request_backup", "coordinator")
    reject(mission, "mission_backup_accept", "family")
    reject(mission, "mission_request_loading", "coordinator")
    act(mission, "mission_wait", "coordinator")
    assert mission.state["status"] == "preparing" and mission.view("resident")["unresolved"]
    act(mission, "mission_advance_time", minutes=90)
    assert mission.state["status"] == "overdue"
    reject(mission, "mission_backup_accept", "family")
    host, mission = fixture()
    start(mission)
    requests(mission)
    locate(mission)
    load(mission)
    block(mission)
    reject(mission, "mission_observe_alternate", usable=1)
    act(mission, "mission_observe_alternate", usable=False)
    reject(mission, "mission_dispatch_alternate", "coordinator")
    reject(mission, "mission_observe_alternate", usable=True)
    assert "no observed usable alternate" in " ".join(mission.view("resident")["unresolved"])


def test_revocation_cancellation_and_deadline():
    host, mission = fixture()
    start(mission)
    requests(mission)
    locate(mission)
    load(mission)
    act(mission, "mission_dispatch_main", "coordinator")
    act(mission, "mission_permissions", robot_transport=False)
    assert mission.state["robot"]["status"] == "stopped"
    reject(mission, "mission_move_robot", "coordinator")
    reject(mission, "mission_dispatch_main", "coordinator")
    act(mission, "mission_permissions", robot_transport=True)
    act(mission, "mission_dispatch_main", "coordinator")
    act(mission, "mission_cancel")
    reject(mission, "mission_move_robot", "coordinator")
    reject(mission, "mission_load_robot", "family")
    assert mission.state["world"]["bag_zone"] != "Departure"
    act(mission, "mission_reset")
    act(mission, "mission_opt_in")
    act(mission, "mission_permissions", **dict.fromkeys(PERMISSIONS, True))
    requests(mission)
    locate(mission)
    load(mission)
    block(mission)
    act(mission, "mission_observe_alternate", usable=True)
    act(mission, "mission_dispatch_alternate", "coordinator")
    act(mission, "mission_set_deadline", deadline_minutes=15)
    act(mission, "mission_move_robot", "coordinator")
    assert mission.state["clock_minutes"] == 15 and mission.state["status"] == "overdue"
    assert mission.state["world"]["bag_zone"] != "Departure"
    reject(mission, "mission_move_robot", "coordinator")
    # Revocation midway through the alternate route resumes from the same observed waypoint.
    host, mission = fixture()
    start(mission)
    requests(mission)
    locate(mission)
    load(mission)
    block(mission)
    act(mission, "mission_observe_alternate", usable=True)
    act(mission, "mission_dispatch_alternate", "coordinator")
    act(mission, "mission_move_robot", "coordinator")
    act(mission, "mission_permissions", alternate_route=False)
    reject(mission, "mission_move_robot", "coordinator")
    act(mission, "mission_permissions", alternate_route=True)
    act(mission, "mission_dispatch_alternate", "coordinator")
    assert mission.state["robot"]["position"] == "R1" and mission.state["robot"]["step"] == 1
    assert Mission.restore(host, mission.dump()).dump() == mission.dump()
    act(mission, "mission_move_robot", "coordinator")
    assert mission.state["status"] == "ready_to_leave"
    # Near the one-day clock limit, deadline interruption cannot create an unsavable overflow.
    host, mission = fixture()
    start(mission)
    requests(mission)
    locate(mission)
    load(mission)
    act(mission, "mission_set_deadline", deadline_minutes=1440)
    for _ in range(11):
        act(mission, "mission_advance_time", minutes=120)
    act(mission, "mission_advance_time", minutes=119)
    act(mission, "mission_dispatch_main", "coordinator")
    act(mission, "mission_move_robot", "coordinator")
    assert mission.state["clock_minutes"] == 1440 and mission.state["status"] == "overdue"
    assert Mission.restore(host, mission.dump()).dump() == mission.dump()
    # Revocation cancels pending backup requests, which cannot later be accepted.
    host, mission = fixture()
    start(mission)
    act(mission, "mission_request_primary", "coordinator")
    act(mission, "mission_primary_decline", "family")
    act(mission, "mission_request_backup", "coordinator")
    act(mission, "mission_permissions", backup_helper=False)
    reject(mission, "mission_backup_accept", "family")
    act(mission, "mission_permissions", backup_helper=True)
    reject(mission, "mission_backup_accept", "family")
    reject(mission, "mission_request_backup", "coordinator")


def test_restore_and_external_invalidation():
    host, mission = fixture()
    assert Mission.restore(host, mission.dump()).dump() == mission.dump()
    start(mission)
    requests(mission)
    locate(mission)
    load(mission)
    block(mission)
    saved = mission.dump()
    household_before = (deepcopy(host.appointment), deepcopy(host.transport), deepcopy(host.documents), deepcopy(host.week.history))
    restored = Mission.restore(host, json.loads(json.dumps(saved)))
    assert restored.dump() == saved and restored.coordinator_view() == mission.coordinator_view()
    assert household_before == (host.appointment, host.transport, host.documents, host.week.history)
    for mutate in (lambda d: d.update(unknown=True), lambda d: d.update(clock_minutes=True),
                   lambda d: d["known"].update(unknown=False), lambda d: d.update(status="ready_to_leave"),
                   lambda d: d["robot"].update(capability="pick_any_object"),
                   lambda d: d["known"].update(helper_loaded=False)):
        corrupt = deepcopy(saved)
        mutate(corrupt)
        try:
            Mission.restore(host, corrupt)
        except ValueError:
            pass
        else:
            raise AssertionError("Malformed restore accepted")
    recover(restored)
    assert Mission.restore(host, restored.dump()).dump() == restored.dump()
    restored.shared_changed("week_order_supplies")
    assert restored.state["status"] == "ready_to_leave"
    host.appointment["time"] = "12:00"
    host.week.legacy_changed("reschedule")
    restored.shared_changed("reschedule")
    assert restored.state["status"] == "invalidated"
    reject(restored, "mission_move_robot", "coordinator")
    assert Mission.restore(host, restored.dump()).state["status"] == "invalidated"


def test_restore_rejects_fabricated_loading_and_shared_changes():
    host, mission = fixture()
    start(mission)
    requests(mission)
    corrupt = mission.dump()
    corrupt["known"].update(documents_staged=True, helper_loaded=True, loading_requested=True)
    corrupt["robot"]["status"] = "loaded"
    try:
        Mission.restore(host, corrupt)
    except ValueError:
        pass
    else:
        raise AssertionError("Unobserved, physically separated items accepted as loaded")
    # Shared mutations are compared as facts, so wrapper action names cannot bypass invalidation.
    for action in ("week_inject", "week_helper_availability", "confirm_documents"):
        host, mission = fixture()
        start(mission)
        requests(mission)
        locate(mission)
        load(mission)
        if action == "week_inject":
            host.week.apply(action, "resident", {"scenario": "papers_moved"})
        elif action == "week_helper_availability":
            host.week.profile["helper"] = BACKUP
            host.week.apply(action, "family", {"available": False})
        else:
            host.documents["location"] = "Other observed location"
        mission.shared_changed(action)
        assert mission.state["status"] == "invalidated", action
        reject(mission, "mission_dispatch_main", "coordinator")
    # A return confirmed for an older appointment cannot substantiate readiness.
    host, mission = fixture()
    start(mission)
    requests(mission)
    locate(mission)
    load(mission)
    block(mission)
    host.week.return_version -= 1
    recover(mission)
    assert mission.state["status"] == "preparing" and not mission._ready()


def run():
    for test in (test_success_and_shared_facts, test_hidden_truth_and_actor_boundaries,
                 test_refusal_wait_and_no_alternate, test_revocation_cancellation_and_deadline,
                 test_restore_and_external_invalidation, test_restore_rejects_fabricated_loading_and_shared_changes):
        test()
    print("Mission acceptance checks passed (success, refusal, hidden observations, blocked route, cancellation, permissions, deadline, restore).")


if __name__ == "__main__":
    run()
