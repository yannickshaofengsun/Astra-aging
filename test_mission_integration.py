"""Run: python3 test_mission_integration.py. No live model or canonical state."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from mission import PERMISSIONS
from persistence import _encoded, load_household
from simulation import Household, InvalidAction


def event(host, action, role="resident", **payload):
    return host.event(action, role, host.revision, payload)


def proposal(host, action, revision=None):
    return host.apply_mission_proposal({"action": action, "reason": "Test fixture selecting a valid bounded action."},
                                       host.revision if revision is None else revision)


def rejects(fn):
    try:
        fn()
    except (ValueError, InvalidAction):
        return
    raise AssertionError("Invalid operation was accepted")


def prepared(host):
    event(host, "mission_reset" if host.mission.view("resident")["active"] else "mission_start")
    event(host, "mission_opt_in")
    event(host, "mission_permissions", **dict.fromkeys(PERMISSIONS, True))
    assert proposal(host, "mission_request_primary")["accepted"]
    event(host, "mission_primary_decline", "family")
    assert proposal(host, "mission_request_backup")["accepted"]
    event(host, "mission_backup_accept", "family")
    event(host, "mission_confirm_travel", "family")
    assert proposal(host, "mission_request_search")["accepted"]
    for item in ("bag", "documents"):
        event(host, "mission_check_" + item)
        event(host, "mission_observe_" + item)
    assert proposal(host, "mission_request_loading")["accepted"]
    event(host, "mission_stage_documents", "family")
    event(host, "mission_load_robot", "family")


def check():
    with TemporaryDirectory() as directory:
        path = Path(directory) / "mission.json"
        host = Household(save_path=path)
        event(host, "mission_start")
        assert host.transport["person"] is None
        pending = deepcopy(host.mission.dump())
        restored = Household(save_path=path)
        assert restored.mission_persistence["status"] == "restored"
        assert restored.mission.dump() == pending and restored.revision > host.revision
        restarted = Household(save_path=path)
        assert restarted.revision > restored.revision
        event(restarted, "mission_opt_in")
        event(restarted, "mission_permissions", coordinator=True)
        revision = restarted.revision
        first = proposal(restarted, "mission_request_primary")
        assert first["accepted"]
        before = restarted.mission.dump()
        assert proposal(restarted, "mission_request_primary", revision)["rejection"] == "stale"
        assert restarted.mission.dump() == before
        assert not proposal(restarted, "mission_primary_decline")["accepted"]
        assert restarted.mission.dump() == before
        event(restarted, "mission_permissions", coordinator=False)
        before = restarted.mission.dump()
        assert not proposal(restarted, "mission_request_search")["accepted"]
        assert restarted.mission.dump() == before
        after = Household(save_path=path)
        assert after.mission.dump() == restarted.mission.dump()
        assert after.mission_proposals == restarted.mission_proposals

        host = Household(save_path=path)
        prepared(host)
        assert proposal(host, "mission_dispatch_main")["accepted"]
        assert proposal(host, "mission_move_robot")["accepted"]
        before = host.mission.dump()
        loaded = Household(save_path=path)
        assert loaded.mission.dump() == before, "Reload repeated robot movement"
        assert proposal(loaded, "mission_move_robot")["accepted"]
        assert loaded.mission.view("resident")["robot"]["status"] == "blocked"
        event(loaded, "mission_observe_alternate", usable=True)
        assert proposal(loaded, "mission_dispatch_alternate")["accepted"]
        assert proposal(loaded, "mission_move_robot")["accepted"]
        event(loaded, "mission_cancel")
        cancelled = loaded.mission.dump()
        assert not proposal(loaded, "mission_move_robot")["accepted"]
        assert loaded.mission.dump() == cancelled
        restored = Household(save_path=path)
        assert restored.mission.dump() == cancelled and restored.mission.view("resident")["status"] == "cancelled"

        # Even a correctly checksummed file must satisfy semantic enum validation.
        envelope = json.loads(path.read_text())
        envelope["data"]["week"]["permissions"]["calendar"] = True
        envelope["data"]["week"]["community"].update(status="cancel_pending", arrangement="cancel_pending", choice=True)
        envelope["sha256"] = sha256(_encoded(envelope["data"])).hexdigest()
        path.write_text(json.dumps(envelope))
        rejects(lambda: load_household(path))
        before = restored.mission.dump()
        rejects(lambda: event(restored, "mission_restore"))
        assert restored.mission.dump() == before
        invalid = Household(save_path=path)
        assert invalid.mission_persistence["status"] == "load_error" and not invalid.mission.view("resident")["active"]
        path.write_text('{"schema":1,"schema":1}')
        rejects(lambda: load_household(path))
        path.write_text("x" * 262145)
        rejects(lambda: load_household(path))
    print("PASS: mission revision/actor boundaries, pending and moving restart, no replay, cancellation, and malformed-save rejection.")


if __name__ == "__main__":
    check()
