"""Run with python3 test_real_world.py; no external services are called."""

from real_world import NEEDS, match_options


def check():
    for need in NEEDS:
        result = match_options(need)
        assert result["city"] == "San Francisco" and result["options"]
        for item in result["options"]:
            assert item["coordination_status"] == "not_requested"
            assert item["unknowns"] and item["next_steps"] and item["checked_at"]
            assert all(url.startswith("https://") for url in item["source_urls"])
    cart = match_options("home_storage", 3000)["options"][0]
    assert cart["published_price_cents"] == 2999
    assert cart["budget_status"] == "total_unknown"  # Item price is not the delivered total.
    assert match_options("home_storage", 2000)["options"][0]["budget_status"] == "listed_item_price_above_budget"
    assert match_options("everyday_help", 0)["options"][0]["budget_status"] == "total_unknown"
    assert {item["id"] for item in match_options("assembly")["options"]} == {"taskrabbit_assembly"}
    assert not match_options("assembly", channel="online")["options"]
    assert not match_options("dressing", channel="local")["options"]
    dressing = match_options("dressing", channel="online")["options"]
    assert {item["id"] for item in dressing} == {"vive_sock_assist_lva1067wht", "vive_button_hook_v_lva2051"}
    for item in dressing:
        assert item["channels"] == ["online"]
        assert item["fit_checks"] and item["limitations"] and item["setup_tasks"]
        assert item["match_status"] == "candidate_needs_checks"
    for item in match_options("bathroom_support", 100000, "online")["options"]:
        assert item["review_required"] and item["match_status"] == "assessment_required"
        assert item["budget_status"] == "total_unknown" and item["coordination_status"] == "not_requested"
    assert match_options("home_storage", channel="online")["options"][0]["id"] == "ikea_nissafors"
    assert match_options("home_storage", channel="local")["options"][0]["id"] == "ikea_nissafors"
    cart["unknowns"].clear()
    assert match_options()["options"][0]["unknowns"]  # Caller edits cannot alter later matches.
    for need, budget in [(None, None), ([], None), ("unknown", None), ("assembly", True),
                         ("assembly", -1), ("assembly", 3.5), ("assembly", float("nan"))]:
        try:
            match_options(need, budget)
        except ValueError:
            pass
        else:
            raise AssertionError((need, budget))
    for channel in [None, [], "web", True]:
        try:
            match_options(channel=channel)
        except ValueError:
            pass
        else:
            raise AssertionError(channel)
    print("Public catalog: task/channel matches, assessment boundaries, budget uncertainty, input and snapshot checks passed.")


if __name__ == "__main__":
    check()
