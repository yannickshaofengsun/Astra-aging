"""A fictional household week; explicit permissions and reports establish outcomes."""

from copy import deepcopy
from math import isfinite


PROFILE_FIELDS = {
    "age_band": ["65–74", "75–84", "85+"],
    "setting": ["urban", "suburban", "rural"],
    "transport": ["self_drives", "public_transit", "helper"],
    "language": ["English", "Spanish", "other"],
    "interaction": ["brief", "detailed"],
    "preferred_activity": ["garden", "library", "quiet_time"],
}
PROFILES = [
    {"id": "nearby", "label": "Living alone, nearby support", "household": "One resident",
     "age_band": "75–84", "setting": "suburban", "transport": "helper", "language": "English",
     "interaction": "brief", "preferred_activity": "garden", "helper": "Alex", "helper_available": True},
    {"id": "couple", "label": "Couple sharing responsibilities", "household": "Two residents",
     "age_band": "65–74", "setting": "urban", "transport": "public_transit", "language": "Spanish",
     "interaction": "detailed", "preferred_activity": "library", "helper": "Sam", "helper_available": True},
    {"id": "remote", "label": "Living alone, remote family", "household": "One resident; remote family",
     "age_band": "85+", "setting": "rural", "transport": "self_drives", "language": "English",
     "interaction": "brief", "preferred_activity": "quiet_time", "helper": "Jordan", "helper_available": False},
]
PERMISSIONS = ("calendar", "backup_transport", "paperwork", "supplies", "home_help")
SCENARIOS = {
    "appointment_conflict": "Clinic moves appointment into a chosen activity",
    "driver_decline": "Usual driver declines",
    "papers_moved": "Required papers have moved",
    "supply_unavailable": "Usual household supply is unavailable",
    "event_cancelled": "Community venue cancels",
    "home_comfort": "Resident reports an awkward-to-reach item",
    "device_missing": "Fictional home-device reading is missing",
}
ROUTINES = {
    "week_ack_appointment": ("calendar", "Send chosen slot; receive mock clinic acknowledgment"),
    "week_request_backup": ("backup_transport", "Request fictional outbound and return help"),
    "week_request_papers": ("paperwork", "Send one delegated paperwork preparation request"),
    "week_order_supplies": ("supplies", "Place fictional replacement order — $18.50"),
    "week_cancel_event": ("calendar", "Acknowledge cancellation of only this activity's arrangements"),
    "week_book_activity": ("calendar", "Receive mock acknowledgment for the chosen alternative"),
    "week_request_home_help": ("home_help", "Send the chosen home-help request"),
}


class WeekPlan:
    """One bounded week. The host owns locks, revisions, and the existing home facts."""

    def __init__(self, host):
        self.host = host
        self._start(PROFILES[0])

    def _start(self, profile, restore=False):
        self.profile = deepcopy(profile)
        self.mode = "assisted"
        self.permissions = {key: False for key in PERMISSIONS}
        self.permissions["supply_cap"] = 25.0
        self.history = []
        self.profile_confirmed = False
        self.permissions_confirmed = False
        self.injected = []
        self.appointment_version = 1
        self.appointment_status = "acknowledged"
        self.appointment_evidence = "Existing fictional Tuesday appointment."
        self.selected_slot = None
        self.backup_version = None
        self.return_status = "not_recorded"
        self.ride_evidence = "Existing pickup accepted; return travel is not recorded."
        self.papers_requested = False
        self.papers_staged = False
        self.papers_needed = False
        self.papers_evidence = "Current reported document location is confirmed in the simulation; checklist checking and physical staging have not been reported."
        self.supplies = {"status": "stocked", "item": "Unscented paper towels",
                         "substitute": "Unscented recycled paper towels", "cost": 18.5,
                         "preapproved_equivalent": True, "one_time_approval": False,
                         "evidence": "Fictional starting supply is available."}
        self.community = {"title": self._activity_title(), "date": "2026-09-17", "time": "14:00",
                          "status": "confirmed", "arrangement": "confirmed", "choice": None,
                          "evidence": "Fictional chosen activity and its own arrangements accepted."}
        self.comfort = {"status": "no_request", "observation": None, "choice": None,
                        "helped": None, "placement_reported": False,
                        "evidence": "No home-help need has been reported."}
        if restore:
            self.host.appointment.update(day="Tuesday", date="2026-09-15", time="10:00", pickup="09:15")
            self.host.transport.update(status="confirmed", person="Alex", for_date="2026-09-15")
            self.host.documents.update(location="Entrance shelf", status="confirmed", recorded_at="Tuesday, 08:00")
            self.host._actual_document_location = "Entrance shelf"
            self.host._reset_game()

    def _activity_title(self):
        return {"garden": "Community garden gathering", "library": "Library social hour",
                "quiet_time": "Quiet reading time"}[self.profile["preferred_activity"]]

    @staticmethod
    def _button(action, label, payload=None):
        result = {"action": action, "label": label}
        if payload is not None:
            result["payload"] = payload
        return result

    def _record(self, participant, category, text):
        self.history.append({"participant": participant, "category": category, "text": text,
                             "revision": self.host.revision + 1})

    def _accounting(self):
        humans = [event for event in self.history if event["participant"] != "agent"]
        by_person = {person: sum(event["participant"] == person for event in humans)
                     for person in ("resident", "family")}
        by_category = {category: sum(event["category"] == category for event in humans)
                       for category in ("setup", "decision", "reply", "administration", "supervision", "correction")}
        return {"human_total": len(humans), "agent_total": len(self.history) - len(humans),
                "human_by_participant": by_person, "human_by_category": by_category,
                "setup_total": by_category["setup"], "repeat_week_total": len(humans) - by_category["setup"],
                "events": deepcopy(self.history),
                "note": "Interaction counts from this run, including setup and supervision. "
                        "Repeat-week total excludes setup only; no time savings are estimated."}

    def _routine_needed(self):
        result = []
        if self.appointment_status == "selected":
            result.append("week_ack_appointment")
        if (self.appointment_status == "acknowledged" and self.host.transport["status"] != "confirmed"
                and self.backup_version != self.appointment_version):
            result.append("week_request_backup")
        if self.papers_needed and not self.papers_staged and not self.papers_requested:
            result.append("week_request_papers")
        if self.supplies["status"] == "needs_order":
            result.append("week_order_supplies")
        if self.community["arrangement"] == "cancel_pending":
            result.append("week_cancel_event")
        if self.community["status"] == "alternative_selected" and self.community["arrangement"] == "cancelled":
            result.append("week_book_activity")
        if self.comfort["status"] == "chosen":
            result.append("week_request_home_help")
        return result

    def _permitted(self, action):
        permission = ROUTINES[action][0]
        if action == "week_order_supplies":
            return self.supplies["one_time_approval"] or (
                self.permissions["supplies"] and self.supplies["preapproved_equivalent"]
                and self.supplies["cost"] <= self.permissions["supply_cap"])
        return self.permissions[permission]

    def _controls(self, role):
        c = {group: [] for group in ("scenario", "actions", "decisions", "helpers", "routine")}
        b = self._button
        if role == "resident":
            c["scenario"] = [b("week_inject", label, {"scenario": key}) for key, label in SCENARIOS.items()
                             if key not in self.injected and not (key in ("home_comfort", "device_missing")
                             and self.comfort["status"] != "no_request")
                             and not (key in ("appointment_conflict", "event_cancelled")
                                      and self.community["status"] != "confirmed")]
            c["actions"] = [b("week_reset", "Reset this fictional week"),
                b("week_mode", "Use individual manual administration" if self.mode == "assisted"
                  else "Use permissioned assistance", {"mode": "manual" if self.mode == "assisted" else "assisted"})]
            if not all(self.permissions[key] for key in PERMISSIONS):
                c["actions"].append(b("week_permissions", "Grant these fictional routine permissions",
                                      {**{key: True for key in PERMISSIONS}, "supply_cap": self.permissions["supply_cap"]}))
            if any(self.permissions[key] for key in PERMISSIONS):
                c["actions"].append(b("week_permissions", "Revoke routine permissions", {key: False for key in PERMISSIONS}))
            if self.appointment_status == "conflict":
                c["decisions"] += [b("week_choose_slot", "Keep activity; choose Friday 10:00 appointment", {"slot": "keep_activity"}),
                                    b("week_choose_slot", f"Keep {self.host.appointment['day']} {self.host.appointment['time']} appointment; release activity", {"slot": "keep_appointment"})]
            if (self.appointment_status == "acknowledged" and self.profile["transport"] in ("self_drives", "public_transit")
                    and (self.host.transport["status"] != "confirmed" or self.return_status != "confirmed")):
                c["decisions"].append(b("week_confirm_own_travel", "I have arranged my own outbound and return travel for this appointment"))
            if self.supplies["status"] == "needs_order":
                if not self._permitted("week_order_supplies") and self.mode == "assisted":
                    c["decisions"].append(b("week_choose_supply", "Approve this $18.50 fictional substitute once", {"choice": "approve"}))
                c["decisions"].append(b("week_choose_supply", "Skip the replacement purchase", {"choice": "skip"}))
            if self.community["status"] in ("cancel_pending", "decision_pending") and self.community["choice"] is None:
                if self.profile["preferred_activity"] != "quiet_time":
                    c["decisions"].append(b("week_choose_activity", "Choose the sample Friday 14:00 alternative", {"choice": "alternative"}))
                c["decisions"].append(b("week_choose_activity", "Leave the time free", {"choice": "free"}))
            if self.comfort["status"] == "decision_pending":
                if self.comfort["observation"] == "missing_reading":
                    c["decisions"].append(b("week_choose_comfort", "Request a check of the fictional device", {"choice": "check"}))
                else:
                    c["decisions"].append(b("week_choose_comfort", "Try moving the item to existing storage", {"choice": "storage"}))
                    c["decisions"].append(b("week_choose_comfort", "Prepare an illustrative $25 bedside-caddy option", {"choice": "equipment"}))
                c["decisions"].append(b("week_choose_comfort", "Leave things as they are", {"choice": "leave"}))
            if self.comfort["status"] == "reported":
                c["decisions"] += [b("week_comfort_feedback", "That helped", {"helped": True}),
                                    b("week_comfort_feedback", "That did not help", {"helped": False})]
            routine = self._routine_needed()
            if self.mode == "manual":
                c["routine"] = [b(action, ROUTINES[action][1]) for action in routine]
            elif any(self._permitted(action) for action in routine):
                c["routine"] = [b("week_run", "Let the assistant complete permitted administration")]
        else:
            available = self.profile["helper_available"]
            c["helpers"].append(b("week_helper_availability", "I am unavailable for physical help" if available
                                  else "I am available for physical help", {"available": not available}))
            if self.backup_version == self.appointment_version and self.host.transport["status"] == "needs_confirmation":
                if available:
                    c["helpers"].append(b("week_accept_backup", "Accept this appointment's outbound and return help"))
                c["helpers"].append(b("week_decline_backup", "Decline this backup request"))
            if available and self.papers_requested and not self.papers_staged:
                c["helpers"].append(b("week_stage_papers", "I checked and staged the papers on the entrance shelf"))
            if self.supplies["status"] == "ordered":
                c["helpers"].append(b("week_deliver_supplies", "Report observed delivery of the fictional supply"))
            if available and self.supplies["status"] == "delivered":
                c["helpers"].append(b("week_place_supplies", "I placed the delivered supply in storage"))
            if available and self.comfort["status"] == "requested":
                c["helpers"].append(b("week_report_home_help", "I completed the requested physical change or device check"))
        return c

    def _exceptions(self):
        result = []
        if self.appointment_status == "conflict":
            result.append("The moved appointment overlaps a chosen activity; a resident choice is needed.")
        if self.host.transport["status"] == "confirmed" and self.return_status != "confirmed":
            result.append("The pickup is accepted, but required return travel is not recorded or accepted.")
        if self.mode == "assisted":
            missing = [ROUTINES[action][1] for action in self._routine_needed() if not self._permitted(action)]
            if missing:
                result.append("Outside current permission: " + "; ".join(missing) + ".")
        if self.backup_version == self.appointment_version and self.host.transport["status"] != "confirmed":
            result.append("Outbound and return travel remain unaccepted." if self.profile["helper_available"]
                          else "The named backup is unavailable; both travel legs remain unresolved.")
        if not self.profile["helper_available"] and (self.papers_requested and not self.papers_staged
                or self.supplies["status"] == "delivered" or self.comfort["status"] == "requested"):
            result.append("Requested physical preparation has no available local helper; it is not complete.")
        if self.comfort["status"] == "unresolved":
            result.append("The resident said the change did not help; the comfort need remains unresolved.")
        return result

    def view(self, role):
        if role not in ("resident", "family"):
            raise ValueError("Choose resident or family.")
        appointment = {key: value for key, value in self.host.appointment.items() if key != "reason" or role == "resident"}
        appointment.update(id="appointment", label="Fictional appointment", status=self.appointment_status,
                           version=self.appointment_version, owner="resident", dependencies=["transport", "paperwork"],
                           evidence=self.appointment_evidence)
        community = dict(self.community, id="community", label="Chosen activity", owner="resident", dependencies=["community_arrangements"])
        transport_status = self.host.transport["status"]
        if transport_status == "confirmed" and self.return_status != "confirmed":
            transport_status = "partially_confirmed"
        papers_status = ("prepared" if self.papers_staged else "requested" if self.papers_requested else
                         "location_known" if self.host.documents["status"] == "confirmed" else "location_uncertain")
        tasks = [
            {"id": "transport", "label": "Appointment travel", "status": transport_status, "owner": self.profile["helper"],
             "dependencies": ["appointment"], "evidence": self.ride_evidence,
             "outbound": deepcopy(self.host.transport), "return_status": self.return_status, "requested_version": self.backup_version},
            {"id": "paperwork", "label": "Required-paper checklist and preparation", "status": papers_status,
             "owner": self.profile["helper"], "dependencies": ["appointment"], "evidence": self.papers_evidence,
             "checklist": ["Appointment letter", "Requested household paperwork"], "reported_location": deepcopy(self.host.documents),
             "staging_reported": self.papers_staged},
            dict(self.supplies, id="supplies", label="Household supplies", owner="resident", dependencies=[]),
            {"id": "community_arrangements", "label": "Activity's own arrangements", "status": self.community["arrangement"],
             "owner": "resident", "dependencies": ["community"], "evidence": self.community["evidence"]},
            dict(self.comfort, id="comfort", label="Home comfort and observations", owner="resident", dependencies=[]),
        ]
        return deepcopy({"profile": self.profile, "profiles": [{"id": p["id"], "label": p["label"]} for p in PROFILES],
            "profile_fields": PROFILE_FIELDS, "mode": self.mode, "permissions": self.permissions,
            "permission_fields": {key: "boolean" for key in PERMISSIONS} | {"supply_cap": {"type": "number", "min": 0, "max": 100}},
            "commitments": [appointment, community], "tasks": tasks, "controls": self._controls(role),
            "exceptions": self._exceptions(), "accounting": self._accounting(),
            "adaptation": self._adaptation_view(),
            "fixture": {"is_synthetic": True, "week_of": "2026-09-14", "country": "United States",
                        "service_rules": "Mock clinic slots: Thursday 14:00 or Friday 10:00; response immediate. "
                            "One named backup controls acceptance of both travel legs. One $18.50 substitute offer, "
                            "available through Friday noon; fictional store acknowledgment is immediate. "
                            "Activity alternative Friday 14:00, one household place; immediate mock response. "
                            "No clock advances or real-world transaction occur."},
            "notice": "Three authored fictional situations, not a representative U.S. sample. "
                      "Age and setting do not infer ability. Requests and acknowledgments are simulated; "
                      "physical completion requires a person's report."})

    def _adaptation_view(self):
        if self.comfort["choice"] != "equipment":
            return None
        return {"title": "Bedside storage caddy", "price_usd": 25,
                "fit": "Unmeasured; dimensions, reach, and load are unknown.",
                "order_state": "prepared", "is_synthetic": True,
                "placement_reported": self.comfort["placement_reported"],
                "preview_image": "/assets/sketch-adapted.png" if getattr(self.host, "home", {}).get("id") == "sketch" else None,
                "notice": "Illustrative equipment and prepared request only; no product, stock, or purchase is verified."}

    def _validate_payload(self, payload, allowed):
        if not isinstance(payload, dict) or not payload or set(payload) - set(allowed):
            raise ValueError("Use only the supported fields for this action.")

    def apply(self, action, role, payload=None):
        if role not in ("resident", "family") or not isinstance(action, str):
            raise ValueError("Choose a supported household action and role.")
        payload = {} if payload is None else payload
        if not isinstance(payload, dict):
            raise ValueError("Action details must be an object.")
        # Editable native form fields are validated here; state-dependent buttons below
        # must still be present in the current role's public action catalog.
        if action in ("week_select_profile", "week_configure", "week_permissions"):
            if role != "resident":
                raise ValueError("The resident controls their profile and standing permissions.")
            if action == "week_select_profile":
                self._validate_payload(payload, ["id"])
                match = next((p for p in PROFILES if p["id"] == payload.get("id")), None)
                if match is None:
                    raise ValueError("Choose one of the fictional household situations.")
                self._start(match, restore=True)
                return "Selected a fresh fictional household week; private scenario state was reset."
            if action == "week_configure":
                self._validate_payload(payload, PROFILE_FIELDS)
                if any(value not in PROFILE_FIELDS[key] for key, value in payload.items()):
                    raise ValueError("Choose a listed profile value.")
                changes = {key: value for key, value in payload.items() if self.profile[key] != value}
                if not changes and self.profile_confirmed:
                    raise ValueError("Those profile values are already recorded.")
                self.profile.update(changes)
                text = "Resident recorded independent fictional profile choices: " + ", ".join(payload) + "."
                category = "correction" if self.profile_confirmed else "setup"
                self.profile_confirmed = True
            else:
                self._validate_payload(payload, self.permissions)
                for key, value in payload.items():
                    if key == "supply_cap":
                        if type(value) not in (int, float) or not isfinite(value) or not 0 <= value <= 100:
                            raise ValueError("The fictional supply cap must be between $0 and $100.")
                    elif type(value) is not bool:
                        raise ValueError("Standing permissions must be true or false.")
                if self.permissions_confirmed and all(self.permissions[key] == value for key, value in payload.items()):
                    raise ValueError("Those permissions are already recorded.")
                revoked = any(self.permissions[key] and value is False for key, value in payload.items() if key in PERMISSIONS)
                self.permissions.update(payload)
                if revoked or "supply_cap" in payload:
                    self.supplies["one_time_approval"] = False
                text = "Resident updated bounded fictional permissions; completed acknowledgments remain history."
                category = "correction" if self.permissions_confirmed else "setup"
                self.permissions_confirmed = True
            self._record(role, category, text)
            return text
        if action in ("week_comfort_feedback", "week_helper_availability"):
            key = "helped" if action == "week_comfort_feedback" else "available"
            if type(payload.get(key)) is not bool:
                raise ValueError("Use true or false for this reported choice.")
        controls = [button for group in self._controls(role).values() for button in group]
        if not any(button["action"] == action and button.get("payload", {}) == payload for button in controls):
            raise ValueError("That action is unavailable, already resolved, or needs a current decision first.")
        if action == "week_reset":
            self._start(self.profile, restore=True)
            return "Reset the fictional week; no external arrangement changed."
        if action == "week_mode":
            self.mode = payload["mode"]
            return "Changed the demonstration administration mode."
        if action == "week_inject":
            return self._inject(payload["scenario"])
        if action == "week_run":
            completed = []
            # ponytail: at most seven known routine types; a bounded pass handles newly
            # unblocked dependencies without an autonomous loop or task framework.
            for _ in range(len(ROUTINES)):
                eligible = [a for a in self._routine_needed() if self._permitted(a)]
                if not eligible:
                    break
                for routine in eligible:
                    text = self._routine(routine)
                    completed.append(text)
                    self._record("agent", "administration", text)
            text = f"Assistant completed {len(completed)} permitted fictional administrative steps; physical reports remain separate."
            self._record(role, "supervision", text)
            return text
        if action in ROUTINES:
            text = self._routine(action)
            self._record(role, "administration", text)
            return text
        text = self._human_action(action, payload)
        category = "reply" if role == "family" else "decision"
        self._record(role, category, text)
        return text

    def _invalidate_ride(self):
        self.host.transport.update(status="needs_confirmation", person=None, for_date=None)
        self.backup_version = None
        self.return_status = "needs_confirmation"
        self.ride_evidence = "Appointment changed; neither travel leg is accepted for this version."

    def _inject(self, scenario):
        self.injected.append(scenario)
        if scenario == "appointment_conflict":
            day = "Thursday" if self.community["date"] == "2026-09-17" else "Friday"
            self.host.appointment.update(day=day, date=self.community["date"], time=self.community["time"], pickup="13:15")
            self.appointment_version += 1
            self.appointment_status = "conflict"
            self.appointment_evidence = f"Mock clinic offered {day} {self.community['time']}, conflicting with the chosen activity."
            self.selected_slot = None
            self._invalidate_ride()
        elif scenario == "driver_decline":
            self.host.transport.update(status="declined", person=None, for_date=None)
            self.backup_version = None
            self.return_status = "declined"
            self.ride_evidence = "Fictional usual driver declined; no accepted backup or return travel."
        elif scenario == "papers_moved":
            self.host._actual_document_location = "Bedroom drawer"
            self.host.documents["status"] = "last_known"
            self.papers_requested = False
            self.papers_staged = False
            self.papers_needed = True
            self.papers_evidence = "The recorded entrance-shelf location is last known; the checklist remains applicable."
        elif scenario == "supply_unavailable":
            self.supplies.update(status="needs_order", one_time_approval=False,
                                 evidence="Mock store reports the usual supply unavailable; an $18.50 equivalent is offered.")
        elif scenario == "event_cancelled":
            self.community.update(status="cancel_pending", arrangement="cancel_pending", choice=None,
                                  evidence="Mock venue cancelled this event; only its own arrangements need closure.")
        else:
            missing = scenario == "device_missing"
            self.comfort.update(status="decision_pending", observation="missing_reading" if missing else "awkward_reach",
                evidence="Fictional device reading unavailable; no clinical interpretation." if missing
                         else "Resident reports an often-used item is awkward to reach; no measured safety conclusion.")
        return "Introduced a fictional scenario: " + SCENARIOS[scenario] + "."

    def _routine(self, action):
        if action == "week_ack_appointment":
            slot = self.selected_slot
            if slot == "keep_activity":
                self.host.appointment.update(day="Friday", date="2026-09-18", time="10:00", pickup="09:15")
            self.appointment_version += 1
            self.appointment_status = "acknowledged"
            self.appointment_evidence = "Mock clinic acknowledged the resident's selected slot. Attendance is not established."
            self._invalidate_ride()
            return "Mock clinic acknowledged the chosen appointment; its new travel is still pending."
        if action == "week_request_backup":
            self.backup_version = self.appointment_version
            self.host.transport.update(status="needs_confirmation", person=None, for_date=None)
            self.return_status = "requested"
            self.ride_evidence = f"Requested {self.profile['helper']} for {self.host.appointment['day']} outbound and return travel, appointment version {self.appointment_version}; no acceptance yet."
            return self.ride_evidence
        if action == "week_request_papers":
            self.papers_requested = True
            self.papers_evidence = f"One preparation request sent to {self.profile['helper']}; physical check and staging are unreported."
            return self.papers_evidence
        if action == "week_order_supplies":
            self.supplies.update(status="ordered", one_time_approval=False,
                                 evidence="Mock store acknowledged the $18.50 substitute order. Delivery and placement are unreported.")
            return self.supplies["evidence"]
        if action == "week_cancel_event":
            self.community["arrangement"] = "cancelled"
            self.community["status"] = {None: "decision_pending", "free": "free", "alternative": "alternative_selected"}[self.community["choice"]]
            self.community["evidence"] = "Mock cancellation acknowledged for this activity and its own arrangements only."
            return self.community["evidence"]
        if action == "week_book_activity":
            self.community.update(title=self._activity_title() + " — sample alternative", date="2026-09-18", time="14:00",
                                  status="confirmed", arrangement="confirmed", evidence="Mock venue acknowledged the chosen alternative; attendance is unreported.")
            return self.community["evidence"]
        self.comfort.update(status="requested", evidence="Chosen home-help request sent; physical work is unreported.")
        return self.comfort["evidence"]

    def _human_action(self, action, payload):
        if action == "week_choose_slot":
            self.selected_slot = payload["slot"]
            self.appointment_status = "selected"
            self.appointment_evidence = "Resident chose an offered appointment slot; mock clinic acknowledgment is pending."
            if self.selected_slot == "keep_appointment":
                self.community.update(status="cancel_pending", arrangement="cancel_pending", choice="free",
                                      evidence="Resident chose the conflicting appointment and released this activity; cancellation acknowledgment pending.")
            return "Resident chose how to resolve the appointment/activity conflict."
        if action == "week_confirm_own_travel":
            self.host.transport.update(status="confirmed", person="Resident", for_date=self.host.appointment["date"])
            self.backup_version = None
            self.return_status = "confirmed"
            self.ride_evidence = "Resident reports their own outbound and return plan for this appointment version; no transport-provider acceptance is inferred."
            return self.ride_evidence
        if action == "week_helper_availability":
            self.profile["helper_available"] = payload["available"]
            if not payload["available"] and self.host.transport["status"] == "confirmed" and self.backup_version == self.appointment_version:
                self.host.transport.update(status="declined", person=None, for_date=None)
                self.return_status = "declined"
                self.ride_evidence = "The accepting helper withdrew availability; both travel legs are unresolved."
            return "Helper reported their own physical-help availability."
        if action in ("week_accept_backup", "week_decline_backup"):
            accept = action == "week_accept_backup"
            self.host.transport.update(status="confirmed" if accept else "declined", person=self.profile["helper"] if accept else None,
                                       for_date=self.host.appointment["date"] if accept else None)
            self.return_status = "confirmed" if accept else "declined"
            self.ride_evidence = f"{self.profile['helper']} {'accepted' if accept else 'declined'} outbound and return travel for the current appointment version {self.appointment_version}."
            return self.ride_evidence
        if action == "week_stage_papers":
            self.papers_staged = True
            self.host._actual_document_location = "Entrance shelf"
            self.host.documents.update(location="Entrance shelf", status="confirmed", recorded_at=f"Helper report, update {self.host.revision + 1}")
            self.papers_evidence = "Authorized helper reports papers checked and staged at the entrance shelf. No duplicate resident confirmation is needed."
            return self.papers_evidence
        if action == "week_choose_supply":
            if payload["choice"] == "skip":
                self.supplies.update(status="declined", one_time_approval=False, evidence="Resident chose to skip the replacement purchase.")
            else:
                self.supplies.update(one_time_approval=True, evidence="Resident explicitly approved this $18.50 equivalent once; no order acknowledgment yet.")
            return self.supplies["evidence"]
        if action in ("week_deliver_supplies", "week_place_supplies"):
            placed = action == "week_place_supplies"
            self.supplies.update(status="placed" if placed else "delivered", evidence="Helper reports the delivered supply placed in storage." if placed
                                 else "Helper reports observed delivery; storage placement is unreported.")
            return self.supplies["evidence"]
        if action == "week_choose_activity":
            choice = payload["choice"]
            self.community["choice"] = choice
            if self.community["arrangement"] == "cancelled":
                self.community["status"] = "alternative_selected" if choice == "alternative" else "free"
            return "Resident chose a sample alternative." if choice == "alternative" else "Resident chose to leave the time free; that is a complete valid choice."
        if action == "week_choose_comfort":
            choice = payload["choice"]
            self.comfort.update(choice=choice, status="declined" if choice == "leave" else "chosen",
                                evidence="Resident chose to leave things as they are." if choice == "leave" else "Resident chose a specific home-help option; no physical work is established.")
            return self.comfort["evidence"]
        if action == "week_report_home_help":
            self.comfort.update(status="reported", placement_reported=self.comfort["choice"] in ("storage", "equipment"),
                                evidence="Helper reports the chosen physical change or device check. Resident feedback is still pending.")
            return self.comfort["evidence"]
        helped = payload["helped"]
        self.comfort.update(status="helped" if helped else "unresolved", helped=helped,
                            evidence="Resident reports that the chosen change helped." if helped else "Resident reports the chosen change did not help; need remains unresolved.")
        return self.comfort["evidence"]

    def legacy_changed(self, action):
        """Keep the old controls and weekly cards on the same household facts."""
        if action == "reschedule":
            self.appointment_version += 1
            self.appointment_status = "acknowledged"
            self.selected_slot = None
            self.appointment_evidence = "Appointment moved through the existing fictional appointment control."
            self._invalidate_ride()
        elif action in ("confirm_ride", "decline_ride"):
            self.backup_version = None
            self.return_status = "not_recorded"
            self.ride_evidence = "Existing control recorded pickup availability only; return travel is not recorded."
        elif action == "move_documents":
            self.papers_requested = False
            self.papers_staged = False
            self.papers_needed = True
            self.papers_evidence = "Document location is last known; checklist retained."
        elif action == "confirm_documents":
            self.papers_evidence = "Resident explicitly checked the current document location."
