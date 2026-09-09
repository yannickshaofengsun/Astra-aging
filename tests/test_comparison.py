"""Run with: python3 -m tests.test_comparison (no model call or external action)."""
from copy import deepcopy
import json
from unittest.mock import patch

from careanchor.comparison import _audit, _compare, compare_households


def check_claims():
    manual = {
        "fixture": {"helper_available": True}, "inputs": ["same disruption"],
        "outcomes": {"papers": "staged"}, "unresolved": [], "audit_failures": [],
        "accounting": {"human_total": 4, "agent_total": 0, "setup_total": 1,
                       "repeat_week_total": 3, "human_by_participant": {"resident": 2, "helper": 2}},
    }
    assisted = deepcopy(manual)
    assisted["accounting"].update(human_total=4, agent_total=8, setup_total=3,
                                  repeat_week_total=1,
                                  human_by_participant={"resident": 3, "helper": 1})
    result = _compare(manual, assisted)
    assert result["first_week_human_saved"] == 0
    assert result["repeat_week_human_saved"] == 2
    assert result["work_shifted"] and not result["claim_supported"]
    assisted["accounting"].update(human_total=3, setup_total=1, repeat_week_total=2,
                                  human_by_participant={"resident": 2, "helper": 1})
    assert _compare(manual, assisted)["claim_supported"]
    assisted["unresolved"] = ["No helper accepted"]
    assert not _compare(manual, assisted)["claim_supported"]
    assisted["unresolved"] = []
    assisted["outcomes"] = {"papers": "requested"}
    assert not _compare(manual, assisted)["same_outcomes"]
    assert not _compare(manual, assisted)["claim_supported"]


def check_replays():
    from careanchor.simulation import Household

    active = Household()
    active.event("week_inject", "resident", active.revision, {"scenario": "appointment_conflict"})
    before = active.view("resident")
    original_event = Household.event
    seen = []

    def checked_event(self, action, role, expected_revision=None, payload=None):
        assert expected_revision == self.revision
        if action not in ("week_select_profile", "week_configure", "week_permissions"):
            controls = self.view(role)["week"]["controls"]
            assert any(button["action"] == action and button.get("payload", {}) == (payload or {})
                       for group in controls.values() for button in group), (role, action, payload)
        seen.append((role, action))
        return original_event(self, action, role, expected_revision, payload)

    with patch.object(Household, "event", checked_event):
        result = active.comparison()
    assert active.view("resident") == before, "Comparison mutated the active household"
    assert len(json.dumps(result).encode()) < 256 * 1024
    assert result["method"]["time_measured"] is False
    assert {row["id"] for row in result["households"]} == {"nearby", "couple", "remote"}
    assert all(action != "week_helper_availability" for _, action in seen)
    for row in result["households"]:
        assert row["comparison"]["same_inputs"] and row["comparison"]["same_outcomes"]
        assert row["manual"]["inputs"] == row["assisted"]["inputs"]
        assert not row["comparison"]["work_shifted"]
        for mode, setup in (("manual", 1), ("assisted", 2)):
            run = row[mode]
            accounting = run["accounting"]
            events = accounting["events"]
            assert not run["audit_failures"], run["audit_failures"]
            assert accounting["setup_total"] == setup
            assert accounting["human_total"] == sum(e["participant"] != "agent" for e in events)
            assert accounting["agent_total"] == sum(e["participant"] == "agent" for e in events)
            assert sum(accounting["human_by_participant"].values()) == accounting["human_total"]
            assert sum(accounting["human_by_category"].values()) == accounting["human_total"]
            assert accounting["repeat_week_total"] == accounting["human_total"] - setup
            assert all(e["category"] not in ("injection", "reset", "game") for e in events)
            if mode == "manual":
                assert accounting["agent_total"] == 0
            else:
                assert accounting["agent_total"] > 0
                assert accounting["human_by_category"]["supervision"] > 0
        if row["id"] == "remote":
            for mode in ("manual", "assisted"):
                assert not row[mode]["fixture"]["profile"]["helper_available"]
                assert row[mode]["outcomes"]["transport"]["status"] == "declined"
                assert row[mode]["outcomes"]["paperwork"]["status"] == "requested"
                assert row[mode]["outcomes"]["supplies"]["status"] == "delivered"
                assert row[mode]["outcomes"]["comfort"]["status"] == "requested"
                assert row[mode]["unresolved"]
            assert not row["comparison"]["claim_supported"]
        else:
            assert not row["manual"]["unresolved"] and not row["assisted"]["unresolved"]
            assert row["comparison"]["claim_supported"]

    # A completion assertion without the corresponding physical report is detected.
    week = active.view("resident")["week"]
    unsupported = deepcopy(week)
    next(task for task in unsupported["tasks"] if task["id"] == "comfort")["status"] = "helped"
    assert any("required human report" in text for text in _audit(week, unsupported, "week_run"))
    assert compare_households() == result, "Replay must be deterministic"


if __name__ == "__main__":
    check_claims()
    check_replays()
    print("Comparison isolation, matched outcomes, permissions, completion evidence and accounting checks passed.")
