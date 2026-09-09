"""Authored meal acceptance without a browser, model, or real household effects."""

from copy import deepcopy
from types import SimpleNamespace
from careanchor.meal import Meal


class CoordinationStub:
    day = 1

    def __init__(self):
        self.completions = []
        self.cancellations = []
        self.available_today = {"alex": True, "morgan": True}

    def available(self, helper):
        return self.available_today[helper]

    def complete_help(self, request_id):
        assert request_id not in self.completions, "duplicate help completion"
        self.completions.append(request_id)

    def cancel_help(self, request_id):
        assert request_id not in self.cancellations, "duplicate cancellation"
        self.cancellations.append(request_id)


def fixture():
    host = SimpleNamespace(coordination=CoordinationStub())
    host.meal = Meal(host)
    return host, host.meal


def tick(meal):
    return meal.apply("meal_tick", "resident", {"episode_id": meal.state["episode_id"], "step": meal.state["step"]})


def run_until(meal, predicate, maximum=100):
    for _ in range(maximum):
        if predicate():
            return
        assert meal.can_tick(), meal.state["phase"]
        tick(meal)
        # Every real intermediate state must remain a loadable, inert snapshot.
        before = meal.dump()
        assert Meal.restore(meal.host, before).dump() == before
    raise AssertionError("Authored meal did not reach the expected bounded outcome")


def rejects(meal, action, role="resident", payload=None):
    before = meal.dump()
    try:
        meal.apply(action, role, payload)
    except ValueError:
        assert meal.dump() == before
    else:
        raise AssertionError("Unexpected accepted action: " + action)


def test_independent_meal():
    host, meal = fixture()
    assert meal.view("resident", "resident") == meal.view("resident")
    assert meal.view("family", "alex")["controls"] == []
    assert meal.view("family", "morgan")["controls"] == []
    meal.apply("meal_start", "resident")
    run_until(meal, lambda: meal.state["status"] == "completed")
    assert meal.state["objects"]["meal"]["location"] == "sink"
    assert meal.state["objects"]["meal"]["state"] == "cleared"
    assert host.coordination.completions == []
    assert not meal.state["actors"]["alex"]["visible"]
    events = meal.state["events"]
    actions = [event["action"] for event in events]
    assert actions.index("arrive") < actions.index("pick_up") < actions.index("prepare") < actions.index("sit") < actions.index("eat") < actions.index("clear")
    meal.apply("meal_feedback", "resident", {"feedback": "keep_routine"})
    rejects(meal, "meal_feedback", payload={"feedback": "keep_routine"})
    old = deepcopy(meal.state)
    meal.apply("meal_replay", "resident")
    assert meal.state["episode_id"] == old["episode_id"] + 1
    assert meal.state["history"] == old["history"] and meal.state["feedback"] == old["feedback"]
    assert meal.state["help"]["status"] == "none" and meal.state["objects"]["meal"]["state"] == "stored"


def test_refusal_then_independent():
    host, meal = fixture()
    meal.request_help("carry-1", "alex")
    meal.apply("meal_start", "resident")
    run_until(meal, lambda: meal.state["phase"] == "waiting_help")
    assert not meal.can_tick()
    rejects(meal, "meal_tick", payload={"episode_id": 1, "step": meal.state["step"]})
    meal.helper_reply("carry-1", "alex", "declined")
    run_until(meal, lambda: meal.state["status"] == "completed")
    assert meal.state["help"]["status"] == "declined" and host.coordination.completions == []
    assert not meal.state["actors"]["alex"]["visible"]


def test_helper_acceptance_arrival_and_completion():
    host, meal = fixture()
    meal.request_help("carry-2", "morgan")
    before = meal.dump()
    meal.request_help("carry-2", "morgan")
    assert meal.dump() == before
    meal.helper_reply("carry-2", "morgan", "accepted")
    assert host.coordination.completions == [] and meal.state["actors"]["morgan"]["position"] == "entry"
    assert meal.state["actors"]["morgan"]["carry"] == []
    meal.apply("meal_start", "resident")
    run_until(meal, lambda: bool(meal.state["actors"]["morgan"]["carry"]))
    assert meal.state["objects"]["meal"]["location"] == "morgan"
    assert meal.state["actors"]["morgan"]["position"] == "preparation"
    assert host.coordination.completions == []
    run_until(meal, lambda: meal.state["help"]["status"] == "completed")
    assert meal.state["objects"]["meal"]["location"] == "table_approach"
    assert meal.state["actors"]["morgan"]["position"] == "table_approach"
    assert host.coordination.completions == ["carry-2"]
    run_until(meal, lambda: meal.state["status"] == "completed")
    assert host.coordination.completions == ["carry-2"]
    Meal.restore(host, meal.dump())
    assert host.coordination.completions == ["carry-2"]


def test_cancellation_midcarry_and_stop():
    host, meal = fixture()
    meal.request_help("carry-3", "alex")
    meal.helper_reply("carry-3", "alex", "accepted")
    meal.apply("meal_start", "resident")
    run_until(meal, lambda: bool(meal.state["actors"]["alex"]["carry"]))
    tick(meal)
    assert meal.state["actors"]["alex"]["position"] == "kitchen_entry"
    meal.apply("meal_continue_independently", "resident")
    assert meal.state["objects"]["meal"]["location"] == "alex"  # cancellation itself does not move objects
    assert meal.state["actors"]["alex"]["phase"] == "stopping"
    tick(meal)
    assert meal.state["objects"]["meal"]["location"] == "kitchen_entry"
    assert meal.state["phase"] == "go_recover"
    assert host.coordination.completions == [] and host.coordination.cancellations == ["carry-3"]
    run_until(meal, lambda: meal.state["status"] == "completed")
    assert host.coordination.completions == []
    # Cancellation at final arrival still requires resident arrival at the table interaction anchor.
    host, meal = fixture()
    meal.request_help("cancel-at-table", "alex")
    meal.helper_reply("cancel-at-table", "alex", "accepted")
    meal.apply("meal_start", "resident")
    run_until(meal, lambda: meal.state["actors"]["alex"]["position"] == "table_approach"
              and bool(meal.state["actors"]["alex"]["carry"]))
    meal.apply("meal_continue_independently", "resident")
    run_until(meal, lambda: meal.state["status"] == "completed")
    assert host.coordination.completions == []
    host, meal = fixture()
    meal.request_help("carry-4", "alex")
    meal.helper_reply("carry-4", "alex", "accepted")
    meal.apply("meal_start", "resident")
    run_until(meal, lambda: bool(meal.state["actors"]["alex"]["carry"]))
    meal.apply("meal_stop", "resident")
    rejects(meal, "meal_tick", payload={"episode_id": 1, "step": meal.state["step"]})
    assert meal.state["objects"]["meal"]["location"] == "alex" and host.coordination.completions == []
    assert Meal.restore(host, meal.dump()).dump() == meal.dump()


def test_pause_stale_ticks_day_and_availability():
    host, meal = fixture()
    meal.apply("meal_start", "resident")
    stale = {"episode_id": 1, "step": 0}
    tick(meal)
    rejects(meal, "meal_tick", payload=stale)
    meal.apply("meal_pause", "resident")
    rejects(meal, "meal_tick", payload={"episode_id": 1, "step": 1})
    restored = Meal.restore(host, meal.dump())
    assert restored.state["status"] == "paused" and restored.state["step"] == 1
    meal.apply("meal_play", "resident")
    run_until(meal, lambda: meal.state["status"] == "completed")
    meal.apply("meal_feedback", "resident", {"feedback": "prefer_independent"})
    meal.next_day(2)
    host.coordination.day = 2
    host.coordination.available_today = {"alex": False, "morgan": False}
    assert meal.state["day"] == 2 and meal.state["status"] == "idle" and len(meal.state["history"]) == 1
    assert len(meal.state["feedback"]) == 1 and meal.state["help"]["status"] == "none"
    rejects(meal, "meal_tick", payload=stale)
    meal.request_help("day2-help", "alex")
    before = meal.dump()
    try:
        meal.helper_reply("day2-help", "alex", "accepted")
    except ValueError:
        assert meal.dump() == before
    else:
        raise AssertionError("Yesterday's helper availability was reused")
    rejects(meal, "meal_start", role="family")
    rejects(meal, "meal_tick", payload={"episode_id": True, "step": 0})


def test_malformed_restore():
    host, meal = fixture()
    saved = meal.dump()
    changes = (lambda s: s.update(unknown=1), lambda s: s.update(step=True),
               lambda s: s.update(status="completed", phase="complete"),
               lambda s: s.update(status="running", phase="retrieve"),
               lambda s: s["actors"]["resident"].update(position="sink"),
               lambda s: s["actors"]["resident"].update(carry=["meal"]),
               lambda s: s["objects"]["meal"].update(location="alex"),
               lambda s: s["help"].update(status="completed", helper="alex", request_id="fake"))
    for change in changes:
        altered = deepcopy(saved)
        change(altered)
        try:
            Meal.restore(host, altered)
        except ValueError:
            pass
        else:
            raise AssertionError("Malformed meal restore accepted")
    assert meal.dump() == saved and host.coordination.completions == []


def run():
    for test in (test_independent_meal, test_refusal_then_independent, test_helper_acceptance_arrival_and_completion,
                 test_cancellation_midcarry_and_stop, test_pause_stale_ticks_day_and_availability, test_malformed_restore):
        test()
    print("Meal acceptance passed: ordinary completion, optional/refused help, arrival before carrying, cancellation, stale/pause/reload/day guards, and malformed saves.")


if __name__ == "__main__":
    run()
