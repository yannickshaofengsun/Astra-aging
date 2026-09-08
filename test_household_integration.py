"""Run: python3 test_household_integration.py. Isolated households; no model or server."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from coordination import PROPOSAL_FIELDS
from persistence import _encoded
from simulation import Household, InvalidAction


def event(host, action, payload=None, role="resident", actor_id=None):
    return host.event(action, role, host.revision, payload, actor_id=actor_id)


def domain_states(host):
    return {key: getattr(host, key).dump()
            for key in ("mission", "coordination", "meal", "hospital", "assessment", "family_edition")}


def rejects_unchanged(host, operation):
    before = host.view("resident")
    try:
        operation()
    except InvalidAction:
        assert host.view("resident") == before, "Rejected operation changed household state"
    else:
        raise AssertionError("Invalid operation was accepted")


def write_envelope(path, envelope):
    envelope["sha256"] = sha256(_encoded(envelope["data"])).hexdigest()
    path.write_bytes(_encoded(envelope))


def clarification():
    result = dict.fromkeys(PROPOSAL_FIELDS, "")
    result.update(intent="clarify", quantity=1, recipients=[], question="Please clarify the request.")
    return result


def check():
    with TemporaryDirectory() as directory:
        path = Path(directory) / "household.json"
        host = Household(save_path=path)
        event(host, "mission_start")
        mission = deepcopy(host.mission.dump())

        # An existing schema-1 mission gains fresh domains without replaying its actions.
        envelope = json.loads(path.read_text())
        envelope["schema"] = 1
        for key in ("coordination", "meal", "hospital", "assessment", "family_edition"):
            envelope["data"].pop(key)
        envelope["data"]["appointment"].pop("location")
        write_envelope(path, envelope)
        host = Household(save_path=path)
        assert host.mission_persistence["status"] == "restored"
        assert host.mission.dump() == mission
        initial_version = host.coordination.version
        event(host, "meal_start")
        assert host.coordination.version == initial_version, "Migration left stale shared facts"
        host.begin_coordination("pending", "Please clarify this request.", host.revision)
        version = host.coordination.version
        event(host, "meal_tick", {key: host.meal.dump()[key] for key in ("episode_id", "step")})
        assert host.coordination.version == version, "Unrelated movement invalidated interpretation"
        event(host, "coordination_cancel", {"request_id": "pending"})

        event(host, "coordination_next_day")
        assert host.coordination.day == host.meal.dump()["day"] == 2
        before = domain_states(host)
        restored = Household(save_path=path)
        assert restored.mission_persistence["status"] == "restored"
        assert domain_states(restored) == before, "Restart replayed or changed domain effects"

        envelope = json.loads(path.read_text())
        envelope["schema"] = 2
        envelope["data"].pop("family_edition")
        write_envelope(path, envelope)
        migrated = Household(save_path=path)
        assert migrated.mission_persistence["status"] == "restored"
        assert all(domain_states(migrated)[key] == value for key, value in before.items()
                   if key != "family_edition"), "Schema-2 migration changed existing domain facts"
        restored = migrated

        # Every fresh-household entry point resets the day consistently across domains.
        for action, payload in (("week_reset", None), ("week_select_profile", {"id": "couple"}),
                                ("reset", None)):
            event(restored, action, payload)
            assert restored.coordination.day == restored.meal.dump()["day"] == 1
            event(restored, "coordination_next_day")
            assert restored.coordination.day == restored.meal.dump()["day"] == 2

        # A correct checksum cannot make contradictory domain state safe to install.
        envelope = json.loads(path.read_text())
        envelope["data"]["meal"]["day"] = 999
        write_envelope(path, envelope)
        rejects_unchanged(restored, lambda: event(restored, "mission_restore"))

    host = Household()
    host.begin_coordination("cancelled", "Please help.", host.revision)
    context = host.coordination_context("cancelled")
    event(host, "coordination_cancel", {"request_id": "cancelled"})
    rejects_unchanged(host, lambda: host.accept_coordination("cancelled", clarification(), context["version"]))
    before = host.view("resident")
    duplicate = host.begin_coordination("cancelled", "Please help.", 0)
    assert duplicate["duplicate"] and host.view("resident") == before

    host.begin_coordination("permission_change", "Please help.", host.revision)
    context = host.coordination_context("permission_change")
    event(host, "coordination_permissions", {"orders": True})
    rejects_unchanged(host, lambda: host.accept_coordination("permission_change", clarification(), context["version"]))

    event(host, "coordination_availability", {"available": False}, "family", "morgan")
    assert not host.coordination.available("morgan") and host.coordination.available("alex")
    rejects_unchanged(host, lambda: event(host, "coordination_availability",
                                       {"actor_id": "alex", "available": False}, "family", "morgan"))
    for role, actor in (("family", "resident"), ("resident", "alex"), ("family", "unknown")):
        rejects_unchanged(host, lambda: event(host, "coordination_next_day", role=role, actor_id=actor))

    host = Household()
    event(host, "reschedule")
    event(host, "confirm_ride", role="family", actor_id="morgan")
    assert host.transport["person"] == "Morgan", "Named pickup confirmation was attributed to another person"
    rejects_unchanged(host, lambda: event(host, "decline_ride", role="family", actor_id="alex"))
    event(host, "decline_ride", role="family", actor_id="morgan")
    assert host.transport["status"] == "declined"

    print("PASS: schema migration, no-effect restart, domain day alignment, atomic restore, "
          "named actor boundaries, cancellation, relevant staleness and request deduplication.")


def check_reply_resume():
    from hospital import PERMISSIONS

    def run(host, identity):
        for _ in range(12):
            if not host.advance_coordination(identity):
                return
        raise AssertionError("The bounded request did not settle")

    def request(host, identity, intent):
        event(host, "hospital_permissions", dict.fromkeys(PERMISSIONS, True))
        event(host, "coordination_permissions", {"notify": True})
        proposal = dict.fromkeys(PROPOSAL_FIELDS, "")
        proposal.update(intent=intent, item="visit-001" if intent == "hospital_coordination" else "rx-001",
                        quantity=1, helper="alex", recipients=["alex", "morgan"],
                        summary="Supplied administrative request")
        host.begin_coordination(identity, "Coordinate the supplied hospital record.", host.revision)
        host.accept_coordination(identity, proposal, host.coordination.version)
        run(host, identity)

    with TemporaryDirectory() as directory:
        path = Path(directory) / "visit.json"
        host = Household(save_path=path)
        request(host, "visit", "hospital_coordination")
        messages = {message["metadata"]["kind"]: message for message in host.coordination.state["messages"]
                    if message["kind"] == "hospital"}
        partial = {"decisions": [{"message_id": messages[kind]["id"], "status": status}
                                 for kind, status in (("driver", "accepted"), ("companion", "declined"))],
                   "question": ""}
        host.accept_recipient_reply("partial", "alex", "I can drive but cannot stay.",
                                    partial, host.coordination.version)
        backups = [commitment for commitment in host.hospital.state["commitments"]
                   if commitment["kind"] == "companion" and commitment["actor_id"] == "morgan"]
        assert len(backups) == 1 and backups[0]["status"] == "requested", "Partial reply did not resume only its missing role"
        assert messages["return"]["status"] == "available", "Unmentioned return travel was accepted"
        assert host.coordination._get("requests", "visit")["status"] != "completed"

        before = domain_states(host)
        host = Household(save_path=path)
        assert host.mission_persistence["status"] == "restored" and domain_states(host) == before
        host.accept_recipient_reply("partial", "alex", "I can drive but cannot stay.", partial, 0)
        assert domain_states(host) == before, "Duplicate natural reply repeated automatic effects"
        context = host.recipient_context("morgan", host.revision)
        event(host, "coordination_cancel", {"request_id": "visit"})
        rejects_unchanged(host, lambda: host.accept_recipient_reply("late", "morgan", "I can stay.",
            {"decisions": [{"message_id": backups[0]["message_id"], "status": "accepted"}], "question": ""},
            context["version"]))

        # A helper becoming unavailable must resume the existing permitted recovery.
        host = Household(save_path=Path(directory) / "availability.json")
        request(host, "availability", "hospital_coordination")
        own = [m for m in host.coordination.state["messages"] if m["kind"] == "hospital"]
        host.accept_recipient_reply("all-roles", "alex", "I can do all three roles.",
            {"decisions": [{"message_id": m["id"], "status": "accepted"} for m in own], "question": ""},
            host.coordination.version)
        assert host.coordination._get("requests", "availability")["status"] == "completed"
        event(host, "coordination_availability", {"available": False}, "family", "alex")
        assert all(m["status"] == "accepted" for m in own), "Today's absence withdrew a future dated promise"
        event(host, "coordination_next_day")
        assert all(m["status"] == "accepted" for m in own), "A new day withdrew a still-valid dated promise"
        event(host, "coordination_set_availability", {"actor_id": "alex", "start_date": host.appointment["date"],
              "end_date": host.appointment["date"], "available": False}, "family", "alex")
        replacements = [c for c in host.hospital.state["commitments"] if c["actor_id"] == "morgan"]
        assert len(replacements) == 3 and all(c["status"] == "requested" for c in replacements), "Availability withdrawal did not resume permitted backup requests"
        assert host.coordination._get("requests", "availability")["status"] == "waiting_helper"
        before = domain_states(host)
        restored = Household(save_path=host.save_path)
        assert restored.mission_persistence["status"] == "restored" and domain_states(restored) == before

        host = Household(save_path=Path(directory) / "pharmacy.json")
        request(host, "rx", "prescription_refill")
        event(host, "hospital_publish_pharmacy", {"status": "ready"})
        run(host, "rx")
        pickup = next(commitment for commitment in host.hospital.state["commitments"] if commitment["kind"] == "pickup")
        host.accept_recipient_reply("rx-accept", "alex", "I can collect it.",
            {"decisions": [{"message_id": pickup["message_id"], "status": "accepted"}], "question": ""},
            host.coordination.version)
        assert host.hospital.state["refills"]["rx"]["status"] == "ready"
        assert host.coordination._get("requests", "rx")["status"] != "completed"
        event(host, "hospital_collect", {"request_id": "rx"}, "family", "alex")
        assert host.hospital.state["refills"]["rx"]["status"] == "collected"
        assert host.coordination._get("requests", "rx")["status"] != "completed", "Collection was treated as delivery"
        event(host, "hospital_deliver", {"request_id": "rx"}, "family", "alex")
        assert host.coordination._get("requests", "rx")["status"] == "completed"
        assert host.coordination._get("messages", pickup["message_id"])["status"] == "completed"
        before = domain_states(host)
        restored = Household(save_path=host.save_path)
        assert restored.mission_persistence["status"] == "restored" and domain_states(restored) == before

    print("PASS: partial hospital reply resumes one backup, stale cancellation and duplicate replies are inert, "
          "pharmacy acceptance/collection/delivery remain distinct, and reload repeats no effects.")


def check_memory_context():
    with TemporaryDirectory() as directory:
        host = Household(save_path=Path(directory) / "memory.json")
        before = host.context_revision
        event(host, "coordination_remember_preference",
              {"key": "delivery_window", "value": "afternoon", "audience": ["resident"]})
        assert host.context_revision == before + 1, "A memory edit left cached chat context current"
        assert "delivery_window" not in host.view("family", "alex")["coordination"]["preferences"]
        remembered = host.context_revision
        event(host, "meal_start")
        event(host, "meal_tick", {key: host.meal.dump()[key] for key in ("episode_id", "step")})
        assert host.context_revision == remembered, "Unrelated movement reset remembered conversation context"

        proposal = dict.fromkeys(PROPOSAL_FIELDS, "")
        proposal.update(intent="forget_preference", quantity=1, recipients=[],
                        memory={"key": "delivery_window", "value": None, "audience": []})
        host.begin_coordination("forget-window", "Forget my delivery preference.", host.revision)
        host.accept_coordination("forget-window", proposal, host.coordination.version)
        for _ in range(12):
            if not host.advance_coordination("forget-window"):
                break
        assert host.context_revision == remembered + 1, "Natural forgetting did not invalidate old chat context"
        assert host.coordination._get("requests", "forget-window")["status"] == "completed"

        before = host.context_revision
        event(host, "coordination_set_availability", {"actor_id": "alex", "start_date": "2026-09-17",
              "end_date": "2026-09-18", "available": True}, "family", "alex")
        assert host.context_revision == before + 1, "Dated availability did not update shared context"
        assert host.coordination.availability_for("alex", "2026-09-17") is True
        snapshots = domain_states(host)
        restored = Household(save_path=host.save_path)
        assert restored.mission_persistence["status"] == "restored"
        assert domain_states(restored) == snapshots, "Restart replayed continuity effects"
        before = restored.context_revision
        event(restored, "meal_pause")
        assert restored.context_revision == before, "Restore left a stale observed memory revision"

    print("PASS: memory edits and natural forgetting invalidate cached context, scoped preferences stay private, "
          "dated availability shares the epoch, and restart/movement replay no memory changes.")


if __name__ == "__main__":
    check()
    check_reply_resume()
    check_memory_context()
