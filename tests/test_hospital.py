"""Supplied proposal fixtures exercise real domains; no model or provider network."""
from copy import deepcopy
import json

from careanchor.coordination import PROPOSAL_FIELDS
from careanchor.hospital import Hospital, PERMISSIONS
from careanchor.simulation import Household


def reject(call):
    try:
        call()
    except ValueError:
        return
    raise AssertionError("Expected a validated rejection")


def request(host, identity, intent="hospital_coordination", visit_helpers=None, helper="alex"):
    proposal = dict.fromkeys(PROPOSAL_FIELDS, "")
    proposal.update(intent=intent, item="visit-001" if intent == "hospital_coordination" else "rx-001",
                    quantity=1, recipients=["alex", "morgan"], helper=helper, summary="Supplied administrative test request")
    if visit_helpers is not None:
        proposal["visit_helpers"] = visit_helpers
    host.coordination.begin(identity, "Please coordinate this supplied administrative record.")
    host.coordination.accept(identity, proposal, host.coordination.version)
    run(host, identity)


def run(host, identity):
    for _ in range(12):
        if not host.coordination.advance(identity):
            return
    raise AssertionError("A bounded administrative pass should settle or wait")


def reply(host, commitment, status):
    host.coordination.apply("coordination_reply", "family",
        {"message_id": commitment["message_id"], "actor_id": commitment["actor_id"], "status": status}, commitment["actor_id"])


def fresh():
    host = Household(save_path=None)
    host.hospital.apply("hospital_permissions", "resident", dict.fromkeys(PERMISSIONS, True))
    return host


def check_visit():
    host = fresh()
    old_appointment, old_context = deepcopy(host.appointment), host.hospital.context()
    host.hospital.apply("hospital_publish_visit", "resident", {"fixture": "time_location_change"})
    assert host.appointment == old_appointment and host.hospital.context() == old_context
    assert host.hospital.view("resident")["retrieved_visit"] is None
    community = deepcopy(host.week.community)
    request(host, "visit-first")
    retrieved = host.hospital.view("resident")["retrieved_visit"]
    assert retrieved["source_version"] == 2 and retrieved["retrieved_at"]["basis"] == "simulation_clock"
    assert host.appointment["location"] == retrieved["appointment"]["location"]
    assert host.appointment["time"] == "14:00" and host.transport["status"] != "confirmed"
    assert host.week.community == community
    commitments = {c["kind"]: c for c in host.hospital.state["commitments"]}
    assert set(commitments) == {"driver", "companion", "return"}
    reply(host, commitments["driver"], "accepted")
    assert host.transport["status"] == "confirmed" and host.week.return_status != "confirmed"
    assert commitments["companion"]["status"] == "requested" and commitments["return"]["status"] == "requested"
    reply(host, commitments["companion"], "declined")
    run(host, "visit-first")
    backup = host.hospital.state["commitments"][-1]
    assert backup["kind"] == "companion" and backup["actor_id"] == "morgan" and backup["status"] == "requested"
    reply(host, commitments["return"], "accepted")
    assert backup["status"] == "requested", "Travel acceptance must not accept companionship"
    reply(host, backup, "accepted")
    run(host, "visit-first")
    assert host.hospital.state["requests"]["visit-first"]["status"] == "arranged"
    assert host.week.return_version == host.week.appointment_version
    assert all(c["actor_id"] == "alex" for c in host.hospital.view("family", "alex")["visit_commitments"])
    for role in ("family", "coordinator"):
        shown = json.dumps(host.hospital.view(role, "alex" if role == "family" else None))
        assert "Private supplied follow-up purpose" not in shown
        assert "provider_visit" not in shown and "provider_pharmacy" not in shown

    saved, shared, inbox = host.hospital.dump(), deepcopy(host.appointment), host.coordination.dump()
    restored = Hospital.restore(host, saved)
    assert restored.dump() == saved and host.appointment == shared and host.coordination.dump() == inbox
    # Rechecking the same source reuses current commitments and creates no new inbox tasks.
    before_messages = len(host.coordination.state["messages"])
    request(host, "same-source", visit_helpers=host.hospital.context()["current_visit_helpers"])
    assert len(host.coordination.state["messages"]) == before_messages
    assert host.hospital.state["requests"]["same-source"]["status"] == "arranged"

    supplied = deepcopy(host.hospital.state["provider_visit"])
    supplied.update(source_version=3, source_timestamp="2026-09-15T10:00:00Z", provenance="supplied_record")
    supplied["appointment"].update(date="2026-09-21", time="09:30", pickup="08:45", location="Supplied East reception")
    known = host.hospital.context()
    host.hospital.apply("hospital_supply_notice", "resident", {"record": supplied})
    assert host.hospital.context() == known and host.appointment == shared
    request(host, "changed-source")
    assert host.appointment["location"] == "Supplied East reception" and host.transport["status"] != "confirmed"
    assert backup["status"] == "invalidated"
    assert host.hospital.state["requests"]["visit-first"]["status"] == "stale"
    assert all(c["status"] != "accepted" for c in host.hospital.state["commitments"])
    assert host.week.community == community

    # External changes invalidate once. Later unrelated work must not repeat effects.
    host.appointment["time"] = "12:30"
    host.week.legacy_changed("reschedule")
    assert host.hospital.shared_changed()
    once, inbox = host.hospital.dump(), host.coordination.dump()
    assert not host.hospital.shared_changed()
    assert host.hospital.dump() == once and host.coordination.dump() == inbox
    host.meal.apply("meal_start", "resident")
    host.meal.apply("meal_tick", "resident", {"episode_id": host.meal.state["episode_id"], "step": host.meal.state["step"]})
    assert not host.hospital.shared_changed() and host.hospital.dump() == once
    return host, saved


def check_refill():
    host = fresh()
    request(host, "refill", "prescription_refill")
    refill = host.hospital.state["refills"]["refill"]
    assert refill["status"] == "authorization_pending"
    assert not host.hospital.state["commitments"]
    reject(lambda: host.hospital.apply("hospital_collect", "family", {"request_id": "refill"}, "alex"))
    old_context = host.hospital.context()
    host.hospital.apply("hospital_publish_pharmacy", "resident", {"status": "ready"})
    assert host.hospital.context() == old_context and refill["status"] == "authorization_pending"
    run(host, "refill")
    assert refill["status"] == "ready" and refill["collected_by"] is None
    pickup = host.hospital.state["commitments"][-1]
    assert pickup["kind"] == "pickup" and pickup["status"] == "requested"
    reject(lambda: host.hospital.apply("hospital_collect", "family", {"request_id": "refill"}, "alex"))
    reply(host, pickup, "accepted")
    run(host, "refill")
    reject(lambda: host.hospital.apply("hospital_deliver", "family", {"request_id": "refill"}, "alex"))
    reject(lambda: host.hospital.apply("hospital_collect", "family", {"request_id": "refill"}, "morgan"))
    host.hospital.apply("hospital_collect", "family", {"request_id": "refill"}, "alex")
    assert refill["status"] == "collected" and refill["delivered_by"] is None
    host.hospital.apply("hospital_deliver", "family", {"request_id": "refill"}, "alex")
    run(host, "refill")
    assert refill["status"] == "delivered" and "ingestion is not established" in refill["evidence"]
    assert host.hospital.state["requests"]["refill"]["status"] == "completed"
    assert next(m for m in host.coordination.state["messages"] if m["id"] == pickup["message_id"])["status"] == "completed"
    assert "existing_prescription" not in json.dumps(host.hospital.context())
    assert not host.hospital.view("family", "morgan")["pickup_commitments"]
    assert Hospital.restore(host, host.hospital.dump()).dump() == host.hospital.dump()
    return host


def check_failures():
    host = fresh()
    host.hospital.apply("hospital_permissions", "resident", {"backup_requests": False})
    request(host, "no-backup")
    companion = next(c for c in host.hospital.state["commitments"] if c["kind"] == "companion")
    reply(host, companion, "declined")
    run(host, "no-backup")
    assert len(host.hospital.state["commitments"]) == 3
    assert host.hospital.state["requests"]["no-backup"]["status"] != "arranged"
    host.hospital.cancel_request("no-backup")
    before = host.hospital.dump()
    assert not host.hospital.advance_request("no-backup")["changed"]
    reject(lambda: host.hospital.recipient_reply(companion["id"], companion["actor_id"], "accepted"))
    assert host.hospital.dump() == before

    host = fresh()
    request(host, "revoked")
    driver = host.hospital.state["commitments"][0]
    host.hospital.apply("hospital_permissions", "resident", {"visit_requests": False})
    before = host.hospital.dump()
    reject(lambda: host.hospital.recipient_reply(driver["id"], "alex", "accepted"))
    assert host.hospital.dump() == before
    host.hospital.next_day(2)
    assert not host.hospital.advance_request("revoked")["changed"]
    assert host.hospital.state["requests"]["revoked"]["status"] == "stale"

    host = fresh()
    request(host, "withdrawn-ready", "prescription_refill")
    host.hospital.apply("hospital_publish_pharmacy", "resident", {"status": "ready"})
    run(host, "withdrawn-ready")
    pickup = host.hospital.state["commitments"][-1]
    reply(host, pickup, "accepted")
    run(host, "withdrawn-ready")
    host.hospital.apply("hospital_publish_pharmacy", "resident", {"status": "authorization_pending"})
    before = host.hospital.dump()
    reject(lambda: host.hospital.apply("hospital_collect", "family", {"request_id": "withdrawn-ready"}, "alex"))
    assert host.hospital.dump() == before
    run(host, "withdrawn-ready")
    assert host.hospital.state["refills"]["withdrawn-ready"]["status"] == "authorization_pending"
    assert pickup["status"] == "invalidated"

    # A later day resumes the same pending pharmacy request, without resubmission.
    submitted = sum("Submitted existing-prescription" in event["text"] for event in host.hospital.state["events"])
    host.coordination.apply("coordination_next_day", "resident")
    assert host.hospital.state["requests"]["withdrawn-ready"]["status"] == "stale"
    assert Hospital.restore(host, host.hospital.dump()).dump() == host.hospital.dump()
    host.hospital.apply("hospital_resume", "resident", {"request_id": "withdrawn-ready"})
    run(host, "withdrawn-ready")
    assert sum("Submitted existing-prescription" in event["text"] for event in host.hospital.state["events"]) == submitted
    assert host.hospital.state["refills"]["withdrawn-ready"]["status"] == "authorization_pending"
    assert Hospital.restore(host, host.hospital.dump()).dump() == host.hospital.dump()

    for mutate in (
        lambda s: s.update(schema=True),
        lambda s: s["permissions"].update(retrieve_records="yes"),
        lambda s: s["requests"]["withdrawn-ready"].update(helper=[]),
        lambda s: s["commitments"][0].update(actor_id="stranger"),
        lambda s: s["refills"]["withdrawn-ready"].update(status="delivered", collected_by=None, delivered_by=None),
        lambda s: s["provider_visit"].update(source_timestamp="yesterday"),
    ):
        broken = host.hospital.dump()
        mutate(broken)
        reject(lambda: Hospital.restore(host, broken))

    host = fresh()
    request(host, "withdraw-visit")
    for commitment in list(host.hospital.state["commitments"]):
        reply(host, commitment, "accepted")
    run(host, "withdraw-visit")
    companion = next(c for c in host.hospital.state["commitments"] if c["kind"] == "companion")
    travel = deepcopy(host.transport)
    host.hospital.apply("hospital_withdraw", "family", {"commitment_id": companion["id"]}, "alex")
    run(host, "withdraw-visit")
    assert host.transport == travel and host.hospital.state["commitments"][-1]["actor_id"] == "morgan"
    assert host.hospital.state["commitments"][-1]["kind"] == "companion"
    assert next(m for m in host.coordination.state["messages"] if m["id"] == companion["message_id"])["status"] == "cancelled"
    assert Hospital.restore(host, host.hospital.dump()).dump() == host.hospital.dump()
    reject(lambda: host.hospital.apply("hospital_resume", "resident", {"request_id": []}))
    reject(lambda: host.hospital.advance_request([]))


def check_split_helpers():
    host = fresh()
    split = {"driver": "alex", "companion": "morgan", "return": "alex"}
    request(host, "split", visit_helpers=split, helper="")
    commitments = list(host.hospital.state["commitments"])
    assert {c["kind"]: c["actor_id"] for c in commitments} == split
    for commitment in commitments:
        reply(host, commitment, "accepted")
    run(host, "split")
    assert host.hospital.context()["current_visit_helpers"] == split
    assert host.hospital.state["requests"]["split"]["helpers"] == split
    snapshot, messages = host.hospital.dump(), host.coordination.dump()
    assert Hospital.restore(host, snapshot).dump() == snapshot
    assert host.coordination.dump() == messages

    host.hospital.apply("hospital_publish_visit", "resident", {"fixture": "time_location_change"})
    known_split = host.hospital.context()["current_visit_helpers"]
    assert known_split == split
    request(host, "split-updated", visit_helpers=known_split, helper="")
    current = [c for c in host.hospital.state["commitments"] if c["request_id"] == "split-updated"]
    assert {c["kind"]: c["actor_id"] for c in current} == split
    assert all(c["status"] == "invalidated" for c in commitments)
    assert all(c["status"] == "requested" for c in current), "Changed notice must not reuse old acceptances"
    assert host.transport["status"] != "confirmed" and host.week.return_status != "confirmed"
    assert Hospital.restore(host, host.hospital.dump()).dump() == host.hospital.dump()

    fallback = fresh()
    request(fallback, "fallback", visit_helpers={"driver": "", "companion": "morgan", "return": ""})
    assert fallback.hospital.state["requests"]["fallback"]["helpers"] == split
    old = fresh()
    request(old, "legacy")
    saved = old.hospital.dump()
    for item in saved["requests"].values():
        item.pop("helpers")
    before_messages = old.coordination.dump()
    migrated = Hospital.restore(old, saved)
    assert migrated.state["requests"]["legacy"]["helpers"] == dict.fromkeys(("driver", "companion", "return"), "alex")
    assert old.coordination.dump() == before_messages
    for malformed in ({"driver": "alex"}, {"driver": "alex", "companion": "stranger", "return": "alex"},
                      {"driver": "", "companion": "morgan", "return": "alex"}):
        before = old.hospital.dump()
        reject(lambda: old.hospital.start_request("bad-map", {"intent": "hospital_coordination", "item": "visit-001",
               "helper": "", "recipients": [], "visit_helpers": malformed}))
        assert old.hospital.dump() == before

    # Changing just one named duty preserves the other accepted responsibilities,
    # which remain withdrawable through the current request that reuses them.
    changed = fresh()
    request(changed, "all-alex")
    initial = list(changed.hospital.state["commitments"])
    for commitment in initial:
        reply(changed, commitment, "accepted")
    run(changed, "all-alex")
    request(changed, "new-companion", visit_helpers=split)
    assert initial[0]["status"] == initial[2]["status"] == "accepted"
    assert initial[1]["status"] == "invalidated"
    new_companion = changed.hospital.state["commitments"][-1]
    reply(changed, new_companion, "accepted")
    run(changed, "new-companion")
    assert any(c["action"] == "hospital_withdraw" and c["payload"]["commitment_id"] == initial[0]["id"]
               for c in changed.hospital.view("family", "alex")["controls"])
    changed.hospital.apply("hospital_withdraw", "family", {"commitment_id": initial[0]["id"]}, "alex")
    run(changed, "new-companion")
    assert changed.hospital.state["commitments"][-1]["kind"] == "driver"
    assert changed.hospital.state["commitments"][-1]["actor_id"] == "morgan"
    assert initial[2]["status"] == "accepted" and new_companion["status"] == "accepted"
    assert Hospital.restore(changed, changed.hospital.dump()).dump() == changed.hospital.dump()


def check_visit_progress_summary():
    host = fresh()
    host.coordination.apply("coordination_permissions", "resident", {"notify": True})
    request(host, "progress", visit_helpers={"driver": "alex", "companion": "morgan", "return": "alex"})
    commitments = {c["kind"]: c for c in host.hospital.state["commitments"]}
    summaries = [host.coordination.state["requests"][0]["summary"]]

    def respond(commitment, status):
        host.event("coordination_reply", "family", host.revision,
                   {"message_id": commitment["message_id"], "status": status}, commitment["actor_id"])
        result = next(r for r in host.view("resident")["coordination"]["requests"] if r["id"] == "progress")
        assert result["summary"] != summaries[-1], "Each real responsibility change needs a meaningful resident update"
        assert result["summary"] == host.hospital.state["requests"]["progress"]["result"]
        assert len(result["summary"]) <= 400, "The coordinator must not truncate responsibility or evidence details"
        assert "Return pickup time is unknown" in result["summary"]
        assert "Attendance and physical paperwork preparation remain unreported" in result["summary"]
        summaries.append(result["summary"])
        return result

    progress = respond(commitments["driver"], "accepted")
    assert progress["status"] == "waiting_helper"
    assert "Outbound driver: Alex accepted" in progress["summary"]
    assert "Hospital companion: Morgan pending" in progress["summary"]
    assert "Return driver: Alex pending" in progress["summary"]
    assert commitments["companion"]["status"] == commitments["return"]["status"] == "requested"

    declined = respond(commitments["companion"], "declined")
    backup = host.hospital.state["commitments"][-1]
    assert backup["kind"] == "companion" and backup["actor_id"] == "alex"
    assert declined["status"] == "waiting_helper"
    assert "Hospital companion: Morgan declined, Alex pending" in declined["summary"]
    assert "Return driver: Alex pending" in declined["summary"]
    accepted = respond(backup, "accepted")
    assert accepted["status"] == "waiting_helper"
    assert "Hospital companion: Morgan declined, Alex accepted" in accepted["summary"]
    completed = respond(commitments["return"], "accepted")
    assert completed["status"] == "completed" and "Return driver: Alex accepted" in completed["summary"]
    assert Hospital.restore(host, host.hospital.dump()).dump() == host.hospital.dump()


def check_dated_visit_continuity():
    host = fresh()
    host.coordination.apply("coordination_permissions", "resident", {"notify": True})
    request(host, "dated", visit_helpers={"driver": "alex", "companion": "morgan", "return": "alex"})
    commitments = {c["kind"]: c for c in host.hospital.state["commitments"]}
    host.coordination.apply("coordination_set_availability", "family",
        {"actor_id": "alex", "start_date": "2026-09-17", "end_date": "2026-09-17", "available": False}, "alex")
    before = host.hospital.dump()
    reject(lambda: host.hospital.recipient_reply(commitments["driver"]["id"], "alex", "accepted"))
    assert host.hospital.dump() == before, "Today's availability must not override a known visit-date conflict"
    host.coordination.apply("coordination_remove_availability", "family",
        {"actor_id": "alex", "start_date": "2026-09-17", "end_date": "2026-09-17"}, "alex")
    assert host.coordination.availability_for("alex", "2026-09-17") is None

    host.event("coordination_reply", "family", host.revision,
               {"message_id": commitments["driver"]["message_id"], "status": "accepted"}, "alex")
    saved_commitments = deepcopy(host.hospital.state["commitments"])
    for _ in range(2):
        host.event("coordination_next_day", "resident", host.revision)
        assert host.hospital.state["commitments"] == saved_commitments
        assert host.hospital.state["requests"]["dated"]["status"] == "waiting"
        assert all(m["status"] in ("available", "accepted") for m in host.coordination.state["messages"] if m["kind"] == "hospital")
    assert host.coordination.state["date"] == "2026-09-17"
    assert host.coordination.availability_for("morgan") is None
    for kind in ("companion", "return"):
        host.event("coordination_reply", "family", host.revision,
                   {"message_id": commitments[kind]["message_id"], "status": "accepted"}, commitments[kind]["actor_id"])
    assert host.hospital.state["requests"]["dated"]["status"] == "arranged"
    assert len(host.hospital.state["commitments"]) == 3
    request(host, "same-visit-next-day", visit_helpers={"driver": "alex", "companion": "morgan", "return": "alex"})
    assert len(host.hospital.state["commitments"]) == 3, "A later-day retrieval reuses still-current named agreements"
    assert host.hospital.state["requests"]["same-visit-next-day"]["status"] == "arranged"
    assert Hospital.restore(host, host.hospital.dump()).dump() == host.hospital.dump()

    host.event("coordination_next_day", "resident", host.revision)
    assert host.coordination.state["date"] == "2026-09-18"
    assert all(c["status"] == "invalidated" for c in host.hospital.state["commitments"])
    assert host.hospital.state["requests"]["dated"]["status"] == "stale"
    reject(lambda: host.hospital.recipient_reply(commitments["return"]["id"], "alex", "accepted"))

    arranged = fresh()
    request(arranged, "arranged-future")
    for commitment in arranged.hospital.state["commitments"]:
        reply(arranged, commitment, "accepted")
    run(arranged, "arranged-future")
    agreements = deepcopy(arranged.hospital.state["commitments"])
    arranged.coordination.apply("coordination_next_day", "resident")
    assert arranged.hospital.state["requests"]["arranged-future"]["status"] == "arranged"
    assert arranged.hospital.state["commitments"] == agreements, "Arranged is not attended; future agreements remain current"


def check_available_requests_only():
    def availability(host, actor, available, on_date="2026-09-17"):
        host.coordination.apply("coordination_set_availability", "family",
            {"actor_id": actor, "start_date": on_date, "end_date": on_date, "available": available}, actor)

    host = fresh()
    availability(host, "alex", False)
    request(host, "eligible-backup")
    assert len(host.hospital.state["commitments"]) == 3
    assert all(c["actor_id"] == "morgan" and c["status"] == "requested" for c in host.hospital.state["commitments"])
    driver = next(c for c in host.hospital.state["commitments"] if c["kind"] == "driver")
    reply(host, driver, "declined")
    run(host, "eligible-backup")
    assert len(host.hospital.state["commitments"]) == 3, "A decline must not re-request the known-unavailable primary"
    assert "No eligible untried helper; unresolved" in host.hospital.state["requests"]["eligible-backup"]["result"]

    for no_permission in (False, True):
        blocked = fresh()
        availability(blocked, "alex", False)
        if no_permission:
            blocked.hospital.apply("hospital_permissions", "resident", {"backup_requests": False})
        else:
            availability(blocked, "morgan", False)
        request(blocked, "uncovered")
        assert not blocked.hospital.state["commitments"]
        assert "unresolved" in blocked.hospital.state["requests"]["uncovered"]["result"]
        before = blocked.hospital.dump()
        run(blocked, "uncovered")
        assert blocked.hospital.dump() == before, "Waiting must not repeat task creation"

    pickup = fresh()
    availability(pickup, "alex", False, "2026-09-15")
    request(pickup, "pickup-backup", "prescription_refill")
    pickup.hospital.apply("hospital_publish_pharmacy", "resident", {"status": "ready"})
    run(pickup, "pickup-backup")
    assert len(pickup.hospital.state["commitments"]) == 1
    assert pickup.hospital.state["commitments"][0]["actor_id"] == "morgan"


if __name__ == "__main__":
    check_available_requests_only()
    check_visit()
    check_refill()
    check_failures()
    check_split_helpers()
    check_visit_progress_summary()
    check_dated_visit_continuity()
    print("Hospital source separation, distinct roles, privacy, pharmacy evidence, cancellation and restore checks passed.")
