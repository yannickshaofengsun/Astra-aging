"""Bounded household requests, mock services, and addressed human replies."""

from copy import deepcopy
from datetime import date, timedelta
from hashlib import sha256
import json
from math import isfinite
import re

from .assessment import DRAFT_SCHEMA


ACTORS = {"alex": "Alex", "morgan": "Morgan"}
ITEMS = {
    "paper_towels": {"label": "Paper towels", "unit_price": 9.0, "stock": 8},
    "dish_soap": {"label": "Dish soap", "unit_price": 5.0, "stock": 8},
    "laundry_detergent": {"label": "Laundry detergent", "unit_price": 14.0, "stock": 0},
}
WINDOWS = {"morning": {"label": "09:00–12:00", "available": True},
           "afternoon": {"label": "14:00–17:00", "available": True},
           "evening": {"label": "18:00–20:00", "available": False}}
APPOINTMENTS = {
    "thursday_1100": {"day": "Thursday", "date": "2026-09-17", "time": "11:00", "pickup": "10:15"},
    "friday_1000": {"day": "Friday", "date": "2026-09-18", "time": "10:00", "pickup": "09:15"},
}
MEMORY_INTENTS = ("remember_preference", "forget_preference")
INTENTS = ("order_supply", "change_delivery", "cancel_order", "change_appointment", "carry_help", "hospital_coordination", "prescription_refill", "assess_home", "schedule_reminder", *MEMORY_INTENTS, "clarify", "unsupported")
PROPOSAL_FIELDS = ("intent", "item", "quantity", "window", "order_id", "appointment_choice", "recipients", "helper", "room_id", "strategy", "summary", "question")
OPTIONAL_PROPOSAL_FIELDS = {"visit_helpers", "memory", "assessment_draft"}
HOSPITAL_INTENTS = ("hospital_coordination", "prescription_refill")
INTENT_FIELDS = {"order_supply": {"item", "window"}, "change_delivery": {"order_id", "window"},
    "cancel_order": {"order_id"}, "change_appointment": {"appointment_choice", "helper"}, "carry_help": {"helper"},
    "hospital_coordination": {"item", "helper", "visit_helpers"}, "prescription_refill": {"item", "helper"},
    "assess_home": {"item", "room_id", "strategy", "assessment_draft"}, "schedule_reminder": {"item"},
    "remember_preference": {"memory"}, "forget_preference": {"memory"}, "clarify": set(), "unsupported": set()}
BOOL_PERMISSIONS = ("orders", "order_changes", "calendar", "notify", "helper_requests")
PREFERENCES = {"delivery_window": ("morning", "afternoon"), "messages": ("brief", "detailed"), "routine": ("keep", "try")}
TERMINAL = ("completed", "failed", "cancelled", "superseded", "unsupported", "declined")
REQUEST_STATES = TERMINAL + ("interpreting", "ready", "running", "waiting_permission", "waiting_helper", "waiting_physical", "needs_clarification", "paused")
ID = re.compile(r"[A-Za-z0-9_-]{1,48}\Z")
DOMAIN_ID = re.compile(r"[A-Za-z0-9_.:-]{1,100}\Z")
MAX_REQUESTS, MAX_MESSAGES = 40, 100
TEXT_LIMITS = {"summary": 400, "question": 400, "item": 160}
PROPOSAL_SCHEMA = {"type": "object", "additionalProperties": False, "required": list(PROPOSAL_FIELDS),
    "properties": {**{key: {"type": "string", "maxLength": TEXT_LIMITS.get(key, 64)}
                      for key in PROPOSAL_FIELDS if key not in ("quantity", "recipients", "intent")},
                   "intent": {"type": "string", "enum": list(INTENTS)}, "quantity": {"type": "integer", "minimum": 1, "maximum": 3},
                   "visit_helpers": {"type": "object", "additionalProperties": False, "required": ["driver", "companion", "return"],
                       "properties": {key: {"type": "string", "enum": ["", *ACTORS]} for key in ("driver", "companion", "return")}},
                   "memory": {"type": "object", "additionalProperties": False, "required": ["key", "value", "audience"],
                       "properties": {"key": {"type": "string", "enum": list(PREFERENCES)},
                           "value": {"type": ["string", "null"], "enum": [None, *[v for choices in PREFERENCES.values() for v in choices]]},
                           "audience": {"type": "array", "maxItems": 3, "items": {"type": "string", "enum": ["resident", *ACTORS]}}}},
                   "assessment_draft": DRAFT_SCHEMA,
                   "recipients": {"type": "array", "maxItems": 2, "items": {"type": "string", "enum": list(ACTORS)}}}}


def _request(request_id, text, day, appointment_version, replacement):
    return {"id": request_id, "text": text, "replace_request_id": replacement,
            "source_digest": None, "memory_redacted": False,
            "status": "interpreting", "proposal": None, "phase": 0, "created_day": day, "day": day,
            "appointment_version": appointment_version, "order_id": "", "service": "none",
            "message_ids": [], "question": "", "summary": "Interpreting your request.", "error": "", "effects": []}


class Coordination:
    def __init__(self, host):
        self.host = host
        self.state = {"version": 0, "day": 1, "date": "2026-09-15", "setup_done": False,
                      "permissions": {**dict.fromkeys(BOOL_PERMISSIONS, False), "spend_cap": 40.0},
                      "preferences": {"delivery_window": "morning", "messages": "brief", "routine": "keep"},
                      "actors": {key: {"name": name, "day": 1, "available": bool(host.week.profile["helper_available"])} for key, name in ACTORS.items()},
                      "requests": [], "orders": [], "messages": [], "history": [], "feedback": [], "replies": [],
                      "clock_minute": 540, "reminders": [], "watch_visit_changes": False,
                      "preference_memory": {}, "availability": [], "memory_revision": 0, "memory_cutoff": 0,
                      "human_interactions": {"resident": 0, "alex": 0, "morgan": 0},
                      "shared": self._shared_facts()}

    @property
    def version(self):
        return self.state["version"]

    @property
    def day(self):
        return self.state["day"]

    @property
    def actors(self):
        return deepcopy(self.state["actors"])

    def availability_for(self, actor, on_date=None):
        """A dated declaration is not an acceptance of a particular duty."""
        on_date = self.state["date"] if on_date is None else on_date
        self._date(on_date, bounded=False)
        for report in self.state["availability"]:
            if (report["actor_id"] == actor and report["start_date"] <= on_date <= report["end_date"]
                    and report["reported_date"] <= on_date):
                return report["available"]
        person = self.state["actors"].get(actor)
        if person and on_date == self.state["date"] and person["day"] == self.day:
            return person["available"]
        return None

    def available(self, actor, on_date=None):
        return self.availability_for(actor, on_date) is True

    @staticmethod
    def _date(value, bounded=True):
        if not isinstance(value, str):
            raise ValueError("Use an ISO calendar date.")
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value or bounded and not date(2026, 9, 15) <= parsed <= date(2027, 9, 14):
            raise ValueError("Choose a date within this fictional household year.")
        return parsed

    def duty_date(self, message):
        if message["kind"] == "travel" or (message["kind"] == "hospital" and message["metadata"].get("kind") != "pickup"):
            return self.host.appointment["date"]
        return (date(2026, 9, 15) + timedelta(days=message["day"] - 1)).isoformat()

    def can_accept(self, message):
        target = self.duty_date(message)
        availability = self.availability_for(message["recipient"], target)
        # An explicit reply to a future dated duty supplies task-specific availability.
        return availability is True or availability is None and (
            target > self.state["date"] or message["kind"] == "hospital" and message["metadata"].get("kind") != "pickup")

    def _current_duty(self, message):
        request = self._get("requests", message["request_id"])
        return (self.duty_date(message) >= self.state["date"]
                and (message["kind"] != "travel" or request["appointment_version"] == self.host.week.appointment_version))

    def _retire_memory_request(self, request):
        if request["memory_redacted"]:
            return
        request.update(source_digest=sha256(request["text"].encode()).hexdigest(), memory_redacted=True,
                       text="[Removed memory source]", summary="Earlier preference source removed; its action record remains.", question="", error="")
        proposal = request["proposal"]
        proposal["memory"] = {"key": proposal["memory"]["key"], "value": None, "audience": []}
        proposal["summary"] = proposal["question"] = ""

    def _remember_preferences(self, values, audience=None, source_request_id=""):
        changed = False
        for key, value in values.items():
            previous = self.state["preference_memory"].get(key)
            shared_with = audience if audience is not None else previous["audience"] if previous else ["resident", *ACTORS]
            shared_with = sorted(shared_with) if value is not None else ["resident"]
            if previous and previous["value"] == value and sorted(previous["audience"]) == shared_with:
                continue
            changed = True
            for old in self.state["requests"]:
                if (old["id"] != source_request_id and old["status"] == "completed" and old["proposal"]
                        and old["proposal"]["intent"] in MEMORY_INTENTS and old["proposal"]["memory"]["key"] == key):
                    self._retire_memory_request(old)
            self.state["preference_memory"][key] = {
                "id": "preference-" + key, "subject": "resident", "key": key, "value": value,
                "audience": shared_with,
                "status": "current" if value is not None else "removed",
                "source": {"actor_id": "resident", "kind": "explicit_report", "date": self.state["date"],
                           "minute": self.state["clock_minute"], "revision": self.version + 1,
                           "request_id": source_request_id}}
            self.state["preferences"][key] = value
        if changed:
            self.state["memory_revision"] += 1
            self.state["memory_cutoff"] = len(self.state["requests"])
        return changed

    def _continuity_view(self, actor):
        memory = {key: record for key, record in self.state["preference_memory"].items() if actor in record["audience"]}
        preferences = {key: value for key, value in self.state["preferences"].items()
                       if key not in self.state["preference_memory"] or key in memory}
        return deepcopy({"preferences": preferences, "preference_memory": memory,
                         "availability": self.state["availability"], "memory_revision": self.state["memory_revision"]})

    def _request_context(self, request):
        result = deepcopy(request)
        if any(r["id"] == request["id"] for r in self.state["requests"][:self.state["memory_cutoff"]]):
            # Keep structured execution evidence; retired conversational text is not memory.
            result["text"] = "Earlier request text omitted after a memory change."
            result["summary"] = "Recorded task status: " + request["status"]
            result["question"] = result["error"] = ""
            if result["proposal"]:
                result["proposal"].pop("summary", None)
                result["proposal"].pop("question", None)
                result["proposal"].pop("memory", None)
        return result

    def _message_context(self, message):
        result = deepcopy(message)
        if any(r["id"] == message["request_id"] for r in self.state["requests"][:self.state["memory_cutoff"]]):
            result.pop("body", None)
        return result

    def model_view(self, role, actor_id=None):
        result = self.view(role, actor_id)
        result["requests"] = [self._request_context(r) for r in result["requests"]]
        for key in ("inbox", "outbox"):
            result[key] = [self._message_context(m) for m in result[key]]
        if self.state["memory_revision"]:
            result["history"] = [{k: v for k, v in h.items() if k != "text"} for h in result["history"]]
            result["replies"] = [{k: v for k, v in r.items() if k not in ("message", "question")} for r in result["replies"]]
        result.pop("controls", None)
        return result

    def _shared_facts(self):
        return {"appointment": {key: self.host.appointment[key] for key in ("date", "day", "time", "pickup")},
                "appointment_version": self.host.week.appointment_version,
                "transport": deepcopy(self.host.transport), "week_permissions": deepcopy(self.host.week.permissions),
                "support": {key: self.host.week.profile[key] for key in ("helper", "helper_available")}}

    @staticmethod
    def _clock_label(minute):
        return f"{minute // 60:02d}:{minute % 60:02d}"

    def _clock(self):
        return {"minute": self.state["clock_minute"], "display": self._clock_label(self.state["clock_minute"]),
                "basis": "Explicit demonstration clock; no real timer or task deadline is inferred."}

    def _pending(self, message):
        request = self._get("requests", message["request_id"])
        return (message["kind"] != "information" and message["status"] in ("available", "read")
                and self._current_duty(message) and request["status"] not in TERMINAL)

    def _check_reminder(self, message_id, hours):
        if type(hours) is not int or not 1 <= hours <= 3:
            raise ValueError("Agree a reminder delay of one to three hours.")
        target = self._get("messages", message_id)
        if not self._pending(target):
            raise ValueError("Choose one current unanswered responsibility for the named recipient.")
        old = next((r for r in self.state["reminders"] if r["target_message_id"] == message_id and r["status"] != "cancelled"), None)
        if old:
            if old["hours"] != hours:
                raise ValueError("Cancel the existing reminder before agreeing a different delay.")
            return target, old
        if len(self.state["reminders"]) >= 40 or self.state["clock_minute"] + hours * 60 > 1439:
            raise ValueError("The reminder must fit within this simulated day and its 40-reminder limit.")
        return target, None

    def _schedule_reminder(self, message_id, hours, source_request_id=None):
        target, old = self._check_reminder(message_id, hours)
        if old:
            return old
        reminder = {"id": "rem-" + str(len(self.state["reminders"]) + 1), "target_message_id": message_id,
                    "source_request_id": source_request_id, "recipient": target["recipient"], "day": self.day, "hours": hours,
                    "scheduled_minute": self.state["clock_minute"], "due_minute": self.state["clock_minute"] + hours * 60,
                    "status": "scheduled", "issued_minute": None, "receipt_id": "", "cancelled_day": None, "cancelled_minute": None}
        self.state["reminders"].append(reminder)
        return reminder

    def _cancel_reminder(self, reminder):
        reminder.update(status="cancelled", cancelled_day=self.day, cancelled_minute=self.state["clock_minute"])
        if reminder["receipt_id"]:
            self._get("messages", reminder["receipt_id"])["status"] = "cancelled"

    def _sync_reminders(self):
        for reminder in self.state["reminders"]:
            if reminder["status"] != "cancelled" and (not self.state["permissions"]["notify"]
                    or reminder["day"] != self.day or not self._pending(self._get("messages", reminder["target_message_id"]))):
                self._cancel_reminder(reminder)

    def _post_information(self, request, recipient, key, body):
        identity = request["id"] + "-" + key + "-" + recipient
        old = next((m for m in self.state["messages"] if m["id"] == identity), None)
        if old:
            return identity
        if len(self.state["messages"]) >= MAX_MESSAGES or len(request["message_ids"]) >= 12:
            raise ValueError("The bounded household inbox is full.")
        self.state["messages"].append({"id": identity, "request_id": request["id"], "recipient": recipient,
            "kind": "information", "body": body[:600], "status": "available", "day": self.day,
            "available_day": self.day, "read_day": None, "response_day": None, "completed_day": None, "metadata": {}})
        request["message_ids"].append(identity)
        return identity

    def _hospital_updates(self, request):
        p = request["proposal"]
        context = self.host.hospital.context()
        domain = next((r for r in context["requests"] if r["id"] == request["id"]), None)
        visit = p["intent"] == "hospital_coordination"
        source = context["retrieved_visit" if visit else "retrieved_pharmacy"]
        if (not p["recipients"] or not source or not domain or domain["source_version"] != source["source_version"]
                or visit and domain["phase"] in ("retrieve", "reconcile") or domain["status"] in ("cancelled", "stale")):
            return []
        key = "notice-" + p["item"] + "-v" + str(source["source_version"])
        if visit:
            appointment = source["appointment"]
            body = (f"Hospital notice version {source['source_version']} reconciled: {appointment['date']} {appointment['time']} at {appointment['location']}. "
                    "Driving, companionship, and return responsibilities are tracked separately. This information update does not accept a duty or report physical completion.")
        else:
            body = (f"Retrieved pharmacy administration update, version {source['source_version']}: {source['status'].replace('_', ' ')}. "
                    "Pickup agreement, collection, and delivery are separate; this information update establishes none of them.")
        existing = {m["id"] for m in self.state["messages"]}
        return [(actor, key, body) for actor in p["recipients"] if request["id"] + "-" + key + "-" + actor not in existing]

    def _touch(self, actor, event, text):
        self._sync_reminders()
        self.state["version"] += 1
        if actor in self.state["human_interactions"] and (event in ("request", "correction", "setup", "natural_reply")
                or event.startswith("coordination_") and event not in ("coordination_next_day", "coordination_advance_clock")):
            self.state["human_interactions"][actor] += 1
        self.state["history"].append({"day": self.day, "minute": self.state["clock_minute"], "actor": actor, "event": event, "text": text})
        self.state["history"] = self.state["history"][-120:]
        self.state["shared"] = self._shared_facts()

    def _get(self, collection, identity):
        value = next((item for item in self.state[collection] if item["id"] == identity), None)
        if value is None:
            raise ValueError("That household record is not available.")
        return value

    def _actor(self, role, actor_id):
        if role == "resident":
            return "resident"
        if role != "family" or (actor_id or "alex") not in ACTORS:
            raise ValueError("Choose the resident, Alex, or Morgan perspective.")
        return actor_id or "alex"

    def begin(self, request_id, text, replace_request_id=None, *, initiated_by="resident"):
        if type(initiated_by) is not str or initiated_by not in ("resident", "coordinator"):
            raise ValueError("Only a resident request or an internal coordinator event may start coordination.")
        if not isinstance(request_id, str) or not ID.fullmatch(request_id):
            raise ValueError("Use a unique request ID of at most 48 letters, numbers, underscores, or dashes.")
        if not isinstance(text, str) or not text.strip() or len(text) > 2000:
            raise ValueError("Describe the household request in 1–2000 characters.")
        old = next((r for r in self.state["requests"] if r["id"] == request_id), None)
        if old:
            same_text = (old["source_digest"] == sha256(text.strip().encode()).hexdigest()
                         if old["memory_redacted"] else old["text"] == text.strip())
            if not same_text or old["replace_request_id"] != replace_request_id:
                raise ValueError("That request ID already belongs to different text. Use a new ID for a correction.")
            return {"request": deepcopy(old), "duplicate": True}
        if len(self.state["requests"]) >= MAX_REQUESTS:
            raise ValueError("This saved demonstration has reached its 40-request limit; start a new household to continue.")
        previous = None
        if replace_request_id is not None:
            if not isinstance(replace_request_id, str) or not ID.fullmatch(replace_request_id):
                raise ValueError("Choose a valid request to correct.")
            previous = self._get("requests", replace_request_id)
        if previous and previous["status"] not in TERMINAL:
            self._cancel(previous, "superseded")
        request = _request(request_id, text.strip(), self.day, self.host.week.appointment_version, replace_request_id)
        self.state["requests"].append(request)
        if initiated_by == "coordinator":
            self._touch("coordinator", "proactive_request", "Coordinator started a request after a household event.")
        else:
            self._touch("resident", "correction" if previous else "request", "Resident corrected a request." if previous else "Resident made a household request.")
        return {"request": deepcopy(request), "duplicate": False}

    def context(self, request_id):
        request = self._get("requests", request_id)
        meal = self.host.meal.help_context() if hasattr(self.host, "meal") else {"can_request": False, "reason": "Meal routine is unavailable."}
        return deepcopy({"version": self.version, "request": self._request_context(request), "day": self.day, "date": self.state["date"],
            "permissions": self.state["permissions"], **self._continuity_view("resident"), "actors": self.state["actors"],
            "appointment": self._shared_facts()["appointment"], "appointment_version": self.host.week.appointment_version,
            "orders": self.state["orders"], "meal": meal,
            "clock": self._clock(), "reminders": self.state["reminders"],
            "pending_responsibilities": [self._message_context(m) for m in self.state["messages"] if self._pending(m)],
            "recent_requests": [self._request_context(r)
                                for r in self.state["requests"] if r["id"] != request_id][-6:],
            "hospital": self.host.hospital.context() if hasattr(self.host, "hospital") else None,
            "assessment": (self.host.assessment.context() if hasattr(self.host.assessment, "context") else self.host.assessment.view("resident")) if hasattr(self.host, "assessment") else None,
            "fixtures": {"items": ITEMS, "delivery_windows": WINDOWS, "appointment_choices": APPOINTMENTS},
            "proposal_schema": PROPOSAL_SCHEMA,
            "intent_fields": {intent: sorted(fields) for intent, fields in INTENT_FIELDS.items()},
            "proposal_help": {"fields": list(PROPOSAL_FIELDS), "intents": list(INTENTS), "quantity": "integer 1–3",
                "optional_fields": sorted(OPTIONAL_PROPOSAL_FIELDS),
                "memory": "Only explicit resident remember_preference/forget_preference requests use memory={key,value,audience}. "
                    "Remember uses an existing typed choice and an explicitly selected audience including resident; private means [resident]. "
                    "Forget uses null value and empty audience. Never infer a permanent preference from a one-time order. "
                    "Other fields are empty strings; recipients is empty and quantity is 1. A missing sharing scope needs clarification.",
                "visit_helpers": "Only hospital_coordination may include {driver,companion,return}. Each value names alex or morgan; empty entries use helper. Omit the map for an unchanged single-helper request. A fully named map permits helper=''.",
                "recipients": list(ACTORS), "irrelevant_text_fields": "empty string",
                "helper": "alex or morgan for change_appointment/carry_help/hospital_coordination/prescription_refill; empty otherwise",
                "home_assessment": "assess_home can save explicitly stated fields using sparse assessment_draft. Omitted fields preserve the current draft; null clears a nullable fact. "
                    "Choose need from assessment.needs and room IDs from assessment.rooms. Only stated dimensions are recorded, always as reported. "
                    "Use catalog_products for a newly stated need; select only a matching sourced product with no conflict against the proposed constraints. "
                    "Strategy and room_id may be empty while gathering details. A concise question may accompany useful draft fields, with empty item and recipients. "
                    "For replace, item may be an exact sourced product ID with quantity and room_id; keep/relocate/adapt require empty item. "
                    "No strategy means preserve the existing approach, not a new resident decision. Setup is an intention, never acceptance. A product is a review draft, never a purchase or verified fit.",
                "reminders": "schedule_reminder uses item=one exact pending responsibility message ID and quantity=agreed hours 1–3; recipients/helper are empty because the target fixes recipient and topic."},
            "instruction": "Interpret only the stated request using supplied identifiers. Ask a clarification if a required item, "
                "order, recipient, helper, or appointment choice is unclear. Use the saved delivery preference only when no window "
                "was specified; a removed/null preference is unknown and needs a choice when required. "
                "Dated availability applies only within the reported dates and never establishes task acceptance. "
                "Do not recover retired preferences from old requests or completed order details. "
                "intent_fields is authoritative: use empty strings for all intent-specific fields not listed for the chosen intent; "
                "hospital_coordination uses item+helper and optional visit_helpers, never appointment_choice, room_id, or strategy. "
                "Use visit_helpers for an explicit split of driving, companionship, and return duties, or to preserve a known current split when the notice changes. "
                "Otherwise the named hospital helper initially receives three separate driving, companionship, and return responsibilities; "
                "one person may accept multiple duties, and an authorized backup follows only a specifically declined duty. "
                "Do not create a new whole-visit request for an already-pending backup. For a clear explicit request, interpret the intent even if standing permissions are missing; "
                "Python will stop at waiting_permission. Do not ask redundant permission questions. For assess_home, compare assessment.evaluated_candidates (available even while keeping an existing item) with budget, space, "
                "existing-item preferences and accepted setup responsibility. Never select an option with a known conflict. Unknown fit or fees stays an explicit review draft. "
                "Schedule a reminder only for the stated named person's exact pending responsibility and explicitly agreed delay; ambiguous topic or delay needs clarification. "
                "Mock service fixtures establish outcomes independently. Never claim a human read, accepted, or "
                "completed something. Resolve short replies only against an identified recent question or request; an ambiguous yes "
                "cannot grant permissions or impersonate a helper reply. Existing appointment reasons and medical details are not supplied."})

    def _validate_proposal(self, proposal, request, restoring=False):
        if (not isinstance(proposal, dict) or not set(PROPOSAL_FIELDS) <= set(proposal)
                or set(proposal) - set(PROPOSAL_FIELDS) - OPTIONAL_PROPOSAL_FIELDS):
            raise ValueError("The interpretation did not match the bounded request format.")
        if proposal["intent"] not in INTENTS or type(proposal["quantity"]) is not int or not 1 <= proposal["quantity"] <= 3:
            raise ValueError("Use a supported intent and quantity from one to three.")
        for key in set(PROPOSAL_FIELDS) - {"quantity", "recipients"}:
            if not isinstance(proposal[key], str) or len(proposal[key]) > TEXT_LIMITS.get(key, 64):
                raise ValueError("Interpretation text is invalid or too long.")
        recipients = proposal["recipients"]
        if not isinstance(recipients, list) or len(recipients) > 2 or any(r not in ACTORS for r in recipients) or len(set(recipients)) != len(recipients):
            raise ValueError("Address only Alex or Morgan, once each.")
        intent = proposal["intent"]
        if "assessment_draft" in proposal:
            if intent != "assess_home":
                raise ValueError("Only an equipment request may supply assessment draft fields.")
            # Restore validates shape and values independently of the current need/room.
            if restoring:
                self.host.assessment.validate_draft(proposal["assessment_draft"])
        if intent in MEMORY_INTENTS:
            self._memory_payload(proposal.get("memory"), forget=intent == "forget_preference" or restoring and request["memory_redacted"])
            if recipients or proposal["quantity"] != 1:
                raise ValueError("Remembering a preference does not send a notification or order anything.")
        elif "memory" in proposal:
            raise ValueError("Only a preference request may supply memory.")
        visit_helpers = proposal.get("visit_helpers")
        if "visit_helpers" in proposal and (intent != "hospital_coordination" or not isinstance(visit_helpers, dict)
                or set(visit_helpers) != {"driver", "companion", "return"}
                or any(type(value) is not str or value not in ("", *ACTORS) for value in visit_helpers.values())
                or any(not value for value in visit_helpers.values()) and proposal["helper"] not in ACTORS):
            raise ValueError("Name each hospital duty separately; an empty duty must use a named helper fallback.")
        used = INTENT_FIELDS[intent]
        if any(proposal[key] for key in ("item", "window", "order_id", "appointment_choice", "helper", "room_id", "strategy") if key not in used):
            raise ValueError("The interpretation mixed unrelated actions; correct the request.")
        if intent in ("clarify", "unsupported"):
            if not proposal["question"] and intent == "clarify":
                raise ValueError("A clarification needs a specific question.")
            return
        if proposal["question"] and not (intent == "assess_home" and proposal.get("assessment_draft")
                                         and not recipients and not proposal["item"]):
            raise ValueError("A request needing clarification cannot execute effects.")
        if intent == "order_supply" and proposal["item"] not in ITEMS or "window" in used and proposal["window"] not in WINDOWS:
            raise ValueError("Choose a supplied household item and delivery window.")
        if "appointment_choice" in used and proposal["appointment_choice"] not in APPOINTMENTS:
            raise ValueError("Choose a supplied appointment alternative.")
        if "helper" in used and proposal["helper"] not in ACTORS and not (
                intent == "hospital_coordination" and visit_helpers and proposal["helper"] == "" and all(visit_helpers.values())):
            raise ValueError("Name Alex or Morgan for the requested responsibility.")
        if "order_id" in used and not restoring:
            order = self._get("orders", proposal["order_id"])
            if order["status"] != "acknowledged":
                raise ValueError("Only an acknowledged, undelivered order can be changed or cancelled.")
        if not restoring and intent == "carry_help" and (not hasattr(self.host, "meal") or not self.host.meal.help_context()["can_request"]):
            raise ValueError("Carrying help is unavailable at this point in the meal routine.")
        if intent in HOSPITAL_INTENTS:
            if (not restoring and not hasattr(self.host, "hospital")) or proposal["item"] != ("visit-001" if intent == "hospital_coordination" else "rx-001"):
                raise ValueError("Use a supplied hospital notice or existing prescription identifier.")
        if intent == "assess_home":
            if proposal["strategy"] not in ("", "keep", "relocate", "adapt", "replace") or proposal["item"] and proposal["strategy"] != "replace":
                raise ValueError("Select a product only for replacement; keep, relocate, and adapt use the existing item.")
            if not restoring:
                self._assessment_evaluation(proposal, self._proposed_assessment(proposal))
        if intent == "schedule_reminder":
            if recipients:
                raise ValueError("The reminder target fixes its recipient; do not address extra people.")
            if not restoring:
                self._check_reminder(proposal["item"], proposal["quantity"])
        if not restoring and intent == "order_supply" and request["replace_request_id"]:
            previous = self._get("requests", request["replace_request_id"])
            if previous["order_id"] and self._get("orders", previous["order_id"])["status"] in ("acknowledged", "delivered", "placed"):
                raise ValueError("That correction refers to an existing order. Change or cancel it instead of creating another order.")
        if not restoring and len(self.state["messages"]) + len(set(recipients + ([proposal["helper"]] if proposal["helper"] else []))) > MAX_MESSAGES:
            raise ValueError("The saved demonstration inbox is full; no new effects were started.")

    def _assessment_evaluation(self, proposal, assessment=None):
        if not hasattr(self.host, "assessment"):
            raise ValueError("The home assessment is unavailable.")
        assessment = assessment or self.host.assessment
        view = assessment.view("resident")
        if (proposal["room_id"] or proposal["item"]) and proposal["room_id"] not in {room["id"] for room in view["rooms"]}:
            raise ValueError("Choose a current room for the assessment draft.")
        if not proposal["item"]:
            return None
        context = assessment.context() if hasattr(assessment, "context") else view
        if proposal["item"] not in {candidate["id"] for candidate in context.get("evaluated_candidates", context.get("candidates", []))}:
            raise ValueError("Choose an exact sourced candidate for the current household need.")
        evaluation = assessment.evaluate(proposal["item"], proposal["quantity"], proposal["room_id"])
        conflicts = [check["reason"] for check in evaluation["checks"].values() if check["status"] == "conflict"]
        if evaluation["status"] == "conflict" or conflicts:
            raise ValueError("The candidate conflicts with recorded household constraints: " + "; ".join(conflicts)[:400])
        return evaluation

    def _proposed_assessment(self, proposal):
        assessment = self.host.assessment
        proposed = (assessment.proposed(proposal["assessment_draft"]) if "assessment_draft" in proposal
                    else type(assessment).restore(self.host, assessment.dump()))
        if proposal["strategy"] and proposed.state["strategy"] != proposal["strategy"]:
            proposed.apply("assessment_strategy", "resident", {"strategy": proposal["strategy"]})
        return proposed

    def _prepare_assessment(self, proposal):
        proposed = self._proposed_assessment(proposal)
        self._assessment_evaluation(proposal, proposed)
        if proposal["item"]:
            desired = {"option_id": proposal["item"], "quantity": proposal["quantity"], "room_id": proposal["room_id"]}
            saved = next((item for item in proposed.state["selections"] if item["option_id"] == proposal["item"]), None)
            if saved is None or any(saved[key] != value for key, value in desired.items()) or saved["home_id"] != self.host.home["id"]:
                if saved is not None:
                    proposed.apply("assessment_remove", "resident", {"option_id": proposal["item"]})
                proposed.apply("assessment_add", "resident", desired)
        self.host.assessment.state = proposed.dump()

    def reply_context(self, actor_id):
        actor = self._actor("family", actor_id)
        inbox = [self._message_context(m) for m in self.view("family", actor)["inbox"] if self._pending(m)]
        schema = {"type": "object", "additionalProperties": False, "required": ["decisions", "question"],
            "properties": {"question": {"type": "string", "maxLength": 400}, "decisions": {"type": "array", "maxItems": 3,
                "items": {"type": "object", "additionalProperties": False, "required": ["message_id", "status"],
                    "properties": {"message_id": {"type": "string", "enum": [m["id"] for m in inbox] or [""]},
                                   "status": {"type": "string", "enum": ["accepted", "declined"]}}}}}}
        return deepcopy({"version": self.version, "day": self.day, "actor_id": actor, "actor": self.state["actors"][actor],
            "inbox": inbox, "reply_schema": schema, **self._continuity_view(actor),
            "instruction": "Interpret only this named person's explicit response to their own supplied responsibilities. "
                "Driving, in-hospital companionship, return travel and carrying are distinct. Leave unmentioned responsibilities pending. "
                "An ambiguous yes produces a question and zero decisions. Never widen household permissions or claim physical completion."})

    def apply_reply(self, reply_id, actor_id, message, proposal, expected_version):
        actor = self._actor("family", actor_id)
        if not isinstance(reply_id, str) or not ID.fullmatch(reply_id) or not isinstance(message, str) or not 1 <= len(message.strip()) <= 2000:
            raise ValueError("Use a bounded unique reply ID and response text.")
        old = next((r for r in self.state["replies"] if r["id"] == reply_id), None)
        if old:
            if old["actor_id"] != actor or old["message"] != message.strip():
                raise ValueError("That reply ID belongs to another response.")
            return deepcopy(old)
        if len(self.state["replies"]) >= 40:
            raise ValueError("The saved reply limit has been reached.")
        if type(expected_version) is not int or expected_version != self.version:
            raise ValueError("Responsibilities changed while interpreting the reply.")
        if (not isinstance(proposal, dict) or set(proposal) != {"decisions", "question"}
                or not isinstance(proposal["question"], str) or len(proposal["question"]) > 400
                or not isinstance(proposal["decisions"], list) or len(proposal["decisions"]) > 3):
            raise ValueError("Use a bounded responsibility reply.")
        decisions = proposal["decisions"]
        if proposal["question"] and decisions or not proposal["question"] and not decisions:
            raise ValueError("Ask one clarification or supply explicit responsibility decisions.")
        eligible = {m["id"]: m for m in self.reply_context(actor)["inbox"]}
        seen = set()
        for decision in decisions:
            if (not isinstance(decision, dict) or set(decision) != {"message_id", "status"}
                    or not isinstance(decision["message_id"], str) or decision["message_id"] not in eligible
                    or decision["message_id"] in seen or decision["status"] not in ("accepted", "declined")):
                raise ValueError("Respond only once to a current responsibility addressed to this person.")
            seen.add(decision["message_id"])
            if decision["status"] == "accepted" and not self.can_accept(eligible[decision["message_id"]]):
                raise ValueError("Resolve this person's availability for the responsibility's date before accepting.")
        # One natural reply may address multiple domains. Roll back all callback facts
        # if any later decision is rejected; never leave half of a reply accepted.
        saved = self.dump()
        transport = deepcopy(self.host.transport)
        week = {key: deepcopy(value) for key, value in vars(self.host.week).items() if key != "host"}
        domains = {key: getattr(self.host, key).dump() for key in ("meal", "hospital") if hasattr(self.host, key)}
        try:
            for decision in decisions:
                self._reply(self._get("messages", decision["message_id"]), decision["status"])
        except ValueError:
            self.state = saved
            self.host.transport = transport
            vars(self.host.week).update(week)
            for key, snapshot in domains.items():
                getattr(self.host, key).state = snapshot
            raise
        record = {"id": reply_id, "actor_id": actor, "message": message.strip(), "decisions": deepcopy(decisions),
                  "question": proposal["question"], "day": self.day}
        self.state["replies"].append(record)
        self._touch(actor, "natural_reply", "Named person replied to their own responsibilities." if decisions else "A specific clarification is needed; no responsibility changed.")
        return deepcopy(record)

    def accept(self, request_id, proposal, expected_version):
        request = self._get("requests", request_id)
        if type(expected_version) is not int or expected_version != self.version or request["status"] != "interpreting":
            raise ValueError("The household or request changed during interpretation. Correct or resume using current facts.")
        self._validate_proposal(proposal, request)
        request["proposal"] = deepcopy(proposal)
        request["summary"] = proposal["summary"] or "Request interpreted."
        request["question"] = proposal["question"]
        request["status"] = {"clarify": "needs_clarification", "unsupported": "unsupported"}.get(proposal["intent"], "ready")
        self._touch("astra", "proposal", "Astra supplied a validated interpretation; no outcome is inferred from the proposal.")
        return deepcopy(request)

    def _permission_problem(self, request):
        p, permissions = request["proposal"], self.state["permissions"]
        intent = p["intent"]
        if intent in (*HOSPITAL_INTENTS, *MEMORY_INTENTS):
            return ""  # The hospital domain validates its narrower supplied permissions per step.
        if request["phase"] <= 1:
            key = {"order_supply": "orders", "change_delivery": "order_changes", "cancel_order": "order_changes",
                   "change_appointment": "calendar", "carry_help": "helper_requests", "assess_home": None,
                   "schedule_reminder": "notify"}[intent]
            if key and not permissions[key]:
                return "Allow this type of routine task or cancel the request."
            if intent == "order_supply" and ITEMS[p["item"]]["unit_price"] * p["quantity"] > permissions["spend_cap"]:
                return "The supplied total exceeds the saved per-order spending cap."
        if request["phase"] in (2, 3) and (p["recipients"] or p["helper"]):
            if not permissions["notify"]:
                return "Permission to send addressed household updates is missing."
            if p["helper"] and not permissions["helper_requests"]:
                return "Permission to request a helper's responsibility is missing."
        return ""

    def advance(self, request_id):
        request = self._get("requests", request_id)
        hospital = request["proposal"] is not None and request["proposal"]["intent"] in HOSPITAL_INTENTS
        if request["status"] in TERMINAL + ("interpreting", "needs_clarification", "waiting_physical", "paused") or request["status"] == "waiting_helper" and not hospital:
            return False
        problem = self._permission_problem(request)
        if problem:
            if request["status"] == "waiting_permission" and request["question"] == problem:
                return False
            request.update(status="waiting_permission", question=problem)
            self._touch("coordinator", "waiting", problem)
            return True
        p, phase = request["proposal"], request["phase"]
        if p["intent"] in MEMORY_INTENTS:
            memory = p["memory"]
            self._memory_payload(memory, forget=p["intent"] == "forget_preference")
            self._remember_preferences({memory["key"]: memory["value"]}, memory["audience"], request["id"])
            request.update(status="completed", phase=1, service="prepared", summary="Preference "
                           + ("removed" if p["intent"] == "forget_preference" else "recorded with its sharing scope")
                           + ". No task or spending permission changed.", effects=["preference_recorded"])
            if p["intent"] == "forget_preference":
                self._retire_memory_request(request)
            self._touch("coordinator", "preference_recorded", request["summary"])
            return True
        if p["intent"] == "schedule_reminder":
            reminder = self._schedule_reminder(p["item"], p["quantity"], request["id"])
            request.update(status="completed", phase=1, service="prepared", summary="Agreed reminder scheduled for "
                           + ACTORS[reminder["recipient"]] + " at " + self._clock_label(reminder["due_minute"]) + "; responsibility remains pending.")
            request["effects"] = ["reminder_scheduled"]
            self._touch("coordinator", "reminder_scheduled", request["summary"])
            return True
        if p["intent"] in HOSPITAL_INTENTS:
            result = (self.host.hospital.start_request(request["id"], p) if phase == 0
                      else self.host.hospital.advance_request(request["id"]))
            if not isinstance(result, dict) or type(result.get("changed")) is not bool or result.get("status") not in REQUEST_STATES:
                raise ValueError("Hospital returned an invalid bounded-step result.")
            updates = self._hospital_updates(request)
            if updates and not self.state["permissions"]["notify"]:
                result = {**result, "status": "waiting_permission", "result": "The administrative facts remain recorded; permission to send the requested named information update is missing."}
            elif updates:
                for recipient, key, body in updates:
                    self._post_information(request, recipient, key, body)
                result = {**result, "changed": True}
            status_changed = request["status"] != result["status"] or request["summary"] != result.get("result", "")[:400]
            request.update(status=result["status"], summary=result.get("result", "")[:400], phase=1)
            if result["changed"] or status_changed:
                self._touch("hospital", "step", request["summary"])
                return True
            return False
        if (p["intent"] in ("change_appointment", "carry_help") and request["day"] != self.day
                and not any(m["request_id"] == request_id and self._current_duty(m)
                            and m["status"] in ("available", "read", "accepted") for m in self.state["messages"])):
            request.update(status="paused", question="This responsibility belonged to an earlier day. Make a current request.")
            self._touch("coordinator", "paused", request["question"])
            return True
        if p["intent"] == "change_appointment" and request["appointment_version"] != self.host.week.appointment_version:
            request.update(status="paused", question="The shared appointment changed. Correct this request using the current appointment.")
            self._touch("coordinator", "paused", request["question"])
            return True
        if p["intent"] == "assess_home":
            if phase == 0:
                self._prepare_assessment(p)
                if p["question"]:
                    request.update(status="needs_clarification", phase=1, service="prepared",
                                   summary=self._outcome_text(request), question=p["question"], effects=["assessment_prepared"])
                    self._touch("coordinator", "assessment_prepared", request["summary"])
                    return True
            else:
                self._assessment_evaluation(p)
                draft = self.host.assessment.dump()
                if p["strategy"] and draft["strategy"] != p["strategy"] or p["item"] and not any(
                        item["option_id"] == p["item"] and item["quantity"] == p["quantity"]
                        and item["room_id"] == p["room_id"] and item["home_id"] == self.host.home["id"]
                        for item in draft["selections"]):
                    raise ValueError("The assessment draft changed. Make a current request before sending its review.")
        request.update(status="running", question="")
        if phase == 0:
            if p["intent"] == "order_supply":
                identity = "ord-" + request["id"]
                order = {"id": identity, "request_id": request["id"], "item": p["item"], "quantity": p["quantity"],
                         "window": p["window"], "cost": ITEMS[p["item"]]["unit_price"] * p["quantity"],
                         "status": "requested", "day": self.day, "acknowledged_day": None, "delivered_by": "", "placed_by": "",
                         "evidence": "Order request sent to the mock store; acknowledgment is pending."}
                self.state["orders"].append(order)
                request["order_id"] = identity
            elif p["intent"] in ("change_delivery", "cancel_order"):
                request["order_id"] = p["order_id"]
            elif p["intent"] == "carry_help":
                self.host.meal.request_help(request["id"], p["helper"])
            request["service"] = "requested"
            request["effects"].append("request_sent")
        elif phase == 1:
            self._service_reply(request)
        elif phase == 2:
            self._send_messages(request)
        elif phase == 3:
            for identity in request["message_ids"]:
                message = self._get("messages", identity)
                if message["status"] == "sent":
                    message.update(status="available", available_day=self.day)
        else:
            if request["service"] == "refused":
                request["status"] = "failed"
            elif p["helper"]:
                request.update(status="waiting_helper", summary="The addressed helper request is available; acceptance is pending.")
            else:
                request.update(status="completed", summary=self._outcome_text(request))
        request["phase"] = min(5, phase + 1)
        self._touch("coordinator", "step", self._outcome_text(request))
        return True

    def _service_reply(self, request):
        p, intent = request["proposal"], request["proposal"]["intent"]
        if intent == "carry_help":
            return  # A human helper supplies the response; Astra and the mock store cannot.
        if intent == "assess_home":
            request["service"] = "prepared"
            request["effects"].append("assessment_prepared")
            return
        refusal = ""
        if intent == "order_supply":
            ordered = sum(o["quantity"] for o in self.state["orders"] if o["item"] == p["item"]
                          and o["day"] == self.day and o["status"] in ("acknowledged", "delivered", "placed"))
            if ordered + p["quantity"] > ITEMS[p["item"]]["stock"]:
                refusal = "The mock store refused the request because supplied stock is unavailable."
            elif not WINDOWS[p["window"]]["available"]:
                refusal = "The mock store refused the supplied delivery window."
            order = self._get("orders", request["order_id"])
            order.update(status="refused" if refusal else "acknowledged", acknowledged_day=None if refusal else self.day,
                         evidence=refusal or "Mock store acknowledged the order. Physical delivery and placement are unreported.")
        elif intent in ("change_delivery", "cancel_order"):
            order = self._get("orders", request["order_id"])
            if order["status"] != "acknowledged":
                refusal = "The mock store cannot change an order that is no longer awaiting delivery."
            elif intent == "change_delivery" and not WINDOWS[p["window"]]["available"]:
                refusal = "The mock store rejected the amendment; the previously accepted delivery window is unchanged."
            elif intent == "change_delivery":
                order.update(window=p["window"], evidence="Mock store acknowledged the new delivery window; no duplicate order was made.")
            else:
                order.update(status="cancelled", evidence="Mock store acknowledged cancellation before delivery.")
        elif intent == "change_appointment":
            selected = APPOINTMENTS[p["appointment_choice"]]
            if selected["date"] < self.state["date"]:
                refusal = "The supplied clinic alternative is in the past for this simulated day."
            elif all(self.host.appointment[key] == value for key, value in selected.items()):
                refusal = "The selected appointment is already on the shared calendar; no duplicate change was made."
            elif (self.host.week.community["status"] == "confirmed" and selected["date"] == self.host.week.community["date"]
                  and selected["time"] == self.host.week.community["time"]):
                refusal = "This supplied slot conflicts with a chosen activity; a resident decision is required."
            else:
                self.host.appointment.update(selected)
                self.host.week.appointment_version += 1
                self.host.week.appointment_status = "acknowledged"
                self.host.week.appointment_evidence = "Mock clinic acknowledged the supplied appointment change."
                self.host.week._invalidate_ride()
                request["appointment_version"] = self.host.week.appointment_version
        request["service"] = "refused" if refusal else "acknowledged"
        request["error"] = refusal
        request["effects"].append("service_refused" if refusal else "service_acknowledged")

    def _outcome_text(self, request):
        p = request["proposal"]
        if request["error"]:
            return request["error"]
        if not p:
            return request["summary"]
        if p["intent"] in ("order_supply", "change_delivery", "cancel_order") and request["order_id"]:
            order = self._get("orders", request["order_id"])
            return self._order_summary(order)
        if p["intent"] == "change_appointment":
            appointment = self.host.appointment
            return f"Appointment: {appointment['day']} {appointment['time']}, pickup {appointment['pickup']}. " + (
                "Mock clinic acknowledged the change; outbound and return help still need a named person's acceptance."
                if request["service"] == "acknowledged" else "Clinic acknowledgment is pending.")
        if p["intent"] == "carry_help":
            return "Help carrying the prepared meal to the usual table was requested; agreement and physical placement are separate."
        if p["intent"] == "assess_home":
            if p["item"]:
                evaluation = self.host.assessment.evaluate(p["item"], p["quantity"], p["room_id"])
                pending = [key.replace("_", " ") for key, check in evaluation["checks"].items() if check["status"] in ("conflict", "unknown")]
                source = next((item for item in self.host.assessment.view("resident")["candidates"] if item["id"] == p["item"]), {})
                subtotal = evaluation["known_items_cents"]
                setup = evaluation["checks"]["setup"]
                return (f"Draft {source.get('name', p['item'])} × {p['quantity']} for {p['room_id']}. Known published item subtotal: ${subtotal / 100:.2f}; "
                        "full delivered total and fit remain unverified. " + ("Open checks: " + ", ".join(pending) + ". " if pending else "")
                        + (setup["reason"] if setup["status"] != "suitable_to_review" else ""))[:540] + " No purchase or physical work was arranged."
            draft = self.host.assessment.view("resident")
            need = next(item["label"] for item in draft["needs"] if item["id"] == draft["need"])
            return ("Updated your equipment draft: " + need + ". "
                    + ("Budget: $" + f'{draft["constraints"]["budget_cents"] / 100:.2f}' + ". " if draft["constraints"]["budget_cents"] is not None else "")
                    + "No purchase or setup was arranged. Fit and full costs remain unconfirmed.")
        return request["summary"]

    @staticmethod
    def _order_summary(order):
        return f"{ITEMS[order['item']]['label']}, quantity {order['quantity']}, {WINDOWS[order['window']]['label']}: {order['evidence']}"

    def _send_messages(self, request):
        p = request["proposal"]
        recipients = list(dict.fromkeys(p["recipients"] + ([p["helper"]] if p["helper"] else [])))
        if len(self.state["messages"]) + len(recipients) > MAX_MESSAGES:
            raise ValueError("The addressed inbox limit was reached.")
        for actor in recipients:
            identity = request["id"] + "-" + actor
            kind = "information"
            if actor == p["helper"] and request["service"] != "refused":
                kind = "carry_help" if p["intent"] == "carry_help" else "travel"
            self.state["messages"].append({"id": identity, "request_id": request["id"], "recipient": actor,
                "kind": kind, "body": self._outcome_text(request), "status": "sent", "day": self.day,
                "available_day": None, "read_day": None, "response_day": None, "completed_day": None, "metadata": {}})
            request["message_ids"].append(identity)

    def fail(self, request_id, message):
        request = self._get("requests", request_id)
        if request["status"] != "interpreting":
            return False
        request.update(status="failed", error=str(message)[:400], summary="The request could not be interpreted; no effects were started.")
        self._touch("coordinator", "failed", request["summary"])
        return True

    def _cancel(self, request, status="cancelled"):
        p = request["proposal"]
        if p and p["intent"] in HOSPITAL_INTENTS and request["phase"] > 0:
            self.host.hospital.cancel_request(request["id"])
        if p and p["intent"] == "carry_help" and request["phase"] > 0 and hasattr(self.host, "meal"):
            self.host.meal.helper_reply(request["id"], p["helper"], "cancelled")
        request.update(status=status, summary="Future request steps stopped; previously acknowledged effects remain recorded.")
        if request["order_id"]:
            order = self._get("orders", request["order_id"])
            if order["status"] == "requested":
                order.update(status="cancelled", evidence="Unacknowledged order request stopped before mock service acceptance.")
        for identity in request["message_ids"]:
            message = self._get("messages", identity)
            if message["status"] not in ("completed", "declined"):
                message["status"] = "cancelled"

    def cancel_help(self, request_id):
        """Meal cancellation hook; it must not recurse through helper_reply."""
        request = self._get("requests", request_id)
        if request["status"] in TERMINAL:
            return False
        request.update(status="cancelled", summary="Meal help stopped; the resident chose how to continue.")
        for identity in request["message_ids"]:
            self._get("messages", identity)["status"] = "cancelled"
        self._touch("resident", "cancel_help", request["summary"])
        return True

    def complete_help(self, request_id):
        request = self._get("requests", request_id)
        if request["status"] == "completed":
            return False
        if request["status"] != "waiting_physical" or request["day"] != self.day:
            raise ValueError("Physical meal completion needs a current accepted responsibility.")
        accepted = [self._get("messages", identity) for identity in request["message_ids"]
                    if self._get("messages", identity)["kind"] == "carry_help"]
        if len(accepted) != 1 or accepted[0]["status"] != "accepted":
            raise ValueError("No named helper accepted this carrying request.")
        accepted[0].update(status="completed", completed_day=self.day)
        request.update(status="completed", summary="The authored meal routine reports the helper placed the bowl at the table.")
        request["effects"].append("physical_placement_reported")
        self._touch(accepted[0]["recipient"], "physical_completion", request["summary"])
        return True

    def shared_changed(self, force=False):
        current = self._shared_facts()
        if current == self.state["shared"] and not force:
            return False
        if current["support"] != self.state["shared"]["support"]:
            support = current["support"]
            matching = [actor for actor, name in ACTORS.items() if name == support["helper"]]
            affected = matching or (list(ACTORS) if not support["helper_available"] else [])
            for actor in affected:
                self.state["actors"][actor].update(day=self.day, available=support["helper_available"])
                self.state["actors"][actor]["available"] = self.availability_for(actor)
        self._touch("household", "shared_change", "Relevant shared household facts changed.")
        return True

    @staticmethod
    def _button(action, label, **payload):
        return {"action": action, "label": label, "payload": payload}

    def view(self, role, actor_id=None):
        actor = self._actor(role, actor_id)
        resident = actor == "resident"
        b = self._button
        controls = {"setup": [], "actions": [], "inbox": [], "reminders": [], "memory": []}
        if resident:
            for key, value in self.state["preferences"].items():
                if value is not None:
                    controls["memory"].append(b("coordination_forget_preference", "Forget my " + key.replace("_", " ") + " preference", key=key))
            if not self.state["setup_done"]:
                controls["setup"].append(b("coordination_setup", "Allow routine coordination with these preferences",
                    permissions={**dict.fromkeys(BOOL_PERMISSIONS, True), "spend_cap": self.state["permissions"]["spend_cap"]},
                    preferences=deepcopy(self.state["preferences"])))
            controls["actions"].append(b("coordination_next_day", "Continue to the next simulated day"))
            if self.state["clock_minute"] + 60 <= 1439:
                controls["reminders"].append(b("coordination_advance_clock", "Advance the demo clock one hour", minutes=60))
            active_targets = {r["target_message_id"] for r in self.state["reminders"] if r["status"] != "cancelled"}
            if self.state["permissions"]["notify"] and len(self.state["reminders"]) < 40 and self.state["clock_minute"] + 60 <= 1439:
                for message in self.state["messages"]:
                    if self._pending(message) and message["id"] not in active_targets:
                        topic = message["metadata"].get("kind", message["kind"]).replace("_", " ")
                        controls["reminders"].append(b("coordination_schedule_reminder", "Remind " + ACTORS[message["recipient"]]
                            + " in one hour about " + topic, message_id=message["id"], hours=1))
            for reminder in self.state["reminders"]:
                if reminder["status"] != "cancelled":
                    controls["reminders"].append(b("coordination_cancel_reminder", "Cancel reminder " + reminder["id"], reminder_id=reminder["id"]))
            if any(self.state["permissions"][key] for key in BOOL_PERMISSIONS):
                controls["actions"].append(b("coordination_permissions", "Pause permissioned coordination", **dict.fromkeys(BOOL_PERMISSIONS, False)))
            for request in self.state["requests"]:
                if request["status"] not in TERMINAL:
                    controls["actions"].append(b("coordination_cancel", "Stop request: " + request["id"], request_id=request["id"]))
                if request["status"] in ("completed", "declined", "failed") and not any(f["request_id"] == request["id"] for f in self.state["feedback"]):
                    for helped in (True, False):
                        controls["actions"].append(b("coordination_feedback", "That helped" if helped else "That did not help", request_id=request["id"], helped=helped))
        else:
            for report in self.state["availability"]:
                if report["actor_id"] == actor:
                    controls["memory"].append(b("coordination_remove_availability", "Remove my availability for "
                        + report["start_date"] + " through " + report["end_date"], actor_id=actor,
                        start_date=report["start_date"], end_date=report["end_date"]))
            for available in (True, False):
                if self.state["actors"][actor]["available"] is not available:
                    controls["actions"].append(b("coordination_availability", "I am available today" if available else "I am unavailable today", actor_id=actor, available=available))
        inbox = [message for message in self.state["messages"] if message["recipient"] == actor and message["status"] != "sent"]
        for message in inbox:
            if message["status"] == "available":
                controls["inbox"].append(b("coordination_read", "Mark update read", message_id=message["id"], actor_id=actor))
            if self._pending(message):
                if self.can_accept(message):
                    controls["inbox"].append(b("coordination_reply", "Accept this responsibility", message_id=message["id"], actor_id=actor, status="accepted"))
                controls["inbox"].append(b("coordination_reply", "Decline this responsibility", message_id=message["id"], actor_id=actor, status="declined"))
        visible_order_ids = {self._get("requests", m["request_id"])["order_id"] for m in inbox}
        orders = self.state["orders"] if resident else [o for o in self.state["orders"] if o["id"] in visible_order_ids]
        for order in orders:
            if order["status"] == "acknowledged":
                controls["actions"].append(b("coordination_report_delivery", "I observed this order delivered", order_id=order["id"], actor_id=actor))
            if order["status"] == "delivered" and (resident or self.available(actor)):
                controls["actions"].append(b("coordination_report_placement", "I placed this delivered order in storage", order_id=order["id"], actor_id=actor))
        return deepcopy({"day": self.day, "date": self.state["date"], "clock": self._clock(), "version": self.version, "selected_actor": actor,
            "reminders": self.state["reminders"] if resident else [r for r in self.state["reminders"] if r["recipient"] == actor],
            "actors": self.state["actors"], "permissions": self.state["permissions"], **self._continuity_view(actor),
            "preference_choices": PREFERENCES, "setup_done": self.state["setup_done"],
            "requests": self.state["requests"] if resident else [], "orders": orders, "inbox": inbox,
            "outbox": self.state["messages"] if resident else [], "controls": controls,
            "history": self.state["history"] if resident else [], "feedback": self.state["feedback"] if resident else [],
            "replies": self.state["replies"] if resident else [r for r in self.state["replies"] if r["actor_id"] == actor],
            "accounting": {"human_by_actor": self.state["human_interactions"] if resident else {actor: self.state["human_interactions"][actor]},
                           "note": "Recorded requests, setup, corrections, named replies and explicit reports. Model and service steps, automatic movement, and demo clock/day controls are excluded; human time is not measured."},
            "notice": "Alex and Morgan are named demonstration contacts, not aliases for a differently named profile helper. "
                      "Declared lack of local support starts both unavailable; each can explicitly report current availability. "
                      "Read receipts, accepted responsibility, and physical reports are separate; no real transaction or message occurs."})

    def _permissions(self, values):
        if not isinstance(values, dict) or not values or set(values) - set(self.state["permissions"]):
            raise ValueError("Use supported coordination permissions.")
        for key, value in values.items():
            if key == "spend_cap":
                if type(value) not in (int, float) or not isfinite(value) or not 0 <= value <= 100:
                    raise ValueError("Use a finite per-order cap from $0 to $100.")
            elif type(value) is not bool:
                raise ValueError("Permissions must be true or false.")

    def _preferences(self, values, allow_unset=False):
        if not isinstance(values, dict) or not values or set(values) - set(PREFERENCES) or any(
                value not in PREFERENCES[key] and not (allow_unset and value is None) for key, value in values.items()):
            raise ValueError("Use the supplied preference choices.")

    def _memory_payload(self, memory, forget=False):
        if not isinstance(memory, dict) or set(memory) != {"key", "value", "audience"} or not isinstance(memory["key"], str) or memory["key"] not in PREFERENCES:
            raise ValueError("Choose one existing preference to remember or forget.")
        audience = memory["audience"]
        if forget:
            if memory["value"] is not None or audience != []:
                raise ValueError("Forgetting uses a null value and no sharing audience.")
        else:
            self._preferences({memory["key"]: memory["value"]})
            if (not isinstance(audience, list) or not 1 <= len(audience) <= 3
                    or any(not isinstance(a, str) or a not in ("resident", *ACTORS) for a in audience)
                    or "resident" not in audience or len(set(audience)) != len(audience)):
                raise ValueError("Choose a sharing audience including the resident, with each person listed once.")

    def _set_availability(self, actor, payload, remove=False):
        fields = {"actor_id", "start_date", "end_date"} | (set() if remove else {"available"})
        if set(payload) != fields or actor not in ACTORS or payload["actor_id"] != actor:
            raise ValueError("Only the named helper can change their own dated availability.")
        start, end = self._date(payload["start_date"]), self._date(payload["end_date"])
        if start > end or not remove and (type(payload["available"]) is not bool or end.isoformat() < self.state["date"]):
            raise ValueError("Report true or false availability for a current or future date interval.")
        reports = []
        found = False
        for old in self.state["availability"]:
            if remove:
                match = all(old[k] == payload[k] for k in fields)
                found |= match
                if not match:
                    reports.append(old)
            elif old["actor_id"] != actor or old["end_date"] < start.isoformat() or old["start_date"] > end.isoformat():
                reports.append(old)
            else:
                if old["start_date"] < start.isoformat():
                    reports.append({**old, "end_date": (start - timedelta(days=1)).isoformat()})
                if old["end_date"] > end.isoformat():
                    reports.append({**old, "start_date": (end + timedelta(days=1)).isoformat()})
        if remove and not found:
            raise ValueError("Choose one of your saved date intervals to remove.")
        if not remove:
            reports.append({**payload, "reported_date": self.state["date"], "reported_minute": self.state["clock_minute"],
                            "revision": self.version + 1})
        if len(reports) > 40:
            raise ValueError("This demonstration holds at most 40 dated availability intervals.")
        saved = self.dump()
        transport = deepcopy(self.host.transport)
        week = {k: deepcopy(v) for k, v in vars(self.host.week).items() if k != "host"}
        domains = {k: getattr(self.host, k).dump() for k in ("meal", "hospital") if hasattr(self.host, k)}
        try:
            self.state["availability"] = sorted(reports, key=lambda r: (r["actor_id"], r["start_date"]))
            if start.isoformat() <= self.state["date"] <= end.isoformat():
                self.state["actors"][actor].update(day=self.day, available=None)
                self.state["actors"][actor]["available"] = self.availability_for(actor)
            if not remove and not payload["available"]:
                for message in self.state["messages"]:
                    if (message["recipient"] == actor and message["status"] == "accepted" and self._current_duty(message)
                            and start.isoformat() <= self.duty_date(message) <= end.isoformat()):
                        self._reply(message, "declined")
            self.state["memory_revision"] += 1
        except ValueError:
            self.state = saved
            self.host.transport = transport
            vars(self.host.week).update(week)
            for key, snapshot in domains.items():
                getattr(self.host, key).state = snapshot
            raise

    def apply(self, action, role, payload=None, actor_id=None):
        actor = self._actor(role, actor_id)
        payload = {} if payload is None else payload
        if not isinstance(payload, dict):
            raise ValueError("Action details must be an object.")
        if action == "coordination_watch_visits":
            if actor != "resident" or set(payload) != {"enabled"} or type(payload["enabled"]) is not bool:
                raise ValueError("The resident chooses whether to watch visit changes.")
            self.state["watch_visit_changes"] = payload["enabled"]
            text = "Visit-change monitoring " + ("enabled." if payload["enabled"] else "disabled.")
            self._touch(actor, action, text)
            return text
        if action in ("coordination_remember_preference", "coordination_forget_preference"):
            if actor != "resident":
                raise ValueError("Only the resident changes their own remembered preferences.")
            forget = action == "coordination_forget_preference"
            if forget and set(payload) != {"key"}:
                raise ValueError("Choose one preference to forget.")
            memory = {"key": payload["key"], "value": None, "audience": []} if forget else payload
            self._memory_payload(memory, forget)
            if not self._remember_preferences({memory["key"]: memory["value"]}, memory["audience"]):
                return "That exact preference and sharing scope are already recorded."
            text = "Remembered preference removed." if forget else "Preference recorded with its source and sharing scope."
            self._touch(actor, action, text)
            return text
        if action in ("coordination_set_availability", "coordination_remove_availability", "coordination_availability"):
            if action == "coordination_availability":
                if set(payload) != {"actor_id", "available"}:
                    raise ValueError("Supply your own named availability report.")
                payload = {**payload, "start_date": self.state["date"], "end_date": self.state["date"]}
            self._set_availability(actor, payload, action == "coordination_remove_availability")
            text = "Dated availability updated; task acceptance remains separate."
            self._touch(actor, action, text)
            return text
        if action in ("coordination_schedule_reminder", "coordination_cancel_reminder", "coordination_advance_clock"):
            if actor != "resident":
                raise ValueError("The resident agrees reminders and advances this demonstration clock.")
            if action == "coordination_schedule_reminder":
                if set(payload) != {"message_id", "hours"} or not self.state["permissions"]["notify"]:
                    raise ValueError("Agree a current responsibility and delay, with permission for named updates.")
                _, old = self._check_reminder(payload["message_id"], payload["hours"])
                if old:
                    return "That exact responsibility already has an agreed reminder; no duplicate was scheduled."
                reminder = self._schedule_reminder(payload["message_id"], payload["hours"])
                text = "Agreed one reminder for " + ACTORS[reminder["recipient"]] + " at " + self._clock_label(reminder["due_minute"]) + "."
            elif action == "coordination_cancel_reminder":
                if set(payload) != {"reminder_id"}:
                    raise ValueError("Choose the agreed reminder to cancel.")
                reminder = self._get("reminders", payload["reminder_id"])
                if reminder["status"] == "cancelled":
                    return "This reminder is already cancelled."
                self._cancel_reminder(reminder)
                text = "Cancelled only this reminder; the underlying responsibility keeps its own status."
            else:
                if (set(payload) != {"minutes"} or type(payload["minutes"]) is not int or not 1 <= payload["minutes"] <= 180
                        or self.state["clock_minute"] + payload["minutes"] > 1439):
                    raise ValueError("Advance 1–180 demo minutes within this day; use next day at the day boundary.")
                end = self.state["clock_minute"] + payload["minutes"]
                due = [r for r in self.state["reminders"] if r["status"] == "scheduled" and r["day"] == self.day
                       and r["due_minute"] <= end and self.state["permissions"]["notify"]
                       and self._pending(self._get("messages", r["target_message_id"]))]
                additions = {}
                for reminder in due:
                    target = self._get("messages", reminder["target_message_id"])
                    additions[target["request_id"]] = additions.get(target["request_id"], 0) + 1
                if len(self.state["messages"]) + len(due) > MAX_MESSAGES or any(
                        len(self._get("requests", identity)["message_ids"]) + count > 12 for identity, count in additions.items()):
                    raise ValueError("The bounded inbox cannot hold these reminders; the demo clock was not advanced.")
                self.state["clock_minute"] = end
                self._sync_reminders()
                for reminder in due:
                    target = self._get("messages", reminder["target_message_id"])
                    topic = target["metadata"].get("kind", target["kind"]).replace("_", " ")
                    receipt = self._post_information(self._get("requests", target["request_id"]), target["recipient"], reminder["id"],
                        "Agreed reminder about " + topic + ": your response to " + target["id"]
                        + " is still pending. No task deadline or physical completion is inferred.")
                    reminder.update(status="issued", issued_minute=end, receipt_id=receipt)
                text = "Demo clock advanced to " + self._clock_label(end) + "; " + str(len(due)) + " agreed reminder(s) issued."
            self._touch(actor, action, text)
            return text
        if action in ("coordination_setup", "coordination_permissions", "coordination_preferences"):
            if actor != "resident":
                raise ValueError("The resident controls these preferences and permissions.")
            if action == "coordination_setup":
                if self.state["setup_done"] or set(payload) != {"permissions", "preferences"}:
                    raise ValueError("Initial coordination setup is one grouped choice, once per household.")
                self._permissions(payload["permissions"])
                self._preferences(payload["preferences"], allow_unset=True)
                self.state["permissions"].update(payload["permissions"])
                self._remember_preferences(payload["preferences"])
                self.state["setup_done"] = True
            elif action == "coordination_permissions":
                self._permissions(payload)
                self.state["permissions"].update(payload)
            else:
                self._preferences(payload)
                if not self._remember_preferences(payload):
                    return "Those preferences are already recorded."
            self._touch(actor, "setup" if action == "coordination_setup" else "correction", "Resident updated coordination preferences or permissions.")
            return "Coordination preferences and permissions recorded."
        buttons = [b for group in self.view(role, actor_id)["controls"].values() for b in group]
        if not any(b["action"] == action and b["payload"] == payload for b in buttons):
            raise ValueError("This action is unavailable for the selected named perspective or current facts.")
        if action in ("coordination_availability", "coordination_feedback"):
            key = "available" if action == "coordination_availability" else "helped"
            if type(payload[key]) is not bool:
                raise ValueError("Use a true or false report.")
        if action == "coordination_next_day":
            new_day = self.day + 1
            if new_day > 365:
                raise ValueError("This demonstration is limited to 365 simulated days.")
            if hasattr(self.host, "meal"):
                self.host.meal.next_day(new_day)
            if hasattr(self.host, "hospital"):
                self.host.hospital.next_day(new_day)
            self.state.update(day=new_day, date=(date.fromisoformat(self.state["date"]) + timedelta(days=1)).isoformat(), clock_minute=540)
            for person in self.state["actors"].values():
                person.update(day=new_day, available=None)
            for identity, person in self.state["actors"].items():
                person["available"] = self.availability_for(identity)
            for message in self.state["messages"]:
                if (message["kind"] != "information" and message["status"] in ("sent", "available", "read", "accepted")
                        and not self._current_duty(message)):
                    request = self._get("requests", message["request_id"])
                    if message["kind"] == "travel" and message["status"] == "accepted" and request["appointment_version"] == self.host.week.appointment_version:
                        person = ACTORS[message["recipient"]]
                        if self.host.transport["person"] == person:
                            self.host.transport.update(status="needs_confirmation", person=None, for_date=None)
                        if self.host.week.return_person == person:
                            self.host.week.return_status = "needs_confirmation"
                            self.host.week.return_person = None
                        self.host.week.ride_evidence = "Earlier-day helper availability expired; current travel acceptance needs a fresh report."
                        request.update(status="paused", question="Recheck this earlier-day travel responsibility for the current day.")
                    message["status"] = "expired"
            for request in self.state["requests"]:
                if (request["proposal"] and request["proposal"]["helper"] and request["status"] not in TERMINAL
                        and not any(m["request_id"] == request["id"] and self._current_duty(m)
                                    and m["status"] in ("available", "read", "accepted") for m in self.state["messages"])):
                    request.update(status="paused", question="Yesterday's help does not establish availability today. Make a current request.")
            text = "Continued to a new day; remembered preferences, dated availability and applicable duties remain. Unreported availability stays unknown."
        elif action == "coordination_cancel":
            self._cancel(self._get("requests", payload["request_id"]))
            text = "Stopped future request effects; acknowledged orders and changes remain recorded."
        elif action in ("coordination_read", "coordination_reply"):
            message = self._get("messages", payload["message_id"])
            if action == "coordination_read":
                message.update(status="read", read_day=self.day)
                text = "Named recipient marked this update read; no responsibility was accepted."
            else:
                self._reply(message, payload["status"])
                text = "Named recipient " + payload["status"] + " this responsibility."
        elif action == "coordination_feedback":
            self.state["feedback"].append({"request_id": payload["request_id"], "day": self.day, "helped": payload["helped"]})
            self.state["feedback"] = self.state["feedback"][-40:]
            text = "Resident feedback recorded without inferring a health or safety outcome."
        else:
            order = self._get("orders", payload["order_id"])
            if action == "coordination_report_delivery":
                order.update(status="delivered", delivered_by=actor, evidence="A named person reports observing this order delivered; placement remains unreported.")
            else:
                order.update(status="placed", placed_by=actor, evidence="A named person reports placing the delivered supply in storage.")
            for request in self.state["requests"]:
                if request["order_id"] == order["id"]:
                    prefix = request["error"] + " Current order: " if request["error"] else ""
                    request["summary"] = (prefix + self._order_summary(order))[:600]
            text = order["evidence"]
        self._touch(actor, action, text)
        return text

    def _reply(self, message, status):
        request = self._get("requests", message["request_id"])
        actor = message["recipient"]
        if status == "accepted" and not self.can_accept(message):
            raise ValueError("This person is not available for the responsibility's date.")
        if not self._current_duty(message) or request["status"] in TERMINAL and request["status"] != "completed":
            raise ValueError("That responsibility is no longer current.")
        if message["kind"] == "travel":
            if request["appointment_version"] != self.host.week.appointment_version:
                raise ValueError("The appointment changed; this travel reply is stale.")
            accepted = status == "accepted"
            self.host.transport.update(status="confirmed" if accepted else "declined", person=ACTORS[actor] if accepted else None,
                                       for_date=self.host.appointment["date"] if accepted else None)
            week = self.host.week
            week.backup_version = week.appointment_version
            week.requested_legs = ["outbound", "return"]
            week.return_status = "confirmed" if accepted else "declined"
            week.return_version = week.appointment_version
            week.return_person = ACTORS[actor] if accepted else None
            week.ride_evidence = ACTORS[actor] + " " + status + " outbound and return travel for this current appointment."
            request.update(status="completed" if accepted else "declined", summary=week.ride_evidence)
        elif message["kind"] == "carry_help":
            meal_status = "cancelled" if status == "declined" and self.host.meal.help_context()["help"]["status"] == "accepted" else status
            self.host.meal.helper_reply(request["id"], actor, meal_status)
            request.update(status="waiting_physical" if status == "accepted" else "declined",
                           summary="Carrying help was accepted; actual table placement is pending." if status == "accepted" else "The named helper declined carrying responsibility.")
        elif message["kind"] == "hospital":
            self.host.hospital.recipient_reply(message["metadata"]["commitment_id"], actor, status)
            request.update(status="ready", summary="Named hospital responsibility reply recorded; the next bounded step can use it.")
        else:
            raise ValueError("An information update carries no responsibility to accept.")
        message.update(status=status, read_day=message["read_day"] or self.day, response_day=self.day)
        if status == "accepted" and "helper_accepted" not in request["effects"]:
            request["effects"].append("helper_accepted")

    def post_domain_message(self, request_id, recipient, key, text, metadata):
        request = self._get("requests", request_id)
        if recipient not in ACTORS or not isinstance(key, str) or not DOMAIN_ID.fullmatch(key) or not isinstance(text, str) or not 1 <= len(text) <= 600:
            raise ValueError("Use a bounded named household message.")
        if (not isinstance(metadata, dict) or set(metadata) != {"domain", "commitment_id", "kind", "version"}
                or metadata["domain"] != "hospital" or not isinstance(metadata["commitment_id"], str)
                or not DOMAIN_ID.fullmatch(metadata["commitment_id"]) or metadata["kind"] not in ("driver", "companion", "return", "pickup")
                or type(metadata["version"]) is not int or metadata["version"] < 1):
            raise ValueError("Use a current hospital commitment reference.")
        identity = request_id + "-" + key + "-" + recipient
        old = next((m for m in self.state["messages"] if m["id"] == identity), None)
        if old:
            if old["body"] != text or old["metadata"] != metadata:
                raise ValueError("That message key already identifies different responsibility facts.")
            return identity
        if len(self.state["messages"]) >= MAX_MESSAGES or len(request["message_ids"]) >= 12:
            raise ValueError("The bounded household inbox is full.")
        self.state["messages"].append({"id": identity, "request_id": request_id, "recipient": recipient,
            "kind": "hospital", "body": text, "status": "available", "day": self.day,
            "available_day": self.day, "read_day": None, "response_day": None, "completed_day": None, "metadata": deepcopy(metadata)})
        request["message_ids"].append(identity)
        self._touch("hospital", "addressed_update", "A hospital responsibility was sent and made available to its named recipient; unread and unaccepted.")
        return identity

    def cancel_domain_message(self, message_id):
        message = self._get("messages", message_id)
        if message["kind"] != "hospital":
            raise ValueError("Choose a hospital responsibility message.")
        if message["status"] in ("cancelled", "completed"):
            return False
        message["status"] = "cancelled"
        self._touch("hospital", "responsibility_cancelled", "A supplied hospital responsibility is no longer current.")
        return True

    def resume_domain_request(self, request_id):
        request = self._get("requests", request_id)
        if request["proposal"] is None or request["proposal"]["intent"] not in HOSPITAL_INTENTS:
            raise ValueError("Choose a hospital administration request.")
        if request["status"] in ("cancelled", "superseded"):
            return False
        request.update(status="ready", question="", day=self.day, appointment_version=self.host.week.appointment_version,
                       summary="Supplied hospital responsibility facts changed; the next bounded step can reconcile them.")
        self._touch("hospital", "request_ready", request["summary"])
        return True

    def complete_domain_message(self, message_id):
        message = self._get("messages", message_id)
        if message["kind"] != "hospital" or message["metadata"]["kind"] != "pickup":
            raise ValueError("Choose an accepted pharmacy pickup responsibility.")
        if message["status"] == "completed":
            return False
        if message["status"] != "accepted" or message["response_day"] is None:
            raise ValueError("A physical delivery report needs an accepted named responsibility.")
        message.update(status="completed", completed_day=self.day)
        request = self._get("requests", message["request_id"])
        if "delivery_reported" not in request["effects"]:
            request["effects"].append("delivery_reported")
        self._touch("hospital", "delivery_reported", "The hospital domain received an explicit physical delivery report for this accepted pickup.")
        return True

    def dump(self):
        return deepcopy(self.state)

    @classmethod
    def restore(cls, host, data):
        result = cls(host)
        if isinstance(data, dict) and "watch_visit_changes" not in data:
            data = deepcopy(data)
            data["watch_visit_changes"] = False
        if isinstance(data, dict) and isinstance(data.get("requests"), list):
            data = deepcopy(data)
            old_keys = set(_request("", "", 1, 1, None)) - {"source_digest", "memory_redacted"}
            for request in data["requests"]:
                if isinstance(request, dict) and set(request) == old_keys:
                    request.update(source_digest=None, memory_redacted=False)
        continuity = {"preference_memory", "availability", "memory_revision", "memory_cutoff"}
        if isinstance(data, dict) and set(data) in (set(result.state) - continuity,
                set(result.state) - continuity - {"clock_minute", "reminders"}):
            data = deepcopy(data)
            data.update({key: deepcopy(result.state[key]) for key in continuity})
        # Only the exact previous shape gains a demonstration clock. Earlier
        # history has no minute evidence, so its timestamps remain explicitly unknown.
        if isinstance(data, dict) and set(data) == set(result.state) - {"clock_minute", "reminders"}:
            data = deepcopy(data)
            data.update(clock_minute=540, reminders=[])
            for entry in data["history"]:
                if isinstance(entry, dict) and set(entry) == {"day", "actor", "event", "text"}:
                    entry["minute"] = None
            # A prior UI build omitted this redundant effect tag after a natural
            # carry reply. Recover it only from both the explicit accepted reply
            # and its completed addressed receipt; completion alone is insufficient.
            for request in data["requests"]:
                p = request.get("proposal") if isinstance(request, dict) else None
                if (isinstance(p, dict) and p.get("intent") == "carry_help" and request.get("status") == "completed"
                        and request.get("effects") == ["request_sent", "physical_placement_reported"]):
                    receipts = [m for m in data["messages"] if isinstance(m, dict) and m.get("id") in request.get("message_ids", [])
                                and m.get("request_id") == request.get("id") and m.get("kind") == "carry_help"
                                and m.get("recipient") == p.get("helper") and m.get("status") == "completed"
                                and m.get("response_day") is not None and m.get("completed_day") is not None]
                    if len(receipts) == 1 and any(isinstance(reply, dict) and reply.get("actor_id") == p.get("helper")
                            and reply.get("day") == receipts[0]["response_day"]
                            and {"message_id": receipts[0]["id"], "status": "accepted"} in reply.get("decisions", [])
                            for reply in data["replies"]):
                        request["effects"].insert(1, "helper_accepted")
        # Earlier increment saves predate the support fingerprint. Add only that
        # derived field; every existing shared fact must still match during validation.
        if (isinstance(data, dict) and isinstance(data.get("shared"), dict)
                and set(data["shared"]) == set(result.state["shared"]) - {"support"}):
            data = deepcopy(data)
            data["shared"]["support"] = deepcopy(result.state["shared"]["support"])
        result._validate_restore(data)
        result.state = deepcopy(data)
        interrupted = [r for r in result.state["requests"] if r["status"] == "interpreting"]
        for request in interrupted:
            request.update(status="failed", error="Interpretation was interrupted by a restart. Retry with a new request ID; no action was executed.",
                           summary="Interrupted request needs a retry; no completion is claimed.")
        if interrupted:
            result._touch("system", "interrupted", "Interrupted interpretations stopped without replay; later messages can continue.")
        return result

    def _validate_restore(self, data):
        def fail():
            raise ValueError("Saved household coordination is malformed or contradictory.")
        if not isinstance(data, dict) or set(data) != set(self.state):
            fail()
        try:
            if len(json.dumps(data, allow_nan=False)) > 250000:
                fail()
            if type(data["version"]) is not int or data["version"] < 0 or type(data["day"]) is not int or not 1 <= data["day"] <= 365:
                fail()
            if type(data["clock_minute"]) is not int or not 0 <= data["clock_minute"] <= 1439:
                fail()
            if type(data["watch_visit_changes"]) is not bool:
                fail()
            if date.fromisoformat(data["date"]) != date(2026, 9, 15) + timedelta(days=data["day"] - 1) or type(data["setup_done"]) is not bool:
                fail()
            self._permissions(data["permissions"])
            self._preferences(data["preferences"], allow_unset=True)
            if set(data["permissions"]) != set(self.state["permissions"]) or set(data["preferences"]) != set(PREFERENCES) or set(data["actors"]) != set(ACTORS):
                fail()
            if (not isinstance(data["human_interactions"], dict) or set(data["human_interactions"]) != {"resident", *ACTORS}
                    or any(type(value) is not int or not 0 <= value <= 100000 for value in data["human_interactions"].values())):
                fail()
            for actor, person in data["actors"].items():
                if set(person) != {"name", "day", "available"} or person["name"] != ACTORS[actor] or person["day"] != data["day"] or person["available"] is not None and type(person["available"]) is not bool:
                    fail()
            limits = {"requests": MAX_REQUESTS, "orders": MAX_REQUESTS, "messages": MAX_MESSAGES, "history": 120, "feedback": 40, "replies": 40, "reminders": 40}
            for key, limit in limits.items():
                if not isinstance(data[key], list) or len(data[key]) > limit:
                    fail()
            maps = {}
            for key in ("requests", "orders", "messages"):
                maps[key] = {item["id"]: item for item in data[key]}
                if len(maps[key]) != len(data[key]):
                    fail()
            requests, orders, messages = maps["requests"], maps["orders"], maps["messages"]
            if (type(data["memory_revision"]) is not int or not 0 <= data["memory_revision"] <= data["version"]
                    or type(data["memory_cutoff"]) is not int or not 0 <= data["memory_cutoff"] <= len(data["requests"])
                    or not isinstance(data["preference_memory"], dict) or set(data["preference_memory"]) - set(PREFERENCES)
                    or data["preference_memory"] and not data["memory_revision"]
                    or not data["memory_revision"] and data["memory_cutoff"]):
                fail()
            for key, record in data["preference_memory"].items():
                if (not isinstance(record, dict) or set(record) != {"id", "subject", "key", "value", "audience", "status", "source"}
                        or record["id"] != "preference-" + key or record["subject"] != "resident" or record["key"] != key
                        or record["value"] != data["preferences"][key] or record["status"] not in ("current", "removed")):
                    fail()
                removed = record["status"] == "removed"
                if removed and (record["value"] is not None or record["audience"] != ["resident"]):
                    fail()
                self._memory_payload({"key": key, "value": record["value"], "audience": [] if removed else record["audience"]}, removed)
                source = record["source"]
                if (not isinstance(source, dict) or set(source) != {"actor_id", "kind", "date", "minute", "revision", "request_id"}
                        or source["actor_id"] != "resident" or source["kind"] != "explicit_report"
                        or self._date(source["date"]) > date.fromisoformat(data["date"])
                        or type(source["minute"]) is not int or not 0 <= source["minute"] <= 1439
                        or type(source["revision"]) is not int or not 1 <= source["revision"] <= data["version"]
                        or not isinstance(source["request_id"], str) or source["request_id"] and source["request_id"] not in requests):
                    fail()
                if source["request_id"]:
                    original = requests[source["request_id"]]
                    original_memory = original["proposal"].get("memory") if original["proposal"] else None
                    if (not isinstance(original_memory, dict) or original_memory.get("key") != key
                            or original_memory.get("value") != record["value"]
                            or sorted(original_memory.get("audience", [])) != ([] if removed else sorted(record["audience"]))
                            or original["status"] != "completed" or original["effects"] != ["preference_recorded"]):
                        fail()
            if any(value is None and key not in data["preference_memory"] for key, value in data["preferences"].items()):
                fail()
            if not isinstance(data["availability"], list) or len(data["availability"]) > 40:
                fail()
            ends = {}
            for report in sorted(data["availability"], key=lambda r: (r["actor_id"], r["start_date"])):
                if (set(report) != {"actor_id", "start_date", "end_date", "available", "reported_date", "reported_minute", "revision"}
                        or report["actor_id"] not in ACTORS or type(report["available"]) is not bool
                        or self._date(report["start_date"]) > self._date(report["end_date"])
                        or self._date(report["reported_date"]) > date.fromisoformat(data["date"])
                        or type(report["reported_minute"]) is not int or not 0 <= report["reported_minute"] <= 1439
                        or type(report["revision"]) is not int or not 1 <= report["revision"] <= data["version"]
                        or ends.get(report["actor_id"], "") >= report["start_date"]):
                    fail()
                ends[report["actor_id"]] = report["end_date"]
                if (report["start_date"] <= data["date"] <= report["end_date"]
                        and data["actors"][report["actor_id"]]["available"] is not report["available"]):
                    fail()
            for r in requests.values():
                if set(r) != set(_request("x", "x", 1, 1, None)) or not ID.fullmatch(r["id"]) or not isinstance(r["text"], str) or not 1 <= len(r["text"]) <= 2000:
                    fail()
                if type(r["memory_redacted"]) is not bool:
                    fail()
                if r["memory_redacted"]:
                    if (not isinstance(r["source_digest"], str) or not re.fullmatch(r"[0-9a-f]{64}", r["source_digest"])
                            or r["text"] != "[Removed memory source]" or r["status"] != "completed"
                            or not r["proposal"] or r["proposal"]["intent"] not in MEMORY_INTENTS
                            or r["question"] or r["error"] or r["proposal"]["summary"] or r["proposal"]["question"]):
                        fail()
                elif r["source_digest"] is not None:
                    fail()
                if r["status"] not in REQUEST_STATES or type(r["phase"]) is not int or not 0 <= r["phase"] <= 5:
                    fail()
                if any(type(r[key]) is not int or not 1 <= r[key] <= data["day"] for key in ("day", "created_day")) or r["created_day"] > r["day"]:
                    fail()
                if type(r["appointment_version"]) is not int or r["appointment_version"] < 1 or r["service"] not in ("none", "requested", "acknowledged", "refused", "prepared"):
                    fail()
                if not isinstance(r["effects"], list) or len(r["effects"]) > 3 or len(set(r["effects"])) != len(r["effects"]):
                    fail()
                if set(r["effects"]) - {"request_sent", "service_acknowledged", "service_refused", "physical_placement_reported", "assessment_prepared", "helper_accepted", "delivery_reported", "reminder_scheduled", "preference_recorded"}:
                    fail()
                if any(not isinstance(r[key], str) or len(r[key]) > 600 for key in ("question", "summary", "error")):
                    fail()
                if r["replace_request_id"] is not None and r["replace_request_id"] not in requests or r["order_id"] and r["order_id"] not in orders:
                    fail()
                if not isinstance(r["message_ids"], list) or len(r["message_ids"]) > 12 or len(set(r["message_ids"])) != len(r["message_ids"]) or any(i not in messages for i in r["message_ids"]):
                    fail()
                if r["proposal"] is None:
                    if r["status"] not in ("interpreting", "failed", "cancelled", "superseded") or r["phase"] or r["effects"]:
                        fail()
                else:
                    p = r["proposal"]
                    self._validate_proposal(p, r, restoring=True)
                    if not isinstance(p, dict) or not set(PROPOSAL_FIELDS) <= set(p) or set(p) - set(PROPOSAL_FIELDS) - OPTIONAL_PROPOSAL_FIELDS or p["intent"] not in INTENTS or type(p["quantity"]) is not int or not 1 <= p["quantity"] <= 3:
                        fail()
                    if any(not isinstance(p[key], str) or len(p[key]) > TEXT_LIMITS.get(key, 64) for key in set(PROPOSAL_FIELDS) - {"quantity", "recipients"}):
                        fail()
                    if not isinstance(p["recipients"], list) or len(p["recipients"]) > 2 or len(set(p["recipients"])) != len(p["recipients"]) or any(a not in ACTORS for a in p["recipients"]):
                        fail()
                    if p["helper"] and p["helper"] not in ACTORS:
                        fail()
                    if p["intent"] in MEMORY_INTENTS:
                        if (r["phase"] not in (0, 1) or r["order_id"] or r["message_ids"]
                                or r["phase"] == 0 and (r["service"] != "none" or r["effects"] or r["status"] == "completed")
                                or r["phase"] == 1 and (r["service"] != "prepared" or r["effects"] != ["preference_recorded"] or r["status"] != "completed")):
                            fail()
                    elif p["intent"] == "schedule_reminder":
                        if (r["phase"] not in (0, 1) or r["order_id"] or r["message_ids"]
                                or r["phase"] == 0 and (r["service"] != "none" or r["effects"] or r["status"] == "completed")
                                or r["phase"] == 1 and (r["service"] != "prepared" or r["effects"] != ["reminder_scheduled"]
                                    or not any(reminder["target_message_id"] == p["item"] and reminder["hours"] == p["quantity"] for reminder in data["reminders"]))):
                            fail()
                    elif p["intent"] == "assess_home" and p["question"]:
                        if (r["phase"] not in (0, 1) or r["order_id"] or r["message_ids"]
                                or r["phase"] == 0 and (r["service"] != "none" or r["effects"])
                                or r["phase"] == 1 and (r["service"] != "prepared" or r["effects"] != ["assessment_prepared"]
                                    or r["status"] not in ("needs_clarification", "cancelled", "superseded", "failed"))):
                            fail()
                    elif p["intent"] not in HOSPITAL_INTENTS:
                        if r["phase"] == 0 and (r["service"] != "none" or r["effects"] or r["order_id"] or r["message_ids"]):
                            fail()
                        if r["phase"] >= 1 and "request_sent" not in r["effects"]:
                            fail()
                        if r["phase"] >= 2 and r["service"] not in ({"requested"} if p["intent"] == "carry_help" else {"prepared"} if p["intent"] == "assess_home" else {"acknowledged", "refused"}):
                            fail()
                        if p["intent"] in ("clarify", "unsupported") and (r["phase"] or r["effects"] or r["status"] not in ("needs_clarification", "unsupported", "cancelled", "superseded")):
                            fail()
                    if r["status"] == "completed" and p["intent"] not in ("change_appointment", "carry_help", "assess_home", "schedule_reminder", *HOSPITAL_INTENTS, *MEMORY_INTENTS) and r["service"] != "acknowledged":
                        fail()
                    if p["intent"] == "carry_help" and r["status"] == "completed" and "physical_placement_reported" not in r["effects"]:
                        fail()
                    if p["intent"] == "assess_home" and r["status"] == "completed" and "assessment_prepared" not in r["effects"]:
                        fail()
                    if p["intent"] in ("change_appointment", "carry_help") and r["status"] in ("completed", "waiting_physical") and (
                            "helper_accepted" not in r["effects"] or not any(messages[i]["response_day"] is not None for i in r["message_ids"])):
                        fail()
                    if p["intent"] == "change_appointment" and r["status"] == "completed" and r["service"] != "acknowledged":
                        fail()
                if r["service"] == "acknowledged" and "service_acknowledged" not in r["effects"] or r["service"] == "refused" and "service_refused" not in r["effects"]:
                    fail()
            order_keys = {"id", "request_id", "item", "quantity", "window", "cost", "status", "day", "acknowledged_day", "delivered_by", "placed_by", "evidence"}
            for o in orders.values():
                if set(o) != order_keys or o["request_id"] not in requests or o["id"] != "ord-" + o["request_id"] or o["item"] not in ITEMS or o["window"] not in WINDOWS:
                    fail()
                if type(o["quantity"]) is not int or not 1 <= o["quantity"] <= 3 or type(o["cost"]) not in (int, float) or o["cost"] != ITEMS[o["item"]]["unit_price"] * o["quantity"]:
                    fail()
                if o["status"] not in ("requested", "acknowledged", "refused", "cancelled", "delivered", "placed") or type(o["day"]) is not int or not 1 <= o["day"] <= data["day"]:
                    fail()
                if o["acknowledged_day"] is not None and (type(o["acknowledged_day"]) is not int or not o["day"] <= o["acknowledged_day"] <= data["day"]):
                    fail()
                if o["status"] in ("acknowledged", "delivered", "placed") and o["acknowledged_day"] is None:
                    fail()
                if o["delivered_by"] not in ("", "resident", *ACTORS) or o["placed_by"] not in ("", "resident", *ACTORS) or not isinstance(o["evidence"], str) or len(o["evidence"]) > 600:
                    fail()
                if o["status"] in ("delivered", "placed") and not o["delivered_by"] or o["status"] == "placed" and not o["placed_by"] or o["placed_by"] and o["status"] != "placed":
                    fail()
            message_keys = {"id", "request_id", "recipient", "kind", "body", "status", "day", "available_day", "read_day", "response_day", "completed_day", "metadata"}
            for m in messages.values():
                if set(m) != message_keys or m["request_id"] not in requests or m["recipient"] not in ACTORS or not m["id"].startswith(m["request_id"] + "-") or not m["id"].endswith("-" + m["recipient"]):
                    fail()
                if m["id"] not in requests[m["request_id"]]["message_ids"] or m["kind"] not in ("information", "travel", "carry_help", "hospital") or m["status"] not in ("sent", "available", "read", "accepted", "declined", "completed", "cancelled", "expired"):
                    fail()
                if m["kind"] == "hospital":
                    meta = m["metadata"]
                    if (not isinstance(meta, dict) or set(meta) != {"domain", "commitment_id", "kind", "version"} or meta["domain"] != "hospital"
                            or not DOMAIN_ID.fullmatch(meta["commitment_id"]) or meta["kind"] not in ("driver", "companion", "return", "pickup")
                            or type(meta["version"]) is not int or meta["version"] < 1):
                        fail()
                elif m["metadata"]:
                    fail()
                if not isinstance(m["body"], str) or len(m["body"]) > 600 or type(m["day"]) is not int or not 1 <= m["day"] <= data["day"]:
                    fail()
                for key in ("available_day", "read_day", "response_day", "completed_day"):
                    if m[key] is not None and (type(m[key]) is not int or not m["day"] <= m[key] <= data["day"]):
                        fail()
                if m["status"] in ("available", "read", "accepted", "declined", "completed") and m["available_day"] is None or m["status"] == "read" and m["read_day"] is None:
                    fail()
                if m["status"] in ("accepted", "declined", "completed") and (m["kind"] == "information" or m["response_day"] is None) or m["status"] == "completed" and m["completed_day"] is None:
                    fail()
            for h in data["history"]:
                if (set(h) != {"day", "minute", "actor", "event", "text"} or type(h["day"]) is not int or not 1 <= h["day"] <= data["day"]
                        or h["minute"] is not None and (type(h["minute"]) is not int or not 0 <= h["minute"] <= 1439)
                        or any(not isinstance(h[k], str) or len(h[k]) > 600 for k in ("actor", "event", "text"))):
                    fail()
            for index, reminder in enumerate(data["reminders"], 1):
                if (set(reminder) != {"id", "target_message_id", "source_request_id", "recipient", "day", "hours", "scheduled_minute", "due_minute", "status", "issued_minute", "receipt_id", "cancelled_day", "cancelled_minute"}
                        or reminder["id"] != "rem-" + str(index) or reminder["target_message_id"] not in messages
                        or type(reminder["day"]) is not int or not 1 <= reminder["day"] <= data["day"]
                        or type(reminder["hours"]) is not int or not 1 <= reminder["hours"] <= 3
                        or any(type(reminder[key]) is not int or not 0 <= reminder[key] <= 1439 for key in ("scheduled_minute", "due_minute"))
                        or reminder["due_minute"] != reminder["scheduled_minute"] + reminder["hours"] * 60
                        or reminder["status"] not in ("scheduled", "issued", "cancelled")):
                    fail()
                target = messages[reminder["target_message_id"]]
                owner = requests[target["request_id"]]
                if target["kind"] == "information" or target["recipient"] != reminder["recipient"] or target["day"] > reminder["day"]:
                    fail()
                if reminder["source_request_id"] is not None:
                    source = requests[reminder["source_request_id"]]
                    if source["proposal"] is None or source["proposal"]["intent"] != "schedule_reminder" or source["proposal"]["item"] != target["id"] or source["proposal"]["quantity"] != reminder["hours"]:
                        fail()
                if reminder["status"] != "cancelled":
                    if (reminder["day"] != data["day"] or not data["permissions"]["notify"] or self.duty_date(target) < data["date"]
                            or owner["status"] in TERMINAL or target["status"] not in ("available", "read")
                            or target["kind"] == "travel" and owner["appointment_version"] != data["shared"]["appointment_version"]
                            or reminder["cancelled_day"] is not None or reminder["cancelled_minute"] is not None):
                        fail()
                elif (type(reminder["cancelled_day"]) is not int or not reminder["day"] <= reminder["cancelled_day"] <= data["day"]
                        or type(reminder["cancelled_minute"]) is not int or not 0 <= reminder["cancelled_minute"] <= 1439):
                    fail()
                if reminder["receipt_id"]:
                    receipt = messages[reminder["receipt_id"]]
                    if (receipt["id"] != target["request_id"] + "-" + reminder["id"] + "-" + target["recipient"]
                            or receipt["kind"] != "information" or receipt["recipient"] != target["recipient"] or receipt["request_id"] != target["request_id"]
                            or receipt["day"] != reminder["day"] or type(reminder["issued_minute"]) is not int
                            or not reminder["due_minute"] <= reminder["issued_minute"] <= 1439
                            or reminder["status"] == "scheduled" or reminder["status"] == "cancelled" and receipt["status"] != "cancelled"):
                        fail()
                elif reminder["issued_minute"] is not None or reminder["status"] == "issued":
                    fail()
                if reminder["status"] == "scheduled" and reminder["due_minute"] <= data["clock_minute"]:
                    fail()
            for f in data["feedback"]:
                if set(f) != {"request_id", "day", "helped"} or f["request_id"] not in requests or type(f["helped"]) is not bool or type(f["day"]) is not int or not 1 <= f["day"] <= data["day"]:
                    fail()
            reply_ids = set()
            for reply in data["replies"]:
                if (set(reply) != {"id", "actor_id", "message", "decisions", "question", "day"} or not ID.fullmatch(reply["id"])
                        or reply["id"] in reply_ids or reply["actor_id"] not in ACTORS or not isinstance(reply["message"], str)
                        or not 1 <= len(reply["message"]) <= 2000 or not isinstance(reply["question"], str) or len(reply["question"]) > 400
                        or type(reply["day"]) is not int or not 1 <= reply["day"] <= data["day"]
                        or not isinstance(reply["decisions"], list) or len(reply["decisions"]) > 3):
                    fail()
                reply_ids.add(reply["id"])
                decisions = reply["decisions"]
                if reply["question"] and decisions or not reply["question"] and not decisions:
                    fail()
                decided = set()
                for decision in decisions:
                    if (set(decision) != {"message_id", "status"} or decision["message_id"] not in messages
                            or decision["message_id"] in decided or decision["status"] not in ("accepted", "declined")
                            or messages[decision["message_id"]]["recipient"] != reply["actor_id"]):
                        fail()
                    decided.add(decision["message_id"])
            if data["shared"] != self._shared_facts():
                fail()
        except (KeyError, TypeError, OverflowError, AttributeError, ValueError):
            fail()
