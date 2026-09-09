"""Run: python3 -m tests.test_simulation"""

import json
from careanchor.simulation import Household, InvalidAction


def rejects(fn):
    try:
        fn()
    except InvalidAction:
        return
    raise AssertionError("Invalid action was accepted")


def check():
    home = Household()
    assert home.view("resident")["plan_status"] == "ready"
    assert home.view("resident")["home"]["id"] == "demo"
    assert "reason" not in home.view("family")["appointment"]
    assert "Private follow-up" not in json.dumps(home.view("family"))
    snapshot = home.view("family")
    snapshot["transport"]["status"] = "tampered"
    assert home.view("family")["transport"]["status"] == "confirmed"

    changed = home.event("reschedule", "resident", home.revision)
    assert changed["transport"] == {"status": "needs_confirmation", "person": None, "for_date": None}
    assert changed["plan_status"] == "needs_attention"
    rejects(lambda: home.event("confirm_ride", "family", 0))
    rejects(lambda: home.event("confirm_ride", "family"))
    rejects(lambda: home.event("confirm_ride", "resident", changed["revision"]))
    declined = home.event("decline_ride", "family", changed["revision"])
    assert declined["transport"]["status"] == "declined"
    assert declined["plan_status"] == "needs_attention"
    accepted = home.event("confirm_ride", "family", declined["revision"])
    assert accepted["plan_status"] == "ready"
    assert accepted["transport"]["for_date"] == "2026-09-17"

    moved = home.event("move_documents", "resident", home.revision)
    assert moved["documents"]["location"] == "Entrance shelf"
    assert moved["documents"]["status"] == "last_known"
    assert "Bedroom drawer" not in json.dumps(home.view("family"))
    assert moved["plan_status"] == "needs_attention"
    rejects(lambda: home.event("confirm_documents", "family", moved["revision"]))
    found = home.event("confirm_documents", "resident", moved["revision"])
    assert found["documents"]["location"] == "Bedroom drawer"
    assert found["documents"]["status"] == "confirmed"
    assert found["plan_status"] == "ready"
    rejects(lambda: home.view("stranger"))
    rejects(lambda: home.event("send_real_booking", "resident"))
    before_reset = found["revision"]
    rejects(lambda: home.event("reset", "resident", 0))
    rejects(lambda: home.event("reset", "resident"))
    rejects(lambda: home.event("reset", "family", home.revision))
    assert home.view("resident")["revision"] == before_reset
    reset = home.event("reset", "resident", home.revision)
    assert reset["revision"] > before_reset
    assert reset["appointment"]["date"] == "2026-09-15"
    assert "reason" not in home.view("family")["appointment"]
    sketch = home.event("select_sketch", "resident", home.revision)
    assert sketch["home"]["id"] == "sketch"
    assert sum(r["use"] == "bedroom" for r in sketch["home"]["rooms"]) == 3
    assert "unmeasured" in sketch["home"]["scale_status"]
    assert sketch["home"]["unknowns"] and sketch["home"]["assumptions"]
    assert {p["id"] for p in sketch["outing"]["hotspots"]} == {"invitation", "bag", "entrance"}
    assert all(0 < p["x"] < 1 and 0 < p["y"] < 1 for p in sketch["outing"]["hotspots"])
    assert "/Users/" not in json.dumps(home.view("family"))
    assert "IMG_4043" not in json.dumps(home.view("family"))
    assert "fictional" in sketch["notice"]
    assert home.event("reset", "resident", home.revision)["home"]["id"] == "sketch"
    assert home.event("select_demo", "family", home.revision)["home"]["id"] == "demo"
    def play(action, role="resident"):
        return home.event(action, role, home.revision)["outing"]
    assert play("keep_routine")["outcome"] == "staying_home"
    rejects(lambda: play("game_bag"))
    rejects(lambda: play("join_activity", "family"))
    assert play("join_activity")["next_hotspot"] == "invitation"
    rejects(lambda: play("game_entrance"))
    assert play("request_support")["support"] == "requested"
    old_revision = home.revision
    for step in ("invitation", "bag", "entrance"):
        played = play("game_" + step)
    assert played["outcome"] == "waiting_for_support"
    rejects(lambda: home.event("confirm_support", "family", old_revision))
    rejects(lambda: play("confirm_support"))
    assert play("confirm_support", "family")["outcome"] == "ready"
    assert play("restart_game")["outcome"] == "choose"
    play("join_activity")
    for step in ("invitation", "bag", "entrance"):
        played = play("game_" + step)
    assert played["outcome"] == "ready" and played["support"] == "not_requested"
    assert play("keep_routine")["outcome"] == "staying_home"
    assert "failure" not in played
    assert home.view("family")["outing"]["activity"]["is_sample"] is True
    print("PASS: coordination/privacy, sketch facts, ordered game steps, voluntary decline, optional support, reset.")


if __name__ == "__main__":
    check()
