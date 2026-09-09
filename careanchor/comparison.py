"""Replay authored household weeks; counts are interactions, never minutes saved."""
from copy import deepcopy


DISRUPTIONS = (
    "appointment_conflict", "driver_decline", "papers_moved",
    "supply_unavailable", "event_cancelled", "home_comfort",
)
CHOICES = {
    "week_choose_slot": {"slot": "keep_activity"},
    "week_choose_supply": {"choice": "approve"},
    "week_choose_activity": {"choice": "alternative"},
    "week_choose_comfort": {"choice": "storage"},
    "week_comfort_feedback": {"helped": True},
}
PERMISSIONS = {
    "calendar": True, "backup_transport": True, "paperwork": True,
    "supplies": True, "home_help": True, "supply_cap": 25,
}
ROUTINE_ACTIONS = {
    "week_ack_appointment", "week_request_backup", "week_request_papers",
    "week_order_supplies", "week_cancel_event", "week_book_activity",
    "week_request_home_help", "week_run",
}
HELPER_ACTIONS = (
    "week_accept_backup", "week_decline_backup", "week_stage_papers",
    "week_deliver_supplies", "week_place_supplies", "week_report_home_help",
)


def _outcomes(week):
    """Only semantic facts: report revisions and narrative timestamps may differ."""
    items = {item["id"]: item for item in week["commitments"] + week["tasks"]}
    fields = {
        "appointment": ("status", "date", "time", "pickup", "version"),
        "community": ("status", "title", "date", "time", "arrangement", "choice"),
        "transport": ("status", "return_status", "requested_version", "outbound"),
        "paperwork": ("status", "checklist"),
        "supplies": ("status", "item", "substitute", "cost"),
        "community_arrangements": ("status",),
        "comfort": ("status", "observation", "choice", "helped"),
    }
    result = {key: {field: deepcopy(items[key][field]) for field in names}
              for key, names in fields.items()}
    result["paperwork"]["reported_location"] = {
        key: items["paperwork"]["reported_location"][key] for key in ("location", "status")}
    return result


def _audit(before, after, action):
    failures = []
    prior, now = _outcomes(before), _outcomes(after)
    for key, status, required in (
        ("transport", "confirmed", "week_accept_backup"),
        ("paperwork", "prepared", "week_stage_papers"),
        ("supplies", "delivered", "week_deliver_supplies"),
        ("supplies", "placed", "week_place_supplies"),
        ("comfort", "reported", "week_report_home_help"),
        ("comfort", "helped", "week_comfort_feedback"),
    ):
        if now[key]["status"] == status and prior[key]["status"] != status and action != required:
            failures.append(f"{key} reached {status} without its required human report.")
    if now["transport"]["status"] == "confirmed":
        if (now["transport"]["return_status"] != "confirmed" or
                now["transport"]["requested_version"] != now["appointment"]["version"] or
                now["transport"]["outbound"]["for_date"] != now["appointment"]["date"]):
            # Starting fixtures have an existing pickup only; they are audited once a
            # disruption has required fresh acceptance of both travel legs.
            if action not in ("week_configure", "week_permissions", "week_mode"):
                failures.append("Accepted transport lacks both legs for the current appointment.")
    new_events = after["accounting"]["events"][len(before["accounting"]["events"]):]
    if any(event["participant"] == "agent" for event in new_events):
        if action != "week_run" or before["mode"] != "assisted":
            failures.append("Agent execution occurred outside a supervised assisted run.")
        # This replay explicitly grants all five routine permissions. Checking the
        # recorded pre-action envelope prevents a benefit from unauthorized work.
        if not all(before["permissions"][key] for key in PERMISSIONS if key != "supply_cap"):
            failures.append("An agent executed without this replay's standing permissions.")
        if now["supplies"]["status"] == "ordered" and prior["supplies"]["status"] != "ordered":
            if now["supplies"]["cost"] > before["permissions"]["supply_cap"]:
                failures.append("The agent ordered above the recorded spending cap.")
    return failures


def _next_control(household):
    resident = household.view("resident")["week"]["controls"]
    for button in resident["decisions"]:
        if CHOICES.get(button["action"]) == button.get("payload", {}):
            return "resident", button
    # The quiet-time household has no alternative event offer. Leaving the time
    # free is its preference-respecting choice in both administration modes.
    activity = [button for button in resident["decisions"] if button["action"] == "week_choose_activity"]
    if activity:
        return "resident", next(button for button in activity if button["payload"] == {"choice": "free"})
    for button in resident["routine"]:
        if button["action"] in ROUTINE_ACTIONS:
            return "resident", button
    helpers = household.view("family")["week"]["controls"]["helpers"]
    for action in HELPER_ACTIONS:
        for button in helpers:
            if button["action"] == action:
                return "family", button
    return None


def _replay(profile_id, mode):
    # Local import avoids the Household.comparison -> comparison -> Household cycle.
    from .simulation import Household

    household = Household()
    inputs, failures = [], []

    def apply(action, role="resident", payload=None):
        before = household.view(role)
        after = household.event(action, role, before["revision"], payload)["week"]
        failures.extend(_audit(before["week"], after, action))
        if action == "week_inject" or action in CHOICES or action in HELPER_ACTIONS:
            inputs.append({"role": role, "action": action, "payload": deepcopy(payload or {})})

    # Profile and mode selectors are demonstration controls, not administration.
    household.event("week_select_profile", "resident", household.revision, {"id": profile_id})
    selected = household.view("resident")["week"]
    if selected["mode"] != mode:
        apply("week_mode", payload={"mode": mode})
    apply("week_configure", payload={key: selected["profile"][key] for key in selected["profile_fields"]})
    if mode == "assisted":
        apply("week_permissions", payload=PERMISSIONS)
    fixture = {"profile": deepcopy(selected["profile"]), "services": deepcopy(selected["fixture"])}

    for scenario in DISRUPTIONS:
        unchanged = _outcomes(household.view("resident")["week"])
        apply("week_inject", payload={"scenario": scenario})
        # ponytail: bounded replay of a fixed seven-task week; unknown actions stay
        # unresolved instead of adding an autonomous planner or inventing success.
        for _ in range(64):
            choice = _next_control(household)
            if choice is None:
                break
            role, button = choice
            apply(button["action"], role, button.get("payload"))
        else:
            failures.append("Replay exceeded its bounded action limit.")
        if scenario == "event_cancelled":
            current = _outcomes(household.view("resident")["week"])
            if any(current[key] != unchanged[key] for key in ("appointment", "transport", "paperwork")):
                failures.append("Community cancellation changed unrelated appointment preparation.")

    week = household.view("family")["week"]
    outcomes = _outcomes(week)
    evidence = [{key: item[key] for key in ("id", "label", "status", "evidence")}
                for item in week["commitments"] + week["tasks"]]
    terminal = {"appointment": {"acknowledged"}, "community": {"confirmed", "free"},
                "transport": {"confirmed"}, "paperwork": {"prepared"}, "supplies": {"placed", "declined"},
                "community_arrangements": {"confirmed", "cancelled"}, "comfort": {"helped", "declined"}}
    unresolved = list(week["exceptions"])
    for item in evidence:
        if item["status"] not in terminal[item["id"]]:
            unresolved.append(f"{item['label']}: {item['status'].replace('_', ' ')}.")
        if not item["evidence"]:
            failures.append(f"{item['label']} has no recorded evidence.")
    return {"fixture": fixture, "inputs": inputs, "accounting": week["accounting"],
            "outcomes": outcomes, "unresolved": unresolved, "evidence": evidence,
            "audit_failures": list(dict.fromkeys(failures))}


def compare_households():
    """Fresh authored fixtures only; neither the active plan nor its choices mutate."""
    from .simulation import Household

    result = {
        "title": "Matched fictional household weeks",
        "notice": "Deterministic simulation interaction counts, not measured time savings or U.S. population estimates.",
        "method": {
            "disruptions": list(DISRUPTIONS), "choices": deepcopy(CHOICES),
            "counts": {
                "first_week": "All recorded human interactions, including bundled profile setup counted as one action, bundled permission setup counted as one action, and each assistant-run supervision action.",
                "repeat_week": "The same replay's human total minus its setup interactions only; not an observed repeat-week study.",
                "agent": "Routine simulated administrative executions counted separately from human interactions.",
            },
            "exclusions": ["Scenario injection", "Profile and mode selectors", "Reset", "Camera and game controls"],
            "time_measured": False,
            "limits": ["Three authored situations have no national weights or representativeness claim.",
                       "Resident and family are recorded role buckets, not individually tracked people.",
                       "Both modes receive the already-identified tasks and disruption list. The replay tests administrative batching, not task discovery or cognitive load.",
                       "Family-role interaction counts are unchanged in these replays; no family burden or time reduction is demonstrated.",
                       "Preferences, fictional responses and physical-help requirements match within each pair; helper availability is never changed.",
                       "This replay deliberately requests backup help rather than choosing self-arranged travel in either mode. Unresolved backup help does not imply a resident cannot drive or use transit.",
                       "All five routine permissions and a $25 cap are explicitly set in the assisted replay; manual administration uses individual resident actions.",
                       "Each disruption settles before the next. Every assistant-run click counts as human supervision.",
                       "Quiet-time preference selects free time; other profiles select the offered alternative.",
                       "No minutes, health effects, clinical suitability, attendance or real services are inferred."],
        },
        "households": [],
    }
    for profile in Household().view("resident")["week"]["profiles"]:
        manual, assisted = _replay(profile["id"], "manual"), _replay(profile["id"], "assisted")
        result["households"].append({**profile, "fixture": deepcopy(manual["fixture"]),
                                     "manual": manual, "assisted": assisted,
                                     "comparison": _compare(manual, assisted)})
    return result


def _compare(manual, assisted):
    left, right = manual["accounting"], assisted["accounting"]
    participants = sorted(set(left["human_by_participant"]) |
                          set(right["human_by_participant"]))
    by_participant = [{
        "participant": person,
        "manual": left["human_by_participant"].get(person, 0),
        "assisted": right["human_by_participant"].get(person, 0),
        "saved": left["human_by_participant"].get(person, 0) -
                 right["human_by_participant"].get(person, 0),
    } for person in participants]
    same_inputs = manual["fixture"] == assisted["fixture"] and manual["inputs"] == assisted["inputs"]
    same_outcomes = manual["outcomes"] == assisted["outcomes"]
    first_saved = left["human_total"] - right["human_total"]
    repeat_saved = left["repeat_week_total"] - right["repeat_week_total"]
    shifted = any(row["saved"] < 0 for row in by_participant)
    reasons = []
    if not same_inputs or not same_outcomes:
        reasons.append("The replays did not preserve identical inputs and outcomes.")
    if manual["audit_failures"] or assisted["audit_failures"]:
        reasons.append("A permission or completion-evidence check failed.")
    if manual["unresolved"] or assisted["unresolved"]:
        reasons.append("Required work remains unresolved; lower interaction counts do not establish a completed-week benefit.")
    if shifted:
        reasons.append("At least one recorded role required more interactions after setup and supervision were counted.")
    if first_saved <= 0:
        reasons.append("Setup and supervision erase the first-week interaction saving.")
    if repeat_saved <= 0:
        reasons.append("There is no interaction saving after excluding setup.")
    return {
        "same_inputs": same_inputs, "same_outcomes": same_outcomes,
        "first_week_human_saved": first_saved,
        "repeat_week_human_saved": repeat_saved,
        "by_participant": by_participant, "work_shifted": shifted,
        "claim_supported": not reasons,
        "explanation": " ".join(reasons) if reasons else
            "This matched synthetic replay used fewer human interactions, including setup, with no increase in either recorded role and no unresolved required work. This is not a measured real-world benefit.",
    }
