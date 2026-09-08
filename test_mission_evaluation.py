"""Run with python3 test_mission_evaluation.py; no model or external service."""
from copy import deepcopy
import json
from unittest.mock import patch

from mission_evaluation import evaluate_missions
from simulation import Household


def check_evaluation():
    active = Household(save_path=None)
    active.event("mission_start", "resident", active.revision)
    before = deepcopy(active.view("resident"))
    # Guard the boundary: this evaluator must never call the model-labelled proposal
    # path, start a model process, or contact an external service.
    with patch.object(Household, "apply_mission_proposal", side_effect=AssertionError("Not a model evaluation")), \
            patch("subprocess.Popen", side_effect=AssertionError("No subprocesses")), \
            patch("socket.socket", side_effect=AssertionError("No network")):
        result = evaluate_missions()
        assert evaluate_missions() == result
    assert active.view("resident") == before
    assert result["kind"] == "scripted_runtime_evaluation" and result["model_used"] is False
    assert len(json.dumps(result).encode()) < 256 * 1024
    cases = {case["id"]: case for case in result["cases"]}
    assert set(cases) == {"recoverable", "backup_declined", "no_alternate", "cancelled", "overdue"}
    for case in cases.values():
        assert not case["audit_failures"], case["audit_failures"]
        assert case["community_preserved"] and case["separate_game_preserved"]
        assert all(case["world_hidden_checks"].values())
        counts, trace = case["counts"], case["trace"]
        assert counts["selected_actions"] == len(trace)
        assert counts["executed_actions"] == sum(row["accepted"] for row in trace)
        assert counts["executed_actions"] + counts["rejected_actions"] == len(trace)
        assert counts["coordinator_actions"] == sum(row["accepted"] and row["role"] == "coordinator" for row in trace)
        assert counts["family_interventions"] == sum(row["role"] == "family" for row in trace)
        assert counts["waits"] == sum(row["accepted"] and row["action"] == "mission_wait" for row in trace)
        assert all(row["offered"] for row in trace if row["accepted"] and row["role"] == "coordinator")
        assert case["simulated_clock"]["real_elapsed_time_measured"] is False
        assert all(left["simulated_minute"] <= right["simulated_minute"] for left, right in zip(trace, trace[1:]))
        assert all(left["revision"] + int(right["accepted"]) == right["revision"]
                   for left, right in zip(trace, trace[1:]))
        if case["id"] != "recoverable":
            assert case["unresolved"] and not case["ready_to_leave"]
            assert case["robot"]["status"] != "delivered"

    recovered = cases["recoverable"]
    assert recovered["ready_to_leave"] and recovered["status"] == "ready_to_leave"
    assert recovered["shared_travel"]["for_current_version"] and not recovered["unresolved"]
    assert recovered["shared_travel"]["return_version"] == recovered["shared_travel"]["mission_appointment_version"]
    assert recovered["shared_travel"]["return_person"] == recovered["shared_travel"]["outbound"]["person"]
    assert recovered["known"]["documents_staged"] and recovered["known"]["helper_loaded"]
    assert recovered["robot"]["status"] == "delivered" and recovered["robot"]["position"] == "Departure"
    assert recovered["simulated_clock"]["elapsed"] == 20 < recovered["simulated_clock"]["deadline"]
    trace = recovered["trace"]
    actions = [row["action"] for row in trace if row["accepted"]]
    for item in ("bag", "documents"):
        assert actions.index("mission_check_" + item) < actions.index("mission_observe_" + item)
    assert actions.index("mission_stage_documents") < actions.index("mission_load_robot") < actions.index("mission_dispatch_main")
    moves = [row for row in trace if row["action"] == "mission_move_robot" and row["accepted"]]
    assert [(row["robot_status"], row["robot_position"]) for row in moves] == [
        ("moving", "Hall"), ("blocked", "Hall"), ("moving", "R1"), ("delivered", "Departure")]
    alternate_attempts = [row for row in trace if row["action"] == "mission_dispatch_alternate"]
    assert [row["accepted"] for row in alternate_attempts] == [False, False, True]

    declined = cases["backup_declined"]
    assert declined["known"]["backup"] == "declined" and not declined["shared_travel"]["for_current_version"]
    assert not declined["known"]["documents_staged"] and not declined["known"]["helper_loaded"]
    blocked = cases["no_alternate"]
    assert blocked["known"]["alternate_route"] == "unavailable" and blocked["robot"]["status"] == "blocked"
    assert cases["cancelled"]["status"] == "cancelled" and cases["cancelled"]["robot"]["status"] == "cancelled"
    overdue = cases["overdue"]
    assert overdue["status"] == "overdue"
    assert overdue["simulated_clock"]["elapsed"] == overdue["simulated_clock"]["deadline"] == 5
    for key in ("cancelled", "overdue"):
        assert cases[key]["trace"][-1]["action"] == "mission_move_robot"
        assert not cases[key]["trace"][-1]["accepted"]


if __name__ == "__main__":
    check_evaluation()
    print("Five mission replay, hidden-world, isolation, timing, rejection and accounting checks passed.")
