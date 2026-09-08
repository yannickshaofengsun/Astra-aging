"""Bounded local snapshots, never pickles or action replays."""
from copy import deepcopy
from datetime import date, datetime
from hashlib import sha256
import json
from math import isfinite
import os
from pathlib import Path
import tempfile

MAX_SAVE = 262144
FIELDS = ("revision", "context_revision", "appointment", "transport", "documents",
          "_actual_document_location", "activity", "outing", "mission_proposals")


def _encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _bounded(value, depth=0):
    if depth > 15:
        raise ValueError("Snapshot is too deeply nested.")
    if value is None or type(value) is bool:
        return
    if type(value) in (int, float):
        if not isfinite(value) or abs(value) > 2**53:
            raise ValueError("Invalid snapshot number.")
    elif type(value) is str:
        if len(value) > 8000:
            raise ValueError("Snapshot text exceeds the limit.")
    elif type(value) is list:
        if len(value) > 1000:
            raise ValueError("Snapshot list exceeds the limit.")
        for item in value:
            _bounded(item, depth + 1)
    elif type(value) is dict:
        if len(value) > 100 or any(type(key) is not str or len(key) > 100 for key in value):
            raise ValueError("Invalid snapshot object.")
        for item in value.values():
            _bounded(item, depth + 1)
    else:
        raise ValueError("Unsupported snapshot type.")


def _shape(value, template):
    """Exact object fields/types; nullable primitive state is checked by its owner."""
    if template is None:
        if value is not None and type(value) not in (str, int, bool):
            raise ValueError("Invalid nullable snapshot field.")
    elif type(template) is dict:
        if type(value) is not dict or set(value) != set(template):
            raise ValueError("Snapshot fields differ from this version.")
        for key in template:
            _shape(value[key], template[key])
    elif type(template) is list:
        if type(value) is not list:
            raise ValueError("Invalid snapshot list.")
        if template:
            for item in value:
                _shape(item, template[0])
    elif type(template) is float:
        if type(value) not in (int, float):
            raise ValueError("Invalid numeric field.")
    elif type(value) is not type(template):
        raise ValueError("Invalid snapshot field type.")


def save_household(host, path):
    data = {key: deepcopy(getattr(host, key)) for key in FIELDS}
    data.update(home_id=host.home["id"], week={key: deepcopy(value) for key, value in vars(host.week).items() if key != "host"},
                mission=host.mission.dump(), coordination=host.coordination.dump(), meal=host.meal.dump(),
                assessment=host.assessment.dump(), hospital=host.hospital.dump(), family_edition=host.family_edition.dump())
    _bounded(data)
    body = _encoded({"schema": 3, "data": data, "sha256": sha256(_encoded(data)).hexdigest()})
    if len(body) > MAX_SAVE:
        raise ValueError("Saved mission exceeds the limit.")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # ponytail: one atomic local snapshot; use a database only for multiple households.
    name = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".mission-", delete=False) as stream:
            name = stream.name
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if name is not None and os.path.exists(name):
            os.unlink(name)


def load_household(path):
    from simulation import Household, home_context
    from mission import Mission
    from coordination import Coordination
    from meal import Meal
    from assessment import Assessment
    from hospital import Hospital
    from family_edition import FamilyEdition
    from week import PROFILE_FIELDS, PROFILES, SCENARIOS

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate snapshot field.")
            result[key] = value
        return result

    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_SAVE + 1)
    if len(raw) > MAX_SAVE:
        raise ValueError("Saved mission exceeds the limit.")
    try:
        envelope = json.loads(raw, object_pairs_hook=pairs,
                              parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        if (type(envelope) is not dict or set(envelope) != {"schema", "data", "sha256"}
                or type(envelope["schema"]) is not int or envelope["schema"] not in (1, 2, 3)
                or sha256(_encoded(envelope["data"])).hexdigest() != envelope["sha256"]):
            raise ValueError("Snapshot version or integrity check failed.")
        data = envelope["data"]
        _bounded(data)
        extra = {"coordination", "meal", "assessment", "hospital"} if envelope["schema"] >= 2 else set()
        if envelope["schema"] == 3:
            extra.add("family_edition")
        if type(data) is not dict or set(data) != set(FIELDS) | {"home_id", "week", "mission"} | extra:
            raise ValueError("Unsupported snapshot fields.")
        if envelope["schema"] == 1 and type(data["appointment"]) is dict:
            data["appointment"].setdefault("location", "")
        candidate = Household()
        for key in FIELDS:
            template = getattr(candidate, key)
            if key == "transport":
                template = {"status": "", "person": None, "for_date": None}
            _shape(data[key], template)
        if min(data["revision"], data["context_revision"]) < 0:
            raise ValueError("Invalid saved revision.")
        if data["home_id"] not in ("demo", "sketch"):
            raise ValueError("Unknown saved house.")
        date.fromisoformat(data["appointment"]["date"])
        for key in ("time", "pickup"):
            datetime.strptime(data["appointment"][key], "%H:%M")
        if data["documents"]["status"] not in ("confirmed", "last_known") or data["transport"]["status"] not in ("confirmed", "needs_confirmation", "declined"):
            raise ValueError("Invalid shared fact status.")
        for key in ("person", "for_date"):
            if data["transport"][key] is not None and type(data["transport"][key]) is not str:
                raise ValueError("Invalid saved transport evidence.")
        if data["transport"]["for_date"] is not None:
            date.fromisoformat(data["transport"]["for_date"])
        outing = data["outing"]
        if (outing["choice"] not in ("undecided", "joined", "declined")
                or outing["support"] not in ("not_requested", "requested", "confirmed")
                or outing["completed_steps"] not in ([], ["invitation"], ["invitation", "bag"], ["invitation", "bag", "entrance"])
                or outing["position"] not in ("invitation", "bag", "entrance")):
            raise ValueError("Invalid saved practice state.")
        week = data["week"]
        _shape(week, {key: value for key, value in vars(candidate.week).items() if key != "host"})
        if week["profile"]["id"] not in {item["id"] for item in PROFILES} or any(week["profile"][key] not in values for key, values in PROFILE_FIELDS.items()):
            raise ValueError("Invalid saved profile.")
        if (week["mode"] not in ("manual", "assisted") or not 0 <= week["permissions"]["supply_cap"] <= 100
                or any(item not in SCENARIOS for item in week["injected"])):
            raise ValueError("Invalid saved week settings.")
        enums = [(week["appointment_status"], ("acknowledged", "conflict", "selected")),
                 (week["selected_slot"], (None, "keep_activity", "keep_appointment")),
                 (week["return_status"], ("not_recorded", "needs_confirmation", "requested", "confirmed", "declined")),
                 (week["supplies"]["status"], ("stocked", "needs_order", "ordered", "delivered", "placed", "declined")),
                 (week["community"]["status"], ("confirmed", "cancel_pending", "decision_pending", "free", "alternative_selected")),
                 (week["community"]["arrangement"], ("confirmed", "cancel_pending", "cancelled")),
                 (week["community"]["choice"], (None, "free", "alternative")),
                 (week["comfort"]["status"], ("no_request", "decision_pending", "chosen", "requested", "reported", "helped", "unresolved", "declined")),
                 (week["comfort"]["observation"], (None, "missing_reading", "awkward_reach")),
                 (week["comfort"]["choice"], (None, "storage", "equipment", "check", "leave"))]
        if any(value not in allowed for value, allowed in enums):
            raise ValueError("Invalid saved week state.")
        if week["comfort"]["helped"] is not None and type(week["comfort"]["helped"]) is not bool:
            raise ValueError("Invalid comfort report.")
        for key in ("appointment_version", "backup_version", "return_version"):
            value = week[key]
            if value is not None and (type(value) is not int or not 1 <= value <= 1_000_000):
                raise ValueError("Invalid saved appointment version.")
        if week["return_person"] is not None and type(week["return_person"]) is not str:
            raise ValueError("Invalid return actor.")
        if (any(leg not in ("outbound", "return") for leg in week["requested_legs"])
                or len(week["requested_legs"]) != len(set(week["requested_legs"]))):
            raise ValueError("Invalid requested travel legs.")
        if (week["appointment_status"] == "selected" and week["selected_slot"] is None
                or week["community"]["status"] == "alternative_selected" and week["community"]["choice"] != "alternative"):
            raise ValueError("Saved plan has no matching choice.")
        for event in week["history"]:
            _shape(event, {"participant": "", "category": "", "text": "", "revision": 0})
            if event["participant"] not in ("resident", "family", "agent"):
                raise ValueError("Unknown event actor.")
            if event["category"] not in ("setup", "decision", "reply", "administration", "supervision", "correction"):
                raise ValueError("Unknown event category.")
        for item in data["mission_proposals"]:
            _shape(item, {"action": "", "reason": "", "accepted": False, "result": "", "rejection": None,
                          "revision": 0, "actor": "", "engine": ""})
            if item["rejection"] not in (None, "stale", "invalid") or item["actor"] != "Astra coordinator":
                raise ValueError("Invalid saved proposal audit.")
        if len(data["mission_proposals"]) > 40:
            raise ValueError("Too many proposal records.")
        for key in FIELDS:
            setattr(candidate, key, deepcopy(data[key]))
        candidate.home = home_context(data["home_id"])
        for key, value in week.items():
            setattr(candidate.week, key, deepcopy(value))
        candidate.mission = Mission.restore(candidate, data["mission"])
        if envelope["schema"] >= 2:
            candidate.coordination = Coordination.restore(candidate, data["coordination"])
            candidate.meal = Meal.restore(candidate, data["meal"])
            candidate.hospital = Hospital.restore(candidate, data["hospital"])
            candidate.assessment = Assessment.restore(candidate, data["assessment"])
            if envelope["schema"] == 3:
                candidate.family_edition = FamilyEdition.restore(candidate, data["family_edition"])
        else:
            # New domains start from the restored plan, without replaying its actions.
            candidate.coordination = Coordination(candidate)
            candidate.meal = Meal(candidate)
            candidate.hospital = Hospital(candidate)
            candidate.assessment = Assessment(candidate)
        # Preserve saved evidence; normalize only four exact old display seeds.
        if candidate.appointment["reason"] == "Private follow-up — synthetic example":
            candidate.appointment["reason"] = "Follow-up visit"
        if candidate.week.appointment_evidence == "Appointment moved through the existing fictional appointment control.":
            candidate.week.appointment_evidence = "Appointment time updated."
        if candidate.week.community["evidence"] == "Fictional chosen activity and its own arrangements accepted.":
            candidate.week.community["evidence"] = "Chosen activity and its arrangements accepted."
        if candidate.week.supplies["evidence"] == "Fictional starting supply is available.":
            candidate.week.supplies["evidence"] = "Paper towels are available at home."
        candidate._observed_memory_revision = candidate.coordination.state.get("memory_revision", 0)
        candidate.view("resident")
        candidate.view("family")
        candidate.coordinator_view()
        return candidate
    except (KeyError, TypeError, AttributeError, UnicodeError, RecursionError) as error:
        raise ValueError("Saved mission could not be validated.") from error
