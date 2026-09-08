"""Run: python3 test_coordination.py. No model, server, or external service call."""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from coordination import Coordination, PROPOSAL_FIELDS
from simulation import Household


def proposal(intent="order_supply", **values):
    result = dict.fromkeys(PROPOSAL_FIELDS, "")
    result.update(intent=intent, quantity=1, recipients=[], summary="A bounded household request.")
    result.update(values)
    return result


def setup(home):
    button = home.coordination.view("resident")["controls"]["setup"][0]
    home.coordination.apply(button["action"], "resident", button["payload"])


def request(home, identity, p, text="Please handle this household request", replacement=None):
    c = home.coordination
    c.begin(identity, text, replacement)
    c.accept(identity, p, c.version)


def run(home, identity):
    for _ in range(12):
        if not home.coordination.advance(identity):
            return
    raise AssertionError("Bounded request did not settle within 12 steps")


def reject(home, callback):
    before = (home.coordination.dump(), deepcopy(home.transport), home.week.view("resident"), home.meal.dump(), home.hospital.dump(), home.assessment.dump())
    try:
        callback()
    except ValueError:
        assert before == (home.coordination.dump(), deepcopy(home.transport), home.week.view("resident"), home.meal.dump(), home.hospital.dump(), home.assessment.dump()), "Rejected request changed facts"
    else:
        raise AssertionError("Invalid request accepted")


def own_state(home):
    state = home.coordination.dump()
    restored = Coordination.restore(home, state)
    assert restored.dump() == state
    return state


def check_supply_and_continuity():
    home = Household()
    c = home.coordination
    schema = c.context(c.begin("schema", "Please clarify my request")["request"]["id"])["proposal_schema"]
    assert schema["type"] == "object" and schema["additionalProperties"] is False
    assert set(schema["required"]) == set(PROPOSAL_FIELDS)
    c.fail("schema", "No effect")
    setup(home)
    request(home, "towels", proposal(item="paper_towels", window="morning", recipients=["alex"]))
    before_human = dict(c.state["human_interactions"])
    assert c.advance("towels")
    assert c.state["orders"][0]["status"] == "requested"
    assert c.advance("towels")
    assert c.state["orders"][0]["status"] == "acknowledged"
    assert c.advance("towels")
    assert c.state["messages"][0]["status"] == "sent" and not c.view("family", "alex")["inbox"]
    run(home, "towels")
    assert c.state["human_interactions"] == before_human, "Automatic steps counted as human work"
    assert c.view("family", "alex")["inbox"][0]["status"] == "available"
    assert not c.view("family", "morgan")["inbox"]
    c.apply("coordination_read", "family", {"message_id": "towels-alex", "actor_id": "alex"}, "alex")
    assert c.state["messages"][0]["status"] == "read"
    assert c.state["orders"][0]["status"] == "acknowledged", "Read receipt fabricated delivery"
    reject(home, lambda: c.apply("coordination_read", "family", {"message_id": "towels-alex", "actor_id": "alex"}, "morgan"))
    saved = c.dump()
    assert c.begin("towels", "Please handle this household request")["duplicate"]
    assert not c.advance("towels") and c.dump() == saved
    reject(home, lambda: c.begin("towels", "Different text"))
    request(home, "change", proposal("change_delivery", order_id="ord-towels", window="afternoon", recipients=["alex"]))
    c.advance("change")
    assert c.state["orders"][0]["window"] == "morning"
    run(home, "change")
    assert len(c.state["orders"]) == 1 and c.state["orders"][0]["window"] == "afternoon"
    request(home, "refused", proposal("change_delivery", order_id="ord-towels", window="evening"))
    run(home, "refused")
    assert c.state["orders"][0]["window"] == "afternoon" and c._get("requests", "refused")["status"] == "failed"
    c.apply("coordination_feedback", "resident", {"request_id": "change", "helped": True})
    c.apply("coordination_preferences", "resident", {"delivery_window": "afternoon"})
    c.apply("coordination_next_day", "resident", {})
    assert not c.available("alex") and not c.available("morgan")
    assert c.state["orders"][0]["status"] == "acknowledged" and c.state["feedback"]
    assert c.state["preferences"]["delivery_window"] == "afternoon"
    assert home.meal.state["day"] == c.day == home.hospital.state["day"]
    c.apply("coordination_report_delivery", "resident", {"order_id": "ord-towels", "actor_id": "resident"})
    assert c.state["orders"][0]["status"] == "delivered"
    c.apply("coordination_report_placement", "resident", {"order_id": "ord-towels", "actor_id": "resident"})
    assert c.state["orders"][0]["status"] == "placed"
    own_state(home)


def check_rejection_cancellation_and_restore():
    home = Household()
    c = home.coordination
    setup(home)
    c.begin("invalid", "Order paper towels")
    version = c.version
    reject(home, lambda: c.accept("invalid", proposal(item="paper_towels", window="morning", quantity=True), version))
    reject(home, lambda: c.accept("invalid", proposal(item="fake", window="morning"), version))
    c.apply("coordination_permissions", "resident", {"orders": False})
    reject(home, lambda: c.accept("invalid", proposal(item="paper_towels", window="morning"), version))
    c.accept("invalid", proposal(item="paper_towels", window="morning"), c.version)
    run(home, "invalid")
    assert not c.state["orders"] and c._get("requests", "invalid")["status"] == "waiting_permission"
    c.apply("coordination_cancel", "resident", {"request_id": "invalid"})
    assert not c.advance("invalid")
    c.apply("coordination_permissions", "resident", {"orders": True})
    request(home, "stop-before", proposal(item="dish_soap", window="morning"))
    c.advance("stop-before")
    c.apply("coordination_cancel", "resident", {"request_id": "stop-before"})
    assert c._get("orders", "ord-stop-before")["status"] == "cancelled"
    request(home, "stop-after", proposal(item="dish_soap", window="morning"))
    c.advance("stop-after"); c.advance("stop-after")
    c.apply("coordination_cancel", "resident", {"request_id": "stop-after"})
    assert c._get("orders", "ord-stop-after")["status"] == "acknowledged"
    request(home, "cancel-order", proposal("cancel_order", order_id="ord-stop-after"))
    run(home, "cancel-order")
    assert c._get("orders", "ord-stop-after")["status"] == "cancelled"
    request(home, "stock", proposal(item="laundry_detergent", window="morning"))
    run(home, "stock")
    assert c._get("requests", "stock")["service"] == "refused"
    c.begin("correct", "Actually dish soap", "stock")
    assert c.context("correct")["recent_requests"][-1]["id"] == "stock"
    interrupted = c.dump()
    home.coordination = c = Coordination.restore(home, interrupted)
    assert c._get("requests", "correct")["status"] == "failed"
    assert not c._get("requests", "correct")["effects"] and "interrupted" in c._get("requests", "correct")["error"]
    assert c.state["orders"] == interrupted["orders"] and interrupted["requests"][-1]["status"] == "interpreting"
    state = own_state(home)
    previous = deepcopy(state)
    previous["shared"].pop("support")
    migrated = Coordination.restore(home, previous).dump()
    assert migrated == state and "support" not in previous["shared"], "Migration changed effects or mutated the saved input"
    old_clock = deepcopy(previous)
    old_clock.pop("clock_minute"); old_clock.pop("reminders")
    for entry in old_clock["history"]:
        entry.pop("minute")
    migrated_clock = Coordination.restore(home, old_clock).dump()
    assert migrated_clock["clock_minute"] == 540 and not migrated_clock["reminders"]
    assert all(entry["minute"] is None for entry in migrated_clock["history"])
    assert migrated_clock["orders"] == state["orders"] and migrated_clock["requests"] == state["requests"]
    assert "clock_minute" not in old_clock and "minute" not in old_clock["history"][0]
    mismatched = deepcopy(previous)
    mismatched["shared"]["appointment"]["time"] = "23:59"
    try:
        Coordination.restore(home, mismatched)
    except ValueError:
        pass
    else:
        raise AssertionError("Support migration hid an unrelated shared-calendar mismatch")
    for mutate in (
        lambda d: d["orders"][0].update(status="placed", delivered_by="", placed_by=""),
        lambda d: d["actors"]["alex"].update(day=0),
        lambda d: d["requests"][0].update(phase=9),
        lambda d: d["permissions"].update(spend_cap=float("nan")),
        lambda d: d["requests"][1].update(phase=0),
        lambda d: d["requests"][1]["proposal"].update(item="invented_product"),
    ):
        bad = deepcopy(state); mutate(bad)
        try:
            Coordination.restore(home, bad)
        except ValueError:
            pass
        else:
            raise AssertionError("Contradictory saved state accepted")


def check_reported_order_summaries():
    from persistence import load_household, save_household
    home = Household()
    c = home.coordination
    setup(home)
    request(home, "soap", proposal(item="dish_soap", window="morning", recipients=["alex"]))
    run(home, "soap")
    request(home, "soap-change", proposal("change_delivery", order_id="ord-soap", window="afternoon", recipients=["alex"]))
    run(home, "soap-change")
    request(home, "soap-refused", proposal("change_delivery", order_id="ord-soap", window="evening"))
    run(home, "soap-refused")
    statuses = {r["id"]: r["status"] for r in c.state["requests"]}
    assert "Physical delivery and placement are unreported" in c._get("requests", "soap")["summary"]
    with TemporaryDirectory() as directory:
        path = Path(directory) / "reported-order.json"
        for action, state, evidence in (("coordination_report_delivery", "delivered", "placement remains unreported"),
                                         ("coordination_report_placement", "placed", "placing the delivered supply in storage")):
            reject(home, lambda: c.apply(action, "family", {"order_id": "ord-soap", "actor_id": "morgan"}, "morgan"))
            c.apply(action, "family", {"order_id": "ord-soap", "actor_id": "alex"}, "alex")
            assert c._get("orders", "ord-soap")["status"] == state
            for record in c.state["requests"]:
                assert evidence in record["summary"] and record["status"] == statuses[record["id"]]
            refused = c._get("requests", "soap-refused")
            assert refused["error"] and refused["summary"].startswith(refused["error"])
            assert "Physical delivery and placement are unreported" not in c._get("requests", "soap")["summary"]
            save_household(home, path)
            restored = load_household(path)
            assert restored.coordination.state["requests"] == c.state["requests"]
            assert restored.coordination.state["orders"] == c.state["orders"]


def check_named_travel_and_meal():
    home = Household()
    c = home.coordination
    setup(home)
    request(home, "appointment", proposal("change_appointment", appointment_choice="friday_1000", helper="alex", recipients=["morgan"]))
    run(home, "appointment")
    assert home.appointment["date"] == "2026-09-18" and home.transport["status"] != "confirmed"
    assert "Private follow-up" not in json.dumps(c.context("appointment"))
    c.apply("coordination_read", "family", {"message_id": "appointment-alex", "actor_id": "alex"}, "alex")
    assert home.transport["status"] != "confirmed"
    context = c.reply_context("alex")
    assert all(m["recipient"] == "alex" for m in context["inbox"])
    reject(home, lambda: c.apply_reply("wrong", "morgan", "yes", {"decisions": [{"message_id": "appointment-alex", "status": "accepted"}], "question": ""}, c.version))
    c.apply_reply("clarify", "alex", "yes", {"decisions": [], "question": "Do you mean both travel legs?"}, c.version)
    assert home.transport["status"] != "confirmed"
    answer = {"decisions": [{"message_id": "appointment-alex", "status": "accepted"}], "question": ""}
    c.apply_reply("accept", "alex", "I can provide both trips", answer, c.version)
    saved = c.dump()
    c.apply_reply("accept", "alex", "I can provide both trips", answer, 0)
    assert c.dump() == saved and home.transport["status"] == "confirmed"
    assert home.week.return_status == "confirmed"
    own_state(home)
    request(home, "carry", proposal("carry_help", helper="morgan"))
    run(home, "carry")
    c.apply_reply("carry-accept", "morgan", "I can carry the meal", {"decisions": [
        {"message_id": "carry-morgan", "status": "accepted"}], "question": ""}, c.version)
    assert c._get("requests", "carry")["status"] == "waiting_physical"
    home.meal.apply("meal_start", "resident", {})
    for _ in range(200):
        if not home.meal.can_tick():
            break
        home.meal.apply("meal_tick", "resident", {"episode_id": home.meal.state["episode_id"], "step": home.meal.state["step"]})
    assert c._get("requests", "carry")["status"] == "completed"
    assert c._get("messages", "carry-morgan")["completed_day"] == c.day
    state = own_state(home)
    legacy = deepcopy(state)
    legacy.pop("clock_minute"); legacy.pop("reminders")
    for entry in legacy["history"]:
        entry.pop("minute")
    next(r for r in legacy["requests"] if r["id"] == "carry")["effects"].remove("helper_accepted")
    migrated = Coordination.restore(home, legacy).dump()
    assert next(r for r in migrated["requests"] if r["id"] == "carry")["effects"] == ["request_sent", "helper_accepted", "physical_placement_reported"]
    assert migrated["messages"] == state["messages"] and migrated["replies"] == state["replies"]
    legacy["replies"] = [r for r in legacy["replies"] if r["id"] != "carry-accept"]
    try:
        Coordination.restore(home, legacy)
    except ValueError:
        pass
    else:
        raise AssertionError("Legacy migration inferred acceptance from physical completion alone")


def check_hospital_and_assessment():
    from hospital import PERMISSIONS
    home = Household()
    c = home.coordination
    setup(home)
    home.hospital.apply("hospital_permissions", "resident", dict.fromkeys(PERMISSIONS, True))
    request(home, "hospital", proposal("hospital_coordination", item="visit-001", helper="alex"))
    run(home, "hospital")
    messages = c.state["messages"]
    assert len(messages) == 3 and {m["metadata"]["kind"] for m in messages} == {"driver", "companion", "return"}
    assert "Private supplied" not in json.dumps(c.context("hospital"))
    assert all(m["recipient"] == "alex" for m in messages)
    by_kind = {m["metadata"]["kind"]: m for m in messages}
    decisions = [{"message_id": by_kind[kind]["id"], "status": status} for kind, status in (("driver", "accepted"), ("companion", "declined"))]
    original = home.hospital.recipient_reply
    calls = []
    def fail_second(*args):
        calls.append(args)
        if len(calls) == 2:
            raise ValueError("Supplied commitment changed")
        return original(*args)
    with patch.object(home.hospital, "recipient_reply", side_effect=fail_second):
        reject(home, lambda: c.apply_reply("atomic", "alex", "I can drive but cannot stay", {"decisions": decisions, "question": ""}, c.version))
    c.apply_reply("hospital-alex", "alex", "I can drive but cannot stay", {"decisions": decisions, "question": ""}, c.version)
    assert c._get("messages", by_kind["return"]["id"])["status"] == "available", "Unmentioned return was accepted"
    run(home, "hospital")
    companion = next(m for m in c.state["messages"] if m["recipient"] == "morgan")
    assert companion["metadata"]["kind"] == "companion"
    c.apply_reply("hospital-morgan", "morgan", "I can accompany", {"decisions": [{"message_id": companion["id"], "status": "accepted"}], "question": ""}, c.version)
    c.apply_reply("hospital-return", "alex", "I can do the return too", {"decisions": [{"message_id": by_kind["return"]["id"], "status": "accepted"}], "question": ""}, c.version)
    run(home, "hospital")
    assert c._get("requests", "hospital")["status"] == "completed"
    own_state(home)


def check_remote_availability():
    home = Household()
    home.event("week_select_profile", "resident", home.revision, {"id": "remote"})
    c = home.coordination
    assert not c.available("alex") and not c.available("morgan")
    setup(home)
    request(home, "remote-carry", proposal("carry_help", helper="alex"))
    run(home, "remote-carry")
    reject(home, lambda: c.apply_reply("remote-accept", "alex", "yes", {"decisions": [{"message_id": "remote-carry-alex", "status": "accepted"}], "question": ""}, c.version))
    assert home.meal.help_context()["help"]["status"] == "requested"
    assert "not aliases" in c.view("resident")["notice"]
    room = home.assessment.view("resident")["rooms"][0]["id"]
    request(home, "review", proposal("assess_home", room_id=room, strategy="keep"))
    run(home, "review")
    assert c._get("requests", "review")["status"] == "completed" and not home.assessment.state["selections"]
    assert home.assessment.view("resident")["costs"]["total_cents"] is None
    own_state(home)


def check_product_selection():
    home = Household()
    c, assessment = home.coordination, home.assessment
    c.begin("product", "Compare a cart for the bedroom using our household constraints")
    context = c.context("product")
    assert context["assessment"]["strategy"] == "keep" and not context["assessment"]["candidates"]
    source = next(item for item in context["assessment"]["evaluated_candidates"] if item["id"] == "ikea_nissafors")
    assert source["evaluation"]["status"] == "unknown"
    assert set(context["intent_fields"]["assess_home"]) == {"item", "room_id", "strategy"}
    p = proposal("assess_home", item=source["id"], room_id="Bedroom", strategy="replace")
    fields = {"budget_cents": 10000, "space": {"room_id": "Bedroom", "basis": "measured",
        "width_in": 50, "depth_in": 50, "height_in": 50}, "preferences": {
        "prefer_existing": False, "allow_assembly": True, "allow_drilling": True, "notes": ""}, "setup": "family"}

    def constraints(value):
        home.event("assessment_constraints", "resident", home.revision, deepcopy(value))

    # The same candidate becomes invalid under a lower budget, too little space,
    # or a stated preference. Rejections leave every domain unchanged.
    version = c.version
    low = deepcopy(fields); low["budget_cents"] = source["published_price_cents"] - 1
    constraints(low)
    reject(home, lambda: c.accept("product", p, version))
    assert assessment.evaluate(p["item"], 1, "Bedroom")["checks"]["budget"]["status"] == "conflict"
    reject(home, lambda: c.accept("product", p, c.version))
    narrow = deepcopy(fields); narrow["space"]["width_in"] = 1
    constraints(narrow)
    reject(home, lambda: c.accept("product", p, c.version))
    for preference in ("allow_assembly", "prefer_existing"):
        restricted = deepcopy(fields)
        restricted["preferences"][preference] = preference == "prefer_existing"
        constraints(restricted)
        reject(home, lambda: c.accept("product", p, c.version))
    constraints(fields)
    evaluation = assessment.evaluate(p["item"], 1, "Bedroom")
    assert evaluation["checks"]["space"]["status"] == "suitable_to_review"
    assert evaluation["checks"]["setup"]["status"] == "unknown" and evaluation["total_cents"] is None
    reject(home, lambda: c.accept("product", dict(p, item="invented-cart"), c.version))
    for strategy in ("keep", "relocate", "adapt"):
        reject(home, lambda strategy=strategy: c.accept("product", dict(p, strategy=strategy), c.version))
    c.accept("product", p, c.version)
    assert not assessment.state["selections"], "A proposal alone changed the draft"

    original = assessment.apply
    def fail_add(action, *args, **kwargs):
        if action == "assessment_add":
            raise ValueError("Selection changed during draft preparation")
        return original(action, *args, **kwargs)
    with patch.object(assessment, "apply", side_effect=fail_add):
        reject(home, lambda: c.advance("product"))
    assert assessment.state["strategy"] == "keep", "A failed selection left a partial strategy change"
    run(home, "product")
    record = c._get("requests", "product")
    assert record["status"] == "completed" and len(assessment.state["selections"]) == 1
    assert "$29.99" in record["summary"] and "unverified" in record["summary"] and "No purchase" in record["summary"]
    assert "not currently accepted" in record["summary"] and not c.state["orders"]
    assert not c.state["setup_done"], "Preparing a review should not grant permissions"

    # A named setup reply changes only that scoped responsibility. An identical
    # later review preserves it; a different quantity needs a new agreement.
    scope = assessment.view("family", "alex")["setup_scope"]
    home.event("assessment_setup_reply", "family", home.revision, {"accepted": True, "scope": scope}, actor_id="alex")
    accepted = deepcopy(assessment.state["setup_acceptance"])
    assert assessment.evaluate(p["item"], 1, "Bedroom")["checks"]["setup"]["status"] == "suitable_to_review"
    request(home, "same-product", p)
    run(home, "same-product")
    assert len(assessment.state["selections"]) == 1 and assessment.state["setup_acceptance"] == accepted
    request(home, "two-products", dict(p, quantity=2))
    run(home, "two-products")
    assert len(assessment.state["selections"]) == 1 and assessment.state["selections"][0]["quantity"] == 2
    assert assessment.state["setup_acceptance"] is None
    assert "$59.98" in c._get("requests", "two-products")["summary"]
    assert assessment.evaluate(p["item"], 2, "Bedroom")["checks"]["setup"]["status"] == "unknown"

    # Recheck current constraints before each bounded effect, not only at model
    # acceptance. No update can send a now-conflicting or removed selection.
    request(home, "changed-budget", p)
    assert c.advance("changed-budget")
    constraints(low)
    reject(home, lambda: c.advance("changed-budget"))
    assert c._get("requests", "changed-budget")["effects"] == ["request_sent"]
    constraints(fields)
    home.event("assessment_remove", "resident", home.revision, {"option_id": p["item"]})
    reject(home, lambda: c.advance("changed-budget"))
    own_state(home)


def hospital_household(identity="visit", recipients=None):
    from hospital import PERMISSIONS
    home = Household()
    setup(home)
    home.hospital.apply("hospital_permissions", "resident", dict.fromkeys(PERMISSIONS, True))
    request(home, identity, proposal("hospital_coordination", item="visit-001", helper="alex", recipients=recipients or []))
    run(home, identity)
    return home


def check_hospital_information():
    home = hospital_household(recipients=["morgan"])
    c = home.coordination
    information = [m for m in c.state["messages"] if m["kind"] == "information"]
    duties = [m for m in c.state["messages"] if m["kind"] == "hospital"]
    assert len(information) == 1 and information[0]["recipient"] == "morgan" and information[0]["status"] == "available"
    assert "version 1" in information[0]["body"] and "Private supplied" not in information[0]["body"]
    assert len(duties) == 3 and all(m["recipient"] == "alex" for m in duties)
    c.apply_reply("all-three", "alex", "I can drive, accompany, and bring them home",
        {"decisions": [{"message_id": m["id"], "status": "accepted"} for m in duties], "question": ""}, c.version)
    run(home, "visit")
    assert c._get("requests", "visit")["status"] == "completed"
    for _ in range(2):
        c.resume_domain_request("visit")
        run(home, "visit")
    assert len([m for m in c.state["messages"] if m["kind"] == "information"]) == 1
    home.hospital.apply("hospital_publish_visit", "resident", {"fixture": "time_location_change"})
    assert "South reception" not in information[0]["body"]
    request(home, "new-notice", proposal("hospital_coordination", item="visit-001", helper="alex", recipients=["morgan"]))
    run(home, "new-notice")
    updates = [m for m in c.state["messages"] if m["kind"] == "information"]
    assert len(updates) == 2 and "version 2" in updates[-1]["body"] and "South reception" in updates[-1]["body"]
    own_state(home)

    blocked = Household()
    from hospital import PERMISSIONS
    blocked.hospital.apply("hospital_permissions", "resident", dict.fromkeys(PERMISSIONS, True))
    request(blocked, "permission", proposal("hospital_coordination", item="visit-001", helper="alex", recipients=["morgan"]))
    run(blocked, "permission")
    assert not any(m["kind"] == "information" for m in blocked.coordination.state["messages"])
    assert blocked.coordination._get("requests", "permission")["status"] == "waiting_permission"
    setup(blocked)
    run(blocked, "permission")
    assert len([m for m in blocked.coordination.state["messages"] if m["kind"] == "information"]) == 1


def check_split_hospital_helpers():
    from hospital import PERMISSIONS
    home = Household()
    c = home.coordination
    setup(home)
    home.hospital.apply("hospital_permissions", "resident", dict.fromkeys(PERMISSIONS, True))
    c.begin("split", "Alex can drive there and home; ask Morgan to accompany")
    roles = {"driver": "alex", "companion": "morgan", "return": "alex"}
    p = proposal("hospital_coordination", item="visit-001", visit_helpers=roles)
    schema = c.context("split")["proposal_schema"]
    assert "visit_helpers" in schema["properties"] and "visit_helpers" not in schema["required"]
    for values in (dict(p, visit_helpers={"driver": "alex"}), dict(p, visit_helpers=dict(roles, companion="stranger")),
                   dict(p, visit_helpers=dict(roles, driver="")), dict(p, visit_helpers="alex"),
                   proposal(item="dish_soap", window="morning", visit_helpers=roles)):
        reject(home, lambda values=values: c.accept("split", values, c.version))
    c.accept("split", p, c.version)
    assert c._get("requests", "split")["proposal"]["visit_helpers"] == roles
    run(home, "split")
    messages = [m for m in c.state["messages"] if m["kind"] == "hospital"]
    assert {m["metadata"]["kind"]: m["recipient"] for m in messages} == roles
    for actor in ("alex", "morgan"):
        c.apply_reply("split-" + actor, actor, "I accept my listed duties", {"decisions": [
            {"message_id": m["id"], "status": "accepted"} for m in messages if m["recipient"] == actor], "question": ""}, c.version)
    run(home, "split")
    assert c._get("requests", "split")["status"] == "completed"
    assert c.context("split")["hospital"]["current_visit_helpers"] == roles
    own_state(home)
    request(home, "fallback", proposal("hospital_coordination", item="visit-001", helper="alex",
        visit_helpers={"driver": "", "companion": "morgan", "return": ""}))
    run(home, "fallback")
    assert home.hospital.state["requests"]["fallback"]["helpers"] == roles
    own_state(home)


def check_agreed_reminders():
    home = hospital_household()
    c = home.coordination
    duties = {m["metadata"]["kind"]: m for m in c.state["messages"]}
    c.apply("coordination_schedule_reminder", "resident", {"message_id": duties["driver"]["id"], "hours": 1})
    request(home, "remind-companion", proposal("schedule_reminder", item=duties["companion"]["id"], quantity=1))
    run(home, "remind-companion")
    c.apply("coordination_schedule_reminder", "resident", {"message_id": duties["return"]["id"], "hours": 2})
    saved = c.dump()
    c.apply("coordination_schedule_reminder", "resident", {"message_id": duties["driver"]["id"], "hours": 1})
    assert c.dump() == saved, "Duplicate scheduling changed its due event or counted another intervention"
    reject(home, lambda: c.apply("coordination_schedule_reminder", "family", {"message_id": duties["driver"]["id"], "hours": 1}, "alex"))
    human = deepcopy(c.state["human_interactions"])
    c.apply("coordination_advance_clock", "resident", {"minutes": 59})
    assert all(r["status"] == "scheduled" for r in c.state["reminders"])
    c.apply("coordination_advance_clock", "resident", {"minutes": 1})
    assert [r["status"] for r in c.state["reminders"]] == ["issued", "issued", "scheduled"]
    assert all(r["issued_minute"] == 600 for r in c.state["reminders"][:2])
    assert c.state["human_interactions"] == human and c.state["history"][-1]["minute"] == 600
    home.coordination = Coordination.restore(home, c.dump())
    c = home.coordination
    c.apply("coordination_advance_clock", "resident", {"minutes": 1})
    assert len([m for m in c.state["messages"] if m["kind"] == "information"]) == 2, "Reload repeated a due reminder"
    c.apply_reply("partial", "alex", "I can drive but cannot stay", {"decisions": [
        {"message_id": duties["driver"]["id"], "status": "accepted"},
        {"message_id": duties["companion"]["id"], "status": "declined"}], "question": ""}, c.version)
    assert [r["status"] for r in c.state["reminders"]] == ["cancelled", "cancelled", "scheduled"]
    assert all(c._get("messages", r["receipt_id"])["status"] == "cancelled" for r in c.state["reminders"][:2])
    assert c._get("messages", duties["return"]["id"])["status"] == "available"
    c.apply("coordination_cancel_reminder", "resident", {"reminder_id": "rem-3"})
    c.apply("coordination_advance_clock", "resident", {"minutes": 60})
    assert len([m for m in c.state["messages"] if m["kind"] == "information"]) == 2
    assert c._get("messages", duties["return"]["id"])["status"] == "available", "Cancelling a reminder cancelled its duty"
    c.apply("coordination_schedule_reminder", "resident", {"message_id": duties["return"]["id"], "hours": 1})
    c.apply("coordination_permissions", "resident", {"notify": False})
    assert c.state["reminders"][-1]["status"] == "cancelled"
    request(home, "permission-reminder", proposal("schedule_reminder", item=duties["return"]["id"], quantity=1))
    run(home, "permission-reminder")
    assert c._get("requests", "permission-reminder")["status"] == "waiting_permission"
    c.apply("coordination_permissions", "resident", {"notify": True})
    run(home, "permission-reminder")
    assert c.state["reminders"][-1]["status"] == "scheduled" and c.state["reminders"][-2]["status"] == "cancelled"
    state = own_state(home)
    for mutate in (lambda d: d.update(clock_minute=True),
                   lambda d: d["reminders"][-1].update(due_minute=700),
                   lambda d: d["reminders"][-1].update(status="issued", receipt_id="missing"),
                   lambda d: d["history"][-1].pop("minute")):
        bad = deepcopy(state); mutate(bad)
        try:
            Coordination.restore(home, bad)
        except ValueError:
            pass
        else:
            raise AssertionError("Contradictory reminder or clock evidence restored")
    c.apply("coordination_next_day", "resident", {})
    assert all(r["status"] == "cancelled" for r in c.state["reminders"])
    assert c.state["clock_minute"] == 540 and not c.available("alex")
    own_state(home)


def check_memory_and_dated_availability():
    from persistence import save_household, load_household

    home = Household()
    c = home.coordination
    original_permissions = deepcopy(c.state["permissions"])
    sentinel = "Private preference report for continuity verification only."
    request(home, "remember", proposal("remember_preference", summary=sentinel,
        memory={"key": "messages", "value": "detailed", "audience": ["resident", "alex"]}), text=sentinel)
    run(home, "remember")
    memory = c.view("resident")["preference_memory"]["messages"]
    assert memory["source"]["request_id"] == "remember" and memory["source"]["actor_id"] == "resident"
    assert memory["source"]["date"] == "2026-09-15" and memory["status"] == "current"
    assert c.view("family", "alex")["preferences"]["messages"] == "detailed"
    assert "messages" not in c.view("family", "morgan")["preferences"]
    assert "messages" not in c.reply_context("morgan")["preference_memory"]
    assert sentinel not in json.dumps(c.model_view("family", "morgan"))
    assert c.state["permissions"] == original_permissions and not c.state["messages"] and not c.state["orders"]
    own_state(home)

    c.apply("coordination_remember_preference", "resident", {"key": "messages", "value": "brief", "audience": ["resident"]})
    unchanged = c.dump()
    c.apply("coordination_remember_preference", "resident", {"key": "messages", "value": "brief", "audience": ["resident"]})
    assert c.dump() == unchanged, "An equal memory edit renewed source, history or context"
    assert c.state["preference_memory"]["messages"]["source"]["request_id"] == ""
    assert "messages" not in c.model_view("family", "alex")["preferences"]
    assert "memory" not in c.context("remember")["request"]["proposal"]
    request(home, "forget", proposal("forget_preference", memory={"key": "messages", "value": None, "audience": []}))
    run(home, "forget")
    assert c.state["preferences"]["messages"] is None
    assert c.state["preference_memory"]["messages"]["status"] == "removed"
    assert sentinel not in json.dumps(c.context("forget"))
    assert sentinel not in json.dumps(c.model_view("resident"))
    assert "memory" not in c.model_view("resident")["requests"][0]["proposal"]
    assert sentinel not in json.dumps(c.dump()) and sentinel not in json.dumps(c.view("resident"))
    retired = c._get("requests", "remember")
    assert retired["memory_redacted"] and len(retired["source_digest"]) == 64
    assert retired["proposal"]["memory"]["value"] is None and retired["effects"] == ["preference_recorded"]
    # A source digest preserves duplicate recognition after the private text is erased.
    assert c.begin("remember", sentinel)["duplicate"] and not c.advance("remember")
    assert c.state["preferences"]["messages"] is None
    c.apply("coordination_permissions", "resident", {"calendar": True, "notify": True, "helper_requests": True})
    assert c.state["preferences"]["messages"] is None, "Unrelated permission edits resurrected removed memory"
    reject(home, lambda: c.apply("coordination_remember_preference", "family",
        {"key": "routine", "value": "try", "audience": ["resident", "alex"]}, "alex"))
    reject(home, lambda: c.apply("coordination_remember_preference", "resident",
        {"key": "routine", "value": "try", "audience": ["alex"]}))
    reject(home, lambda: c.apply("coordination_remember_preference", "resident",
        {"key": "orders", "value": "allowed", "audience": ["resident"]}))

    def report(actor, start, end, available):
        c.apply("coordination_set_availability", "family", {"actor_id": actor, "start_date": start,
                "end_date": end, "available": available}, actor)

    assert c.availability_for("alex", "2026-09-18") is None, "Today's fixture was treated as future availability"
    report("alex", "2026-09-16", "2026-09-18", True)
    report("alex", "2026-09-17", "2026-09-17", False)
    report("morgan", "2026-09-16", "2026-09-18", False)
    assert [c.availability_for("alex", f"2026-09-{day}") for day in (16, 17, 18, 19)] == [True, False, True, None]
    assert not c.available("morgan", "2026-09-18")
    reject(home, lambda: c.apply("coordination_set_availability", "family",
        {"actor_id": "alex", "start_date": "2026-09-18", "end_date": "2026-09-18", "available": True}, "morgan"))
    reject(home, lambda: report("alex", "2026-09-20", "2026-09-19", True))
    reject(home, lambda: report("alex", "20260920", "2026-09-20", True))
    reject(home, lambda: report("alex", "2026-09-20", "2026-09-20", 1))

    request(home, "future-travel", proposal("change_appointment", appointment_choice="friday_1000", helper="alex"))
    run(home, "future-travel")
    duty = c._get("messages", "future-travel-alex")
    c.apply("coordination_reply", "family", {"message_id": duty["id"], "actor_id": "alex", "status": "accepted"}, "alex")
    c.apply("coordination_next_day", "resident", {})
    assert c.available("alex") and not c.available("morgan")
    assert duty["status"] == "accepted" and home.transport["status"] == "confirmed"
    assert c.state["preferences"]["messages"] is None
    c.apply("coordination_next_day", "resident", {})
    assert not c.available("alex") and c.available("alex", "2026-09-18")
    assert duty["status"] == "accepted", "Absence today cancelled an accepted duty tomorrow"

    with TemporaryDirectory() as directory:
        path = Path(directory) / "continuity.json"
        save_household(home, path)
        assert sentinel not in path.read_text(), "Forgotten source text survived in the saved snapshot"
        restored = load_household(path)
        assert restored.coordination.dump() == c.dump(), "Restart changed memory, duties or evidence"
        assert not restored.coordination.advance("remember")
        assert restored.coordination.state["preferences"]["messages"] is None
    second = Household()
    assert not second.coordination.state["preference_memory"] and not second.coordination.state["availability"]

    report("alex", "2026-09-18", "2026-09-18", False)
    assert duty["status"] == "declined" and home.transport["status"] != "confirmed"
    c.apply("coordination_remove_availability", "family",
        {"actor_id": "alex", "start_date": "2026-09-18", "end_date": "2026-09-18"}, "alex")
    assert c.availability_for("alex", "2026-09-18") is None and duty["status"] == "declined"
    state = own_state(home)
    for mutate in (
        lambda d: d["preference_memory"]["messages"]["source"].update(actor_id="morgan"),
        lambda d: d["preference_memory"]["messages"].update(value="detailed"),
        lambda d: d["preference_memory"]["messages"].update(audience=["resident", "alex"]),
        lambda d: d.update(memory_cutoff=999),
        lambda d: d.update(memory_revision=True),
        lambda d: d["availability"].append(deepcopy(d["availability"][0])),
        lambda d: d["availability"][0].update(available=1),
        lambda d: d["requests"][0].update(source_digest="not-a-digest"),
        lambda d: d["requests"][0]["proposal"]["memory"].update(value="detailed"),
    ):
        bad = deepcopy(state); mutate(bad)
        try:
            Coordination.restore(home, bad)
        except ValueError:
            pass
        else:
            raise AssertionError("Malformed or contradictory continuity state restored")


def check_proactive_request_provenance():
    home = Household(save_path=None)
    c = home.coordination
    home.begin_coordination("auto-v2", "Automatic check of a changed hospital notice.", home.revision, initiated_by="coordinator")
    assert c.state["human_interactions"] == dict.fromkeys(("resident", "alex", "morgan"), 0)
    assert c.state["history"][-1]["actor"] == "coordinator"
    assert c.state["history"][-1]["event"] == "proactive_request"
    before = c.dump()
    assert home.begin_coordination("auto-v2", "Automatic check of a changed hospital notice.", home.revision, initiated_by="coordinator")["duplicate"]
    assert c.dump() == before
    reject(home, lambda: c.begin("invalid-source", "Request", initiated_by="alex"))
    reject(home, lambda: home.begin_coordination("invalid-source", "Request", home.revision, initiated_by=True))
    home.begin_coordination("resident", "Please arrange the visit.", home.revision)
    assert c.state["human_interactions"]["resident"] == 1
    assert c.state["history"][-1]["actor"] == "resident" and c.state["history"][-1]["event"] == "request"


if __name__ == "__main__":
    check_proactive_request_provenance()
    check_supply_and_continuity()
    check_rejection_cancellation_and_restore()
    check_reported_order_summaries()
    check_named_travel_and_meal()
    check_hospital_and_assessment()
    check_remote_availability()
    check_product_selection()
    check_hospital_information()
    check_split_hospital_helpers()
    check_agreed_reminders()
    check_memory_and_dated_availability()
    print("PASS coordination: bounded effects, named replies, scoped memory/corrections/removal, dated availability, restart recovery, and reminders without repeat delivery.")
