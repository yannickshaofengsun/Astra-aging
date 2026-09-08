"""Run with python3 -B test_assessment.py; no services or transactions are used."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

import assessment
from assessment import Assessment
from real_world import match_options


def check():
    host = SimpleNamespace(home={"id": "demo", "rooms": [
        {"label": "Bedroom", "use": "bedroom"}, {"label": "Bathroom", "use": "bathroom"}],
        "confirmed": [], "assumptions": [], "unknowns": []})
    draft = Assessment(host)
    add = {"option_id": "ikea_nissafors", "quantity": 2, "room_id": "Bedroom"}
    catalog_before = match_options("home_storage")
    assert draft.view("resident")["strategy"] == "keep" and not draft.view("resident")["candidates"]
    assert "assessment_add" not in draft.view("resident")["controls"]["actions"]
    try:
        draft.apply("assessment_add", "resident", add)
    except ValueError:
        pass
    else:
        raise AssertionError("Keep strategy must not add a purchase")
    draft.apply("assessment_existing", "resident", {"description": "Reading basket", "current_room_id": "Bedroom", "target_room_id": "Bathroom"})
    kept = draft.view("resident")["existing_placement"]
    assert kept["before"] == kept["after"] == {"home_id": "demo", "room_id": "Bedroom"}
    for strategy in ("relocate", "adapt"):
        draft.apply("assessment_strategy", "resident", {"strategy": strategy})
        planned = draft.view("resident")
        assert planned["existing_placement"]["after"] == {"home_id": "demo", "room_id": "Bathroom"}
        assert planned["existing_placement"]["status"] == "needs_checks"
        assert planned["existing_placement"]["condition"] == "unknown" and planned["existing_placement"]["accepted"] is False
        assert not planned["candidates"] and planned["costs"]["total_cents"] is None
        assert not {"delivery", "removal"} & {step["id"] for step in planned["timeline"]}
    draft.apply("assessment_strategy", "resident", {"strategy": "replace"})
    assert draft.view("resident")["existing_placement"]["after"] is None
    draft.apply("assessment_observation", "resident", {"text": "I want my reading supplies within reach."})
    draft.apply("assessment_add", "resident", add)
    view = draft.view("resident")
    item, costs = view["selections"][0], view["costs"]
    assert item["item_subtotal_cents"] == 5998 == costs["known_item_subtotal_cents"] == costs["item_subtotal_cents"]
    assert costs["unknown_item_count"] == 0 and not costs["partial_known_subtotal"]
    assert all(costs[key] is None for key in ("delivery_cents", "setup_cents", "removal_cents", "tax_cents", "assessment_cents", "one_time_total_cents", "total_cents", "recurring_cents", "recurring_period"))
    assert item["source_dimensions"] == {"dimensions_in": catalog_before["options"][0]["dimensions_in"]}
    assert item["placement"]["before"] is None and item["placement"]["after"] == {"home_id": "demo", "room_id": "Bedroom"}
    assert item["condition"] == "unknown" and item["fit_status"] == item["placement"]["status"] == "needs_checks"
    assert item["responsibility"]["accepted"] is False
    assert all(step["date"] is None and step["accepted"] is False for step in view["timeline"])
    family_controls = draft.view("family")["controls"]
    assert family_controls["can_edit"] is False and family_controls["actions"] == []
    assert family_controls["can_edit_constraints"] is False and family_controls["can_reply_setup"] is False

    # Invalid requests must leave every prior selection and the observation intact.
    for action, role, payload in (
        ("assessment_add", "resident", add),
        ("assessment_add", "resident", {**add, "quantity": True}),
        ("assessment_add", "resident", {**add, "quantity": 0}),
        ("assessment_add", "resident", {**add, "quantity": 11}),
        ("assessment_add", "resident", {**add, "room_id": "Invented room"}),
        ("assessment_add", "resident", {**add, "option_id": "taskrabbit_assembly"}),
        ("assessment_add", "resident", {**add, "option_id": "oxo_jar_opener_1173600"}),
        ("assessment_observation", "resident", {"text": "x" * 501}),
        ("assessment_need", "resident", {"need": True}),
        ("assessment_need", "resident", {"need": "lighting", "confirmed": True}),
        ("assessment_remove", "resident", {"option_id": "missing"}),
        ("assessment_remove", "family", {"option_id": add["option_id"]}),
        ("assessment_strategy", "family", {"strategy": "keep"}),
        ("assessment_strategy", "resident", {"strategy": True}),
        ("assessment_strategy", "resident", {"strategy": "buy"}),
        ("assessment_existing", "resident", {"description": " ", "current_room_id": "Bedroom", "target_room_id": "Bathroom"}),
        ("assessment_existing", "resident", {"description": "x" * 201, "current_room_id": "Bedroom", "target_room_id": "Bathroom"}),
        ("assessment_existing", "resident", {"description": "Basket", "current_room_id": "missing", "target_room_id": "Bathroom"}),
    ):
        before = draft.dump()
        try:
            draft.apply(action, role, payload)
        except ValueError:
            pass
        else:
            raise AssertionError((action, payload))
        assert draft.dump() == before

    draft.apply("assessment_need", "resident", {"need": "bathroom_support"})
    bathroom = draft.view("resident")["candidates"][0]
    draft.apply("assessment_add", "resident", {"option_id": bathroom["id"], "quantity": 1, "room_id": "Bathroom"})
    assert draft.view("family")["selections"][1]["fit_status"] == "assessment_required"
    assert len(draft.dump()["selections"]) == 2
    assert "organize everyday items" in draft.view("resident")["selections"][0]["rationale"]
    assert "bathroom" not in draft.view("resident")["selections"][0]["rationale"]
    saved = draft.dump()
    assert Assessment.restore(host, saved).dump() == saved
    view["selections"][0]["source"]["dimensions_in"]["width"] = 0
    assert match_options("home_storage") == catalog_before
    assert draft.view("resident")["selections"][0]["source_dimensions"]["dimensions_in"]["width"] == 11.75

    # Keeping the current item pauses product choices without deleting or charging them.
    chosen = draft.dump()["selections"]
    draft.apply("assessment_strategy", "resident", {"strategy": "keep"})
    kept = draft.view("resident")
    assert draft.dump()["selections"] == chosen
    assert kept["existing_placement"]["before"] == kept["existing_placement"]["after"]
    assert all(not item["active"] and item["placement"]["after"] is None for item in kept["selections"])
    assert kept["costs"]["known_item_subtotal_cents"] == kept["costs"]["item_subtotal_cents"] == 0
    assert kept["costs"]["total_cents"] is None
    assert {step["id"] for step in kept["timeline"]} == {"fit", "feedback"}
    draft.apply("assessment_strategy", "resident", {"strategy": "replace"})
    assert all(item["active"] for item in draft.view("resident")["selections"])
    assert draft.dump() == saved

    # Unknown item prices remain a partial subtotal, with units counted explicitly.
    real_match = assessment.match_options
    def unknown_price(need):
        result = real_match(need)
        for source in result["options"]:
            if source["id"] == "ikea_nissafors":
                source["published_price_cents"] = None
        return result
    with patch.object(assessment, "match_options", unknown_price):
        costs = draft.view("resident")["costs"]
        assert costs["unknown_item_count"] == 2 and costs["partial_known_subtotal"]
        assert costs["item_subtotal_cents"] is None and costs["total_cents"] is None
        assert costs["known_item_subtotal_cents"] == bathroom["published_price_cents"]

    # A draft cannot exceed ten unique selections, even across different needs.
    bounded = Assessment(host)
    bounded.apply("assessment_strategy", "resident", {"strategy": "replace"})
    choices = []
    for need in assessment.NEEDS:
        for option in match_options(need)["options"]:
            if option["kind"] == "product" and option["id"] not in {item[1] for item in choices}:
                choices.append((need, option["id"]))
    assert len(choices) >= 11
    for need, option_id in choices[:10]:
        bounded.apply("assessment_need", "resident", {"need": need})
        bounded.apply("assessment_add", "resident", {"option_id": option_id, "quantity": 1, "room_id": "Bedroom"})
    bounded.apply("assessment_need", "resident", {"need": choices[10][0]})
    before = bounded.dump()
    try:
        bounded.apply("assessment_add", "resident", {"option_id": choices[10][1], "quantity": 1, "room_id": "Bedroom"})
    except ValueError:
        pass
    else:
        raise AssertionError("An eleventh product was accepted")
    assert bounded.dump() == before

    # A draft stays attached to the original home and cannot silently transfer fit.
    other = SimpleNamespace(home={"id": "sketch", "rooms": [{"label": "R1", "use": "unspecified"}]})
    restored = Assessment.restore(other, saved)
    assert restored.dump() == saved
    assert all(item["placement"]["status"] == "needs_review" for item in restored.view("resident")["selections"])
    assert restored.view("resident")["existing_placement"]["status"] == "needs_review"
    assert restored.view("resident")["selections"][1]["fit_status"] == "assessment_required"
    for mutate in (
        lambda data: data.update(extra=True),
        lambda data: data["selections"][0].update(quantity=True),
        lambda data: data["selections"][0].update(room_id="Invented room"),
        lambda data: data["selections"][0].update(home_id="missing"),
        lambda data: data["selections"].append(deepcopy(data["selections"][0])),
        lambda data: data.update(strategy="buy"),
        lambda data: data["existing_item"].update(target_room_id="Invented room"),
        lambda data: data["existing_item"].update(description=""),
    ):
        bad = deepcopy(saved)
        mutate(bad)
        try:
            Assessment.restore(other, bad)
        except ValueError:
            pass
        else:
            raise AssertionError(bad)
    draft.apply("assessment_remove", "resident", {"option_id": "ikea_nissafors"})
    assert len(draft.dump()["selections"]) == 1
    print("PASS: assessment source prices, unknown totals, atomic validation, roles, fit review, room intent, source isolation, and restore/home changes.")


def check_constraints():
    class CoordinationStub:
        day = 1
        people = {"alex": {"day": 1, "available": True}, "morgan": {"day": 1, "available": True}}

        def available(self, actor):
            person = self.people.get(actor)
            return bool(person and person["day"] == self.day and person["available"] is True)

    host = SimpleNamespace(home={"id": "demo", "rooms": [
        {"label": "Bedroom", "use": "bedroom"}, {"label": "Bathroom", "use": "bathroom"}],
        "confirmed": [], "assumptions": [], "unknowns": []}, coordination=CoordinationStub())
    draft = Assessment(host)
    initial = draft.dump()
    assert initial["constraints"]["budget_cents"] is None
    assert initial["constraints"]["space"] == {"home_id": "demo", "room_id": None, "basis": "unknown",
                                               "width_in": None, "depth_in": None, "height_in": None}
    assert initial["setup_acceptance"] is None
    assert draft.view("family", "alex")["controls"]["can_edit"] is False
    assert draft.view("family", "alex")["controls"]["can_edit_constraints"] is True
    assert draft.view("family", "alex")["controls"]["can_reply_setup"] is False
    fields = {"budget_cents": 10000, "space": {"room_id": "Bedroom", "basis": "measured",
        "width_in": 50, "depth_in": 50, "height_in": 50}, "preferences": {
        "prefer_existing": False, "allow_assembly": True, "allow_drilling": True, "notes": "Keep the walkway clear."},
        "setup": "resident"}

    def set_fields(value=None, role="resident", actor_id=None):
        draft.apply("assessment_constraints", role, deepcopy(fields if value is None else value), actor_id=actor_id)

    def reject(action, role, payload, actor_id=None):
        before = draft.dump()
        try:
            draft.apply(action, role, payload, actor_id=actor_id)
        except ValueError:
            pass
        else:
            raise AssertionError((action, role, payload, actor_id))
        assert draft.dump() == before

    draft.apply("assessment_strategy", "resident", {"strategy": "replace"})
    draft.apply("assessment_existing", "resident", {"description": "Low basket", "current_room_id": "Bedroom", "target_room_id": "Bedroom"})
    source_before = match_options("home_storage")
    set_fields(role="family", actor_id="alex")
    assert draft.dump()["constraints"]["recorded_by"] == "alex"
    evaluation = draft.evaluate("ikea_nissafors", 1, "Bedroom")
    assert evaluation["total_cents"] is None and evaluation["known_items_cents"] == 2999
    assert evaluation["checks"]["setup"]["status"] == "unknown", "Family proposing resident setup is not resident consent"
    assert set(evaluation["checks"]) == {"budget", "space", "preferences", "setup", "existing_item"}
    assert evaluation["checks"]["space"]["status"] == "suitable_to_review"
    assert all(check["status"] in ("suitable_to_review", "conflict", "unknown") and check["reason"]
               for check in evaluation["checks"].values())
    assert evaluation["status"] in ("suitable_to_review", "conflict", "unknown")
    assert evaluation["checks"]["budget"]["status"] == "unknown"
    assert "evaluation" in draft.view("resident")["candidates"][0]

    # Dimensions must be reported for this room and be complete outer measurements.
    small = deepcopy(fields)
    small["space"].update(width_in=10, depth_in=10, height_in=20)
    set_fields(small)
    assert draft.evaluate("ikea_nissafors", 1, "Bedroom")["checks"]["space"]["status"] == "conflict"
    reported = deepcopy(fields)
    reported["space"]["basis"] = "reported"
    set_fields(reported)
    assert draft.evaluate("ikea_nissafors", 1, "Bedroom")["checks"]["space"]["status"] == "unknown"
    set_fields()
    assert draft.evaluate("ikea_nissafors", 1, "Bathroom")["checks"]["space"]["status"] == "unknown"
    assert draft.evaluate("ikea_nissafors", 2, "Bedroom")["checks"]["space"]["status"] == "unknown"
    assert draft.evaluate("vive_suction_reacher_lva1001", 1, "Bedroom")["checks"]["space"]["status"] == "unknown"
    assert draft.evaluate("moen_dn7060_shower_chair", 1, "Bedroom")["checks"]["space"]["status"] == "unknown"

    # Published quantities aggregate across the draft without counting the candidate twice.
    draft.apply("assessment_add", "resident", {"option_id": "ikea_nissafors", "quantity": 2, "room_id": "Bedroom"})
    draft.apply("assessment_need", "resident", {"need": "easy_grip"})
    draft.apply("assessment_add", "resident", {"option_id": "oxo_jar_opener_1173600", "quantity": 1, "room_id": "Bedroom"})
    cheap = deepcopy(fields)
    cheap["budget_cents"] = 7000
    set_fields(cheap)
    aggregate = draft.evaluate("ikea_nissafors", 2, "Bedroom")
    assert aggregate["known_items_cents"] == 7697 and aggregate["checks"]["budget"]["status"] == "conflict"
    assert draft.evaluate("ikea_nissafors", 3, "Bedroom")["known_items_cents"] == 10696
    set_fields()
    affordable_items = draft.evaluate("ikea_nissafors", 2, "Bedroom")
    assert affordable_items["total_cents"] is None and affordable_items["checks"]["budget"]["status"] == "unknown"
    assert draft.view("resident")["costs"]["tax_cents"] is None
    assert all("evaluation" in selection for selection in draft.view("resident")["selections"])

    no_assembly = deepcopy(fields)
    no_assembly["preferences"]["allow_assembly"] = False
    set_fields(no_assembly)
    assert draft.evaluate("ikea_nissafors", 2, "Bedroom")["checks"]["preferences"]["status"] == "conflict"
    prefer_existing = deepcopy(fields)
    prefer_existing["preferences"]["prefer_existing"] = True
    set_fields(prefer_existing)
    assert draft.evaluate("ikea_nissafors", 2, "Bedroom")["checks"]["preferences"]["status"] == "conflict"
    no_drilling = deepcopy(fields)
    no_drilling["preferences"]["allow_drilling"] = False
    set_fields(no_drilling)
    assert draft.evaluate("moen_r8716d1gch_grab_bar", 1, "Bedroom")["checks"]["preferences"]["status"] == "conflict"

    # Family setup is a named person's scoped reply, not a strategy or model claim.
    family_setup = deepcopy(fields)
    family_setup["setup"] = "family"
    set_fields(family_setup)
    scope = draft.view("family", "alex")["setup_scope"]
    assert scope and draft.view("family", "alex")["controls"]["can_reply_setup"] is True
    assert draft.evaluate("ikea_nissafors", 2, "Bedroom")["checks"]["setup"]["status"] == "unknown"
    for role, actor, payload in (
        ("resident", None, {"accepted": True, "scope": scope}),
        ("family", None, {"accepted": True, "scope": scope}),
        ("family", "stranger", {"accepted": True, "scope": scope}),
        ("family", "alex", {"accepted": 1, "scope": scope}),
        ("family", "alex", {"accepted": True, "scope": "forged"}),
        ("family", "alex", {"accepted": True, "scope": scope, "actor_id": "morgan"}),
    ):
        reject("assessment_setup_reply", role, payload, actor)
    draft.apply("assessment_setup_reply", "family", {"accepted": True, "scope": scope}, actor_id="alex")
    accepted = draft.dump()["setup_acceptance"]
    assert accepted == {"actor_id": "alex", "scope": scope, "accepted": True}
    assert draft.evaluate("ikea_nissafors", 2, "Bedroom")["checks"]["setup"]["status"] == "suitable_to_review"
    assert draft.evaluate("ikea_nissafors", 3, "Bedroom")["checks"]["setup"]["status"] == "unknown"
    reject("assessment_setup_reply", "family", {"accepted": True, "scope": scope}, "morgan")
    draft.apply("assessment_setup_reply", "family", {"accepted": False, "scope": scope}, actor_id="alex")
    assert draft.view("resident")["accepted_setup"] is None
    assert draft.evaluate("ikea_nissafors", 2, "Bedroom")["checks"]["setup"]["status"] == "unknown"
    draft.apply("assessment_setup_reply", "family", {"accepted": True, "scope": scope}, actor_id="alex")
    assert draft.evaluate("ikea_nissafors", 2, "Bedroom")["total_cents"] is None
    host.coordination.people["alex"]["available"] = False
    assert draft.evaluate("ikea_nissafors", 2, "Bedroom")["checks"]["setup"]["status"] != "suitable_to_review"
    assert draft.view("family", "alex")["controls"]["can_reply_setup"] is False
    reject("assessment_setup_reply", "family", {"accepted": True, "scope": scope}, "alex")
    host.coordination.people["alex"]["available"] = True
    host.coordination.day += 1
    assert draft.view("family", "alex")["setup_scope"] != scope
    assert draft.evaluate("ikea_nissafors", 2, "Bedroom")["checks"]["setup"]["status"] != "suitable_to_review"
    reject("assessment_setup_reply", "family", {"accepted": True, "scope": scope}, "alex")
    host.coordination.people["alex"]["day"] = host.coordination.day
    scope = draft.view("family", "alex")["setup_scope"]
    draft.apply("assessment_setup_reply", "family", {"accepted": True, "scope": scope}, actor_id="alex")
    draft.apply("assessment_observation", "resident", {"text": "Use the basket for books only."})
    assert draft.dump()["setup_acceptance"] is None
    reject("assessment_setup_reply", "family", {"accepted": True, "scope": scope}, "alex")

    # Home changes and inactive replacement options cannot preserve setup acceptance.
    scope = draft.view("family", "alex")["setup_scope"]
    draft.apply("assessment_setup_reply", "family", {"accepted": True, "scope": scope}, actor_id="alex")
    original_home = host.home
    host.home = {"id": "sketch", "rooms": [{"label": "R1", "use": "unspecified"}]}
    assert draft.view("family", "alex")["setup_scope"] != scope
    assert draft.view("family", "alex")["controls"]["can_reply_setup"] is False
    assert draft.evaluate("ikea_nissafors", 2, "R1")["checks"]["space"]["status"] == "unknown"
    reject("assessment_setup_reply", "family", {"accepted": True, "scope": scope}, "alex")
    host.home = original_home
    draft.apply("assessment_strategy", "resident", {"strategy": "keep"})
    assert draft.dump()["setup_acceptance"] is None
    assert draft.view("family", "alex")["controls"]["can_reply_setup"] is False
    reject("assessment_setup_reply", "family", {"accepted": True, "scope": draft.view("family", "alex")["setup_scope"]}, "alex")

    # Malformed constraints are rejected atomically; readers cannot forge attribution.
    invalid = []
    for key, value in (("budget_cents", True), ("budget_cents", -1), ("budget_cents", 12.5), ("setup", "anyone")):
        bad = deepcopy(fields)
        bad[key] = value
        invalid.append(bad)
    for key, value in (("basis", "guessed"), ("room_id", "missing"), ("width_in", True), ("depth_in", float("nan")), ("height_in", float("inf")), ("width_in", -1)):
        bad = deepcopy(fields)
        bad["space"][key] = value
        invalid.append(bad)
    for key, value in (("prefer_existing", "yes"), ("allow_assembly", 1), ("allow_drilling", [])):
        bad = deepcopy(fields)
        bad["preferences"][key] = value
        invalid.append(bad)
    invalid += [{**fields, "recorded_by": "alex"}, {**fields, "space": {**fields["space"], "home_id": "sketch"}}]
    for payload in invalid:
        reject("assessment_constraints", "resident", payload)
    reject("assessment_constraints", "family", fields)
    reject("assessment_constraints", "family", fields, "stranger")
    reject("assessment_constraints", "resident", fields, "alex")

    # Older five-field drafts migrate to unknown constraints without fabricated history.
    current = draft.dump()
    legacy = {key: deepcopy(current[key]) for key in ("need", "observation", "selections", "strategy", "existing_item")}
    old_copy = deepcopy(legacy)
    migrated = Assessment.restore(host, legacy)
    assert legacy == old_copy
    assert migrated.dump()["constraints"]["budget_cents"] is None
    assert migrated.dump()["constraints"]["space"]["basis"] == "unknown"
    assert migrated.dump()["setup_acceptance"] is None
    assert migrated.dump()["selections"] == current["selections"]
    assert Assessment.restore(host, current).dump() == current
    for mutate in (
        lambda data: data["constraints"].update(budget_cents=True),
        lambda data: data["constraints"]["space"].update(width_in=float("nan")),
        lambda data: data["constraints"]["preferences"].update(allow_assembly="yes"),
        lambda data: data["constraints"].update(recorded_by="stranger"),
        lambda data: data.update(setup_acceptance={"actor_id": "stranger", "scope": "forged", "accepted": True}),
    ):
        bad = deepcopy(current)
        mutate(bad)
        try:
            Assessment.restore(host, bad)
        except ValueError:
            pass
        else:
            raise AssertionError(bad)
    assert match_options("home_storage") == source_before
    # Withdrawal cannot revive an earlier setup promise when availability returns.
    from simulation import Household
    live_host = Household()
    live = live_host.assessment
    live.apply("assessment_strategy", "resident", {"strategy": "replace"})
    live.apply("assessment_add", "resident", {"option_id": "ikea_nissafors", "quantity": 1, "room_id": "Bedroom"})
    live.apply("assessment_constraints", "resident", family_setup)
    live.apply("assessment_setup_reply", "family", {"accepted": True, "scope": live.view("family", "alex")["setup_scope"]}, actor_id="alex")
    assert live.view("resident")["accepted_setup"] is not None
    live_host.event("coordination_availability", "family", live_host.revision, {"available": False}, actor_id="alex")
    assert live.view("resident")["accepted_setup"] is None
    live_host.event("coordination_availability", "family", live_host.revision, {"available": True}, actor_id="alex")
    assert live.view("resident")["accepted_setup"] is None, "Availability returning must not revive an old setup promise"
    live.apply("assessment_setup_reply", "family", {"accepted": True, "scope": live.view("family", "alex")["setup_scope"]}, actor_id="alex")
    live_host.event("select_sketch", "resident", live_host.revision)
    assert live.view("resident")["accepted_setup"] is None
    live_host.event("select_demo", "resident", live_host.revision)
    assert live.view("resident")["accepted_setup"] is None, "Returning to a home must not revive an old setup promise"
    print("PASS: assessment constraints change evaluation; budget aggregation, measured-space limits, preferences, scoped setup replies, atomic rejection, and migration.")


if __name__ == "__main__":
    check()
    check_constraints()
