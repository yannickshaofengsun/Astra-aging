"""Authored mission replays through real validators. No model or external action."""
from copy import deepcopy
import json


def _case(case_id, label):
    from simulation import Household

    household = Household(save_path=None)
    community = deepcopy(household.week.community)
    game = deepcopy(household.outing)
    trace, failures = [], []
    hidden_checks = {"snapshots_checked": 0, "hidden_keys_absent": True,
                     "items_unknown_until_observed": True, "blockage_unknown_until_inspected": True,
                     "helper_decline_requires_report": True, "alternate_requires_observation": True}
    observed_items = set()
    reported = set()
    blocked_seen = False

    def inspect():
        nonlocal blocked_seen
        view = household.mission.coordinator_view()
        hidden_checks["snapshots_checked"] += 1
        forbidden = {"world", "bag_zone", "documents_zone", "primary_available", "main_blocked", "alternate_usable"}

        def keys(value):
            if isinstance(value, dict):
                return set(value) | set().union(*(keys(child) for child in value.values()), set())
            if isinstance(value, list):
                return set().union(*(keys(child) for child in value), set())
            return set()

        hidden_checks["hidden_keys_absent"] &= not bool(keys(view) & forbidden)
        for item in ("bag", "documents"):
            if item not in observed_items:
                hidden_checks["items_unknown_until_observed"] &= view["known"][item]["location"] is None
        if view["known"]["main_route"] == "blocked":
            blocked_seen = True
        if not blocked_seen:
            hidden_checks["blockage_unknown_until_inspected"] &= view["known"]["main_route"] == "unknown"
        if "mission_primary_decline" not in reported:
            hidden_checks["helper_decline_requires_report"] &= view["known"]["primary"] != "declined"
        if "mission_observe_alternate" not in reported:
            hidden_checks["alternate_requires_observation"] &= view["known"]["alternate_route"] == "unknown"
        return view

    def step(role, action, payload=None, expected=True):
        before = inspect()
        before_revision = household.revision
        before_state = household.mission.dump()
        controls = household.mission.view(role)["controls"][role]
        offered = any(button["action"] == action and button.get("payload", {}) == (payload or {})
                      for button in controls)
        editable = role == "resident" and action in ("mission_permissions", "mission_set_deadline", "mission_advance_time")
        try:
            if role == "coordinator":
                # The script never impersonates an Astra proposal. Mission.apply is
                # the real role/action validator; a fresh host needs only revision bookkeeping.
                with household._lock:
                    result = household.mission.apply(action, role, payload)
                    household.revision += 1
            else:
                household.event(action, role, before_revision, payload)
                result = household.mission.coordinator_view()["events"][-1]["result"]
            accepted = True
        except ValueError as error:
            accepted, result = False, str(error)
        if accepted and not (offered or editable):
            failures.append(f"{action} executed without an exposed control or validated settings form.")
        if accepted != expected:
            failures.append(f"{action}: expected {'acceptance' if expected else 'rejection'}, got {'acceptance' if accepted else 'rejection'}.")
        if accepted:
            reported.add(action)
            if action in ("mission_observe_bag", "mission_observe_documents"):
                observed_items.add(action.removeprefix("mission_observe_"))
            if household.revision != before_revision + 1:
                failures.append(f"{action} did not advance the successful action revision once.")
        elif household.mission.dump() != before_state or household.revision != before_revision:
            failures.append(f"Rejected {action} changed mission state or revision.")
        after = inspect()
        if (before["known"]["main_route"] != "blocked" and after["known"]["main_route"] == "blocked"
                and action != "mission_move_robot"):
            hidden_checks["blockage_unknown_until_inspected"] = False
        trace.append({"role": role, "action": action, "payload": deepcopy(payload or {}),
                      "accepted": accepted, "offered": offered, "result": result,
                      "revision": household.revision, "simulated_minute": after["clock_minutes"],
                      "status": after["status"], "robot_status": after["robot"]["status"],
                      "robot_position": after["robot"]["position"]})

    step("resident", "mission_start")
    step("resident", "mission_opt_in")
    step("resident", "mission_permissions", {"coordinator": True, "backup_helper": True,
         "robot_transport": True, "main_route": True})
    step("coordinator", "mission_request_primary")
    step("coordinator", "mission_request_search")
    step("coordinator", "mission_wait")
    step("family", "mission_primary_decline")
    step("coordinator", "mission_request_backup")
    step("family", "mission_backup_decline" if case_id == "backup_declined" else "mission_backup_accept")
    for item in ("bag", "documents"):
        step("resident", "mission_check_" + item)
        step("resident", "mission_observe_" + item)
    if case_id == "backup_declined":
        step("coordinator", "mission_request_backup", expected=False)
        step("coordinator", "mission_request_loading", expected=False)
        step("coordinator", "mission_wait")
    else:
        step("family", "mission_confirm_travel")
        step("coordinator", "mission_request_loading")
        step("family", "mission_stage_documents")
        step("family", "mission_load_robot")
        if case_id == "overdue":
            step("resident", "mission_set_deadline", {"deadline_minutes": 5})
        step("coordinator", "mission_dispatch_main")
        step("coordinator", "mission_move_robot")
        if case_id == "cancelled":
            step("resident", "mission_cancel")
            step("coordinator", "mission_move_robot", expected=False)
        elif case_id == "overdue":
            step("coordinator", "mission_move_robot", expected=False)
        else:
            step("coordinator", "mission_move_robot")  # Inspect the blocked segment and stop.
            step("coordinator", "mission_dispatch_alternate", expected=False)
            step("resident", "mission_observe_alternate", {"usable": case_id != "no_alternate"})
            if case_id == "no_alternate":
                step("coordinator", "mission_dispatch_alternate", expected=False)
                step("coordinator", "mission_wait")
            else:
                step("coordinator", "mission_dispatch_alternate", expected=False)  # Observation alone is not permission.
                step("resident", "mission_permissions", {"alternate_route": True})
                step("coordinator", "mission_dispatch_alternate")
                step("coordinator", "mission_move_robot")
                step("coordinator", "mission_move_robot")

    final = inspect()
    current_travel = (household.transport["status"] == "confirmed" and
                      household.transport["person"] == final["helper_names"]["backup"] and
                      household.transport["for_date"] == final["appointment"]["date"] and
                      household.week.return_status == "confirmed" and
                      household.week.return_version == final["appointment_version"] and
                      household.week.return_person == final["helper_names"]["backup"] and
                      household.week.backup_version == final["appointment_version"] == household.week.appointment_version)
    ready = final["status"] == "ready_to_leave"
    if ready and (not current_travel or not final["known"]["documents_staged"] or
                  not final["known"]["helper_loaded"] or final["robot"]["status"] != "delivered" or
                  final["clock_minutes"] >= final["deadline_minutes"]):
        failures.append("Readiness lacks current travel, physical reports, delivery, or time before the deadline.")
    community_preserved = community == household.week.community
    game_preserved = game == household.outing
    if not community_preserved or not game_preserved:
        failures.append("The mission changed an unrelated community commitment or the independent game.")
    if not all(value for key, value in hidden_checks.items() if key != "snapshots_checked"):
        failures.append("A coordinator observation exposed hidden or unobserved world facts.")
    controls = {"mission_start", "mission_reset", "mission_set_deadline", "mission_advance_time"}
    return {
        "id": case_id, "label": label, "status": final["status"], "ready_to_leave": ready,
        "simulated_clock": {"elapsed": final["clock_minutes"], "deadline": final["deadline_minutes"],
                            "unit": "fictional minutes", "real_elapsed_time_measured": False},
        "shared_travel": {"outbound": deepcopy(household.transport), "return_status": household.week.return_status,
                          "return_version": household.week.return_version, "return_person": household.week.return_person,
                          "mission_appointment_version": final["appointment_version"],
                          "shared_appointment_version": household.week.appointment_version,
                          "accepted_version": household.week.backup_version, "for_current_version": current_travel},
        "community_preserved": community_preserved, "separate_game_preserved": game_preserved,
        "world_hidden_checks": hidden_checks,
        "counts": {
            "selected_actions": len(trace), "executed_actions": sum(row["accepted"] for row in trace),
            "resident_interventions": sum(row["role"] == "resident" and row["action"] not in controls for row in trace),
            "family_interventions": sum(row["role"] == "family" for row in trace),
            "coordinator_actions": sum(row["role"] == "coordinator" and row["accepted"] for row in trace),
            "waits": sum(row["action"] == "mission_wait" and row["accepted"] for row in trace),
            "rejected_actions": sum(not row["accepted"] for row in trace),
            "game_controls": sum(row["action"] in controls for row in trace),
        },
        "known": final["known"], "robot": final["robot"], "unresolved": final["unresolved"],
        "trace": trace, "audit_failures": failures,
    }


def evaluate_missions():
    """Return reproducible evidence from fresh, unsaved Household instances."""
    return {
        "kind": "scripted_runtime_evaluation", "model_used": False,
        "notice": "Authored action scripts exercise actual simulation validators. These are not Astra-selected actions or evidence of model performance.",
        "method": {
            "disruptions": ["Appointment changed", "Primary helper unavailable", "Bag and documents moved", "Main symbolic route blocked"],
            "human_inputs": "The script supplies resident choices, observations and family reports; these are fictional interventions, not actual people.",
            "counts": "Selected actions include rejected probes. Executed actions and coordinator actions include accepted waits. Resident/family interventions count selected role actions, excluding start, reset and fictional-clock controls; permission setup is included.",
            "rejections": "The authored scripts deliberately attempt forbidden actions to verify rejection; these probes are not model mistakes or ordinary workflow requirements.",
            "clock": "Only explicit clock changes and robot execution steps advance fictional minutes. No real human or model duration is measured.",
            "limits": ["No model, network call, saved-session mutation, real booking, physical robot or clinical action.",
                       "Role action counts do not establish individual burden or time savings.",
                       "The script knows the authored case; hidden-world checks test the coordinator view, not an AI's ability to discover a solution.",
                       "Unavailable helper and unavailable alternate route are separate failure cases; neither is silently repaired."],
        },
        "cases": [_case(key, label) for key, label in (
            ("recoverable", "Changed outing recovered through observed, permitted actions"),
            ("backup_declined", "Backup declines; physical preparation stays unresolved"),
            ("no_alternate", "Blocked main route; no usable alternate observed"),
            ("cancelled", "Resident cancels while delivery is moving"),
            ("overdue", "Departure deadline reached before delivery"),
        )],
    }


if __name__ == "__main__":
    print(json.dumps(evaluate_missions(), indent=2, ensure_ascii=False, sort_keys=True))
