"""A bounded, symbolic outing rehearsal. Observations never come from model prose."""

from copy import deepcopy
from datetime import date, datetime, timedelta

PERMISSIONS = ("coordinator", "backup_helper", "robot_transport", "main_route", "alternate_route")
TITLE = "Prepare for the changed appointment"
NOTICE = ("Demo outing: the clock, helper replies, and robot movement are simulated. Routes are not measured. "
          "No real trip or robot action occurs; route safety and attendance remain unverified.")
PRIMARY = "Alex (primary helper)"
BACKUP = "Morgan (backup helper)"


def _item(last_known):
    return {"last_known": last_known, "location": None, "status": "last_known"}


def _blank():
    return {"schema": 1, "active": False, "status": "idle", "clock_minutes": 0,
            "deadline_minutes": 90, "appointment_version": 0,
            "appointment": {"day": "Tuesday", "date": "2026-09-15", "time": "10:00", "pickup": "09:15"},
            "opted_in": False, "permissions": dict.fromkeys(PERMISSIONS, False),
            "known": {"bag": _item("R1"), "documents": _item("Entrance shelf"),
                      "primary": "not_requested", "backup": "not_requested", "travel": "not_confirmed",
                      "main_route": "unknown", "alternate_route": "unknown",
                      "search_requested": False, "loading_requested": False,
                      "documents_staged": False, "helper_loaded": False},
            "robot": {"capability": "carry_preloaded_bag", "status": "empty", "position": "Storage",
                      "route": None, "step": 0, "report": "No load or movement has been reported."},
            "world": {"bag_zone": "Storage", "documents_zone": "R1", "primary_available": False,
                      "main_blocked": True, "alternate_usable": False},
            "events": [], "event_count": 0}


class Mission:
    """Host supplies locking and revision validation; this object owns one mission."""

    def __init__(self, host):
        self.host = host
        self.state = _blank()

    @staticmethod
    def _button(action, label, payload=None):
        return {"action": action, "label": label, **({"payload": payload} if payload is not None else {})}

    def _record(self, actor, action, result):
        s = self.state
        s["event_count"] += 1
        s["events"].append({"actor": actor, "action": action, "result": result, "time": s["clock_minutes"]})
        # ponytail: keep the latest 200 audit entries; full durable audit is outside this local rehearsal.
        s["events"] = s["events"][-200:]
        return result

    def _current(self):
        return (self.state["appointment_version"] == self.host.week.appointment_version
                and self.state["appointment"] == {k: self.host.appointment[k] for k in self.state["appointment"]})

    def _ready(self):
        s, k = self.state, self.state["known"]
        return (s["opted_in"] and self._current() and k["travel"] == "confirmed"
                and self.host.transport["status"] == "confirmed" and self.host.transport["person"] == BACKUP
                and self.host.transport["for_date"] == s["appointment"]["date"]
                and self.host.week.return_status == "confirmed"
                and self.host.week.return_version == s["appointment_version"]
                and self.host.week.return_person == BACKUP and self._shared_evidence_matches()
                and k["documents_staged"] and k["helper_loaded"]
                and s["world"]["bag_zone"] == s["world"]["documents_zone"] == "Departure"
                and s["robot"]["status"] == "delivered" and s["clock_minutes"] < s["deadline_minutes"])

    def _update_status(self):
        s = self.state
        if s["status"] != "preparing":
            return
        if s["clock_minutes"] >= s["deadline_minutes"]:
            s["status"] = "overdue"
            if s["robot"]["status"] != "delivered":
                s["robot"].update(status="stopped", report="Deadline reached; delivery stopped and departure readiness is unresolved.")
        elif self._ready():
            s["status"] = "ready_to_leave"

    def _controls(self, role):
        s, k, p, r = self.state, self.state["known"], self.state["permissions"], self.state["robot"]
        controls = {actor: [] for actor in ("resident", "family", "coordinator")}
        c, b = controls[role], self._button
        if role == "resident":
            c.append(b("mission_reset" if s["active"] else "mission_start",
                       "Restart appointment preparation" if s["active"] else "Prepare for the appointment"))
        if not s["active"] or s["status"] != "preparing" or not self._current():
            return controls
        if role == "resident":
            c += [b("mission_cancel", "Cancel appointment preparation"),
                  b("mission_advance_time", "Advance demo clock by 5 minutes", {"minutes": 5}),
                  b("mission_advance_time", "Advance demo clock by 15 minutes", {"minutes": 15})]
            if not s["opted_in"]:
                c.append(b("mission_opt_in", "I choose to prepare for this appointment"))
            if s["opted_in"] and k["search_requested"]:
                for item in ("bag", "documents"):
                    if k[item]["status"] == "last_known":
                        c.append(b("mission_check_" + item, "Check the last-known " + item + " location"))
                    elif k[item]["status"] == "not_found":
                        c.append(b("mission_observe_" + item, "Report finding the " + item + " during the search"))
            if k["main_route"] == "blocked" and k["alternate_route"] == "unknown":
                c += [b("mission_observe_alternate", "Report an observed usable alternate route", {"usable": True}),
                      b("mission_observe_alternate", "Report no usable alternate route", {"usable": False})]
        elif role == "family":
            if k["primary"] == "requested":
                c.append(b("mission_primary_decline", PRIMARY + ": report unavailable"))
            if k["backup"] == "requested" and p["backup_helper"]:
                c += [b("mission_backup_accept", BACKUP + ": accept preparation help"),
                      b("mission_backup_decline", BACKUP + ": decline this request")]
            if k["backup"] == "accepted" and p["backup_helper"]:
                if k["travel"] == "not_confirmed":
                    c.append(b("mission_confirm_travel", BACKUP + ": confirm outbound and return for this appointment"))
                if k["loading_requested"] and not k["documents_staged"] and all(
                        k[item]["status"] == "located" for item in ("bag", "documents")):
                    c.append(b("mission_stage_documents", BACKUP + ": report putting the observed documents in the bag"))
                if k["documents_staged"] and not k["helper_loaded"]:
                    c.append(b("mission_load_robot", BACKUP + ": report loading the prepared bag onto the robot"))
        elif s["opted_in"] and p["coordinator"]:
            if k["primary"] == "not_requested":
                c.append(b("mission_request_primary", "Ask Alex about availability"))
            if k["primary"] == "declined" and k["backup"] == "not_requested" and p["backup_helper"]:
                c.append(b("mission_request_backup", "Ask Morgan for backup help"))
            if not k["search_requested"]:
                c.append(b("mission_request_search", "Ask the resident to check the last-known item locations"))
            if k["backup"] == "accepted" and p["backup_helper"] and not k["loading_requested"] and all(
                    k[item]["status"] == "located" for item in ("bag", "documents")):
                c.append(b("mission_request_loading", "Ask the helper to pack the papers and load the bag"))
            if k["helper_loaded"] and p["robot_transport"]:
                if r["status"] in ("loaded", "stopped") and k["main_route"] != "blocked" and p["main_route"]:
                    c.append(b("mission_dispatch_main", "Send the loaded robot along the main route"))
                if r["status"] in ("blocked", "stopped") and k["alternate_route"] == "usable" and p["alternate_route"]:
                    c.append(b("mission_dispatch_alternate", "Use the checked alternative route"))
                if r["status"] == "moving" and p[r["route"] + "_route"]:
                    c.append(b("mission_move_robot", "Check and move one route step"))
            c.append(b("mission_wait", "Wait and explain what is needed"))
        return controls

    def _unresolved(self):
        s, k = self.state, self.state["known"]
        if not s["active"]:
            return []
        if s["status"] == "ready_to_leave":
            return []
        result = []
        if s["status"] in ("cancelled", "invalidated", "overdue"):
            result.append({"cancelled": "Resident cancelled; pending work and delivery are stopped.",
                           "invalidated": "Shared appointment or item facts changed; replay before new work.",
                           "overdue": "Departure deadline reached; this run did not establish readiness in time."}[s["status"]])
        if not s["opted_in"]:
            result.append("The resident has not chosen to proceed.")
        if k["backup"] != "accepted":
            result.append("Preparation helper acceptance is unresolved.")
        if k["travel"] != "confirmed":
            result.append("Outbound and return commitments for this appointment are unresolved.")
        for item in ("bag", "documents"):
            if k[item]["status"] in ("last_known", "not_found"):
                result.append("The " + item + " location needs an explicit observation.")
        if not k["documents_staged"]:
            result.append("Documents have not been reported staged inside the bag.")
        if not k["helper_loaded"]:
            result.append("A helper has not reported loading the prepared bag.")
        if s["robot"]["status"] != "delivered":
            result.append("The bag has not been reported at the departure point.")
        if k["main_route"] == "blocked" and k["alternate_route"] != "usable":
            result.append("Main route is blocked; no observed usable alternate route is available.")
        return result

    def view(self, role):
        if role not in ("resident", "family", "coordinator"):
            raise ValueError("Choose a supported mission actor.")
        s = self.state
        return deepcopy({"active": s["active"], "status": s["status"], "title": TITLE,
                         "clock_minutes": s["clock_minutes"], "deadline_minutes": s["deadline_minutes"],
                         "clock_basis": "Demo minutes since preparation started. Each robot step takes 5 minutes. The pickup deadline stops unfinished movement.",
                         "pickup": s["appointment"]["pickup"], "appointment": s["appointment"],
                         "appointment_version": s["appointment_version"], "opted_in": s["opted_in"],
                         "known": s["known"], "robot": s["robot"], "permissions": s["permissions"],
                         "permission_fields": list(PERMISSIONS), "controls": self._controls(role),
                         "events": s["events"], "event_count": s["event_count"], "unresolved": self._unresolved(),
                         "helper_names": {"primary": PRIMARY, "backup": BACKUP}, "notice": NOTICE,
                         "actor_note": "Family actions represent Alex or Morgan, as named on each button."})

    def coordinator_view(self):
        return self.view("coordinator")

    def _start(self):
        previous = self.state
        s = _blank()
        if previous["active"] and self._current():
            appointment = deepcopy(previous["appointment"])
        else:
            appointment = {k: self.host.appointment[k] for k in s["appointment"]}
            moved = date.fromisoformat(appointment["date"]) + timedelta(days=1)
            appointment.update(date=moved.isoformat(), day=moved.strftime("%A"),
                               time="11:00" if appointment["time"] != "11:00" else "10:00",
                               pickup="10:15" if appointment["time"] != "11:00" else "09:15")
        self.host.appointment.update(appointment)
        self.host.week.legacy_changed("reschedule")
        s.update(active=True, status="preparing", appointment=appointment,
                 appointment_version=self.host.week.appointment_version)
        s["known"]["documents"] = _item(self.host.documents["location"])
        if s["known"]["documents"]["last_known"] == "R1":
            s["world"]["documents_zone"] = "Storage"
        self.host._actual_document_location = s["world"]["documents_zone"]
        self.host.documents["status"] = "last_known"
        self.host.week.legacy_changed("move_documents")
        self.state = s
        return "Outing rehearsal started for the changed appointment. Prior travel needs renewed confirmation; item locations remain last known."

    def apply(self, action, role, payload=None):
        if role not in ("resident", "family", "coordinator") or type(action) is not str:
            raise ValueError("Choose a supported mission actor and action.")
        payload = {} if payload is None else payload
        if type(payload) is not dict:
            raise ValueError("Mission action details must be an object.")
        if action == "mission_observe_alternate" and (set(payload) != {"usable"} or type(payload["usable"]) is not bool):
            raise ValueError("Supply an explicit usable or unavailable route observation.")
        s, k, p, r = self.state, self.state["known"], self.state["permissions"], self.state["robot"]
        editable = action in ("mission_permissions", "mission_set_deadline", "mission_advance_time")
        if editable:
            if role != "resident" or s["status"] != "preparing" or not self._current():
                raise ValueError("The resident controls these settings during an active rehearsal.")
            if action == "mission_permissions":
                if not payload or set(payload) - set(PERMISSIONS) or any(type(v) is not bool for v in payload.values()):
                    raise ValueError("Use supported boolean mission permissions.")
                if all(p[key] == value for key, value in payload.items()):
                    raise ValueError("Those permissions are already recorded.")
            else:
                field = "deadline_minutes" if action == "mission_set_deadline" else "minutes"
                maximum = 1440 if field == "deadline_minutes" else 120
                if set(payload) != {field} or type(payload[field]) is not int or not 1 <= payload[field] <= maximum:
                    raise ValueError("Use a whole number of minutes within the allowed range.")
                if action == "mission_set_deadline" and payload[field] == s[field]:
                    raise ValueError("That deadline is already recorded.")
                if action == "mission_advance_time" and s["clock_minutes"] + payload[field] > 1440:
                    raise ValueError("The demo clock is limited to one day.")
        elif not any(c["action"] == action and c.get("payload", {}) == payload
                     for c in self._controls(role)[role]):
            raise ValueError("This action is not available for this actor in the current mission.")

        if action in ("mission_start", "mission_reset"):
            text = self._start()
        elif action == "mission_opt_in":
            s["opted_in"] = True
            text = "Resident chose to prepare for the current appointment."
        elif action == "mission_permissions":
            p.update(payload)
            if not p["backup_helper"] and k["backup"] == "requested":
                k["backup"] = "cancelled"
            if r["status"] == "moving" and (not p["coordinator"] or not p["robot_transport"] or not p[r["route"] + "_route"]):
                r.update(status="stopped", report="Movement stopped because a required permission was revoked.")
            text = "Resident updated mission permissions; revoked permissions stop future actions."
        elif action == "mission_set_deadline":
            s["deadline_minutes"] = payload["deadline_minutes"]
            text = "Resident updated the departure deadline."
        elif action == "mission_advance_time":
            s["clock_minutes"] += payload["minutes"]
            text = "Demo clock advanced by " + str(payload["minutes"]) + " minutes."
        elif action == "mission_cancel":
            s["status"] = "cancelled"
            r.update(status="cancelled", report="Resident cancelled; no further delivery can execute.")
            for key in ("primary", "backup"):
                if k[key] == "requested":
                    k[key] = "cancelled"
            text = "Resident cancelled the rehearsal. Pending requests and robot delivery are stopped."
        elif action in ("mission_request_primary", "mission_request_backup"):
            helper = "primary" if action.endswith("primary") else "backup"
            k[helper] = "requested"
            text = (PRIMARY if helper == "primary" else BACKUP) + " was asked; acceptance is pending."
        elif action == "mission_primary_decline":
            k["primary"] = "declined"
            text = PRIMARY + " reports being unavailable for this appointment."
        elif action in ("mission_backup_accept", "mission_backup_decline"):
            accepted = action.endswith("accept")
            k["backup"] = "accepted" if accepted else "declined"
            text = BACKUP + (" accepted preparation help; travel still needs explicit confirmation." if accepted else " declined. No further request will be sent to this helper in this run.")
        elif action == "mission_confirm_travel":
            k["travel"] = "confirmed"
            self.host.transport.update(status="confirmed", person=BACKUP, for_date=s["appointment"]["date"])
            self.host.week.return_status = "confirmed"
            self.host.week.return_version = s["appointment_version"]
            self.host.week.return_person = BACKUP
            self.host.week.requested_legs = []
            self.host.week.backup_version = s["appointment_version"]
            self.host.week.ride_evidence = "Morgan explicitly confirmed outbound and return for the current mission appointment."
            text = self.host.week.ride_evidence
        elif action == "mission_request_search":
            k["search_requested"] = True
            text = "Resident was asked to check each item's last-known location before searching elsewhere."
        elif action.startswith("mission_check_"):
            item = action.removeprefix("mission_check_")
            k[item].update(status="not_found", location=None)
            text = "Resident checked the last-known " + item + " location and reports it was not found there; its current location is uncertain."
        elif action.startswith("mission_observe_") and action != "mission_observe_alternate":
            item = action.removeprefix("mission_observe_")
            location = s["world"][item + "_zone"]
            k[item].update(status="located", location=location)
            if item == "documents":
                self.host.documents.update(status="confirmed", location=location, recorded_at="Resident mission observation")
                self.host.week.papers_evidence = "Resident observed the document location; no staging is established."
            text = "Resident reports observing the " + item + " at " + location + ". Location is known; preparation is not established."
        elif action == "mission_request_loading":
            k["loading_requested"] = True
            self.host.week.papers_requested = True
            text = "Accepted backup was asked to stage the observed documents in the bag, then report loading it."
        elif action == "mission_stage_documents":
            if any(k[item]["location"] != s["world"][item + "_zone"] for item in ("bag", "documents")):
                raise ValueError("A current physical observation is needed before staging.")
            k["documents_staged"] = True
            k["documents"].update(status="staged", location="Inside bag at " + s["world"]["bag_zone"])
            s["world"]["documents_zone"] = s["world"]["bag_zone"]
            self._sync_documents("Helper reports documents placed inside the observed bag.")
            text = "Morgan reports staging the observed documents inside the bag. The robot is not loaded yet."
        elif action == "mission_load_robot":
            k["helper_loaded"] = True
            s["world"].update(bag_zone="Robot", documents_zone="Robot")
            k["bag"].update(status="loaded", location="Robot")
            k["documents"].update(status="loaded", location="Inside bag on robot")
            r.update(status="loaded", report="Morgan reports loading the prepared bag onto the demo robot.")
            self._sync_documents(r["report"])
            text = r["report"]
        elif action == "mission_observe_alternate":
            usable = payload["usable"]
            s["world"]["alternate_usable"] = usable
            k["alternate_route"] = "usable" if usable else "unavailable"
            text = "Resident reports that the alternative route is " + ("usable." if usable else "not usable.")
        elif action in ("mission_dispatch_main", "mission_dispatch_alternate"):
            route = "main" if action.endswith("main") else "alternate"
            r.update(status="moving", route=route, step=r["step"] if r["route"] == route else 0,
                     report="Loaded robot dispatched on the permitted " + route + " route; arrival is unreported.")
            text = r["report"]
        elif action == "mission_move_robot":
            s["clock_minutes"] = min(s["clock_minutes"] + 5, s["deadline_minutes"])
            self._update_status()
            if s["status"] == "overdue":
                text = r["report"]
            elif (r["route"] == "main" and r["step"] == 1 and s["world"]["main_blocked"]):
                k["main_route"] = "blocked"
                r.update(status="blocked", report="The demo robot found the main route blocked and stopped at Hall. The bag has not been delivered.")
                text = r["report"]
            else:
                if r["route"] == "alternate" and not s["world"]["alternate_usable"]:
                    raise ValueError("A current usable route observation is required.")
                r["step"] += 1
                r["position"] = ("Hall" if r["route"] == "main" else "R1") if r["step"] == 1 else "Departure"
                if r["position"] == "Departure":
                    r["status"] = "delivered"
                    s["world"].update(bag_zone="Departure", documents_zone="Departure")
                    k["bag"].update(status="delivered", location="Departure")
                    k["documents"].update(status="delivered", location="Inside bag at Departure")
                    self._sync_documents("The demo robot reports the prepared bag delivered at Departure.")
                r["report"] = "The demo robot reports " + ("prepared bag delivered at Departure." if r["status"] == "delivered" else "one route step completed; currently at " + r["position"] + ".")
                text = r["report"]
        else:  # mission_wait has no physical effect, but its explicit decision remains auditable.
            text = "Waiting. " + " ".join(self._unresolved()[:3])
        self._update_status()
        if self.state["status"] == "overdue" and "deadline" not in text.lower():
            text += " Departure deadline reached; this run remains unresolved."
        return self._record(role, action, text)

    def _sync_documents(self, evidence):
        self.host._actual_document_location = self.state["known"]["documents"]["location"]
        self.host.documents.update(status="confirmed", location=self.host._actual_document_location,
                                   recorded_at="Explicit mission report")
        self.host.week.papers_staged = True
        self.host.week.papers_evidence = evidence

    def _shared_evidence_matches(self):
        s, k, h = self.state, self.state["known"], self.host
        documents_known = k["documents"]["status"] not in ("last_known", "not_found")
        expected_location = k["documents"]["location"] if documents_known else k["documents"]["last_known"]
        expected_actual = k["documents"]["location"] if k["documents_staged"] else s["world"]["documents_zone"]
        if (h.documents["status"] != ("confirmed" if documents_known else "last_known")
                or h.documents["location"] != expected_location or h._actual_document_location != expected_actual
                or h.week.papers_staged != k["documents_staged"]):
            return False
        if k["travel"] == "confirmed":
            return (h.transport == {"status": "confirmed", "person": BACKUP, "for_date": s["appointment"]["date"]}
                    and h.week.return_status == "confirmed" and h.week.return_version == s["appointment_version"]
                    and h.week.return_person == BACKUP)
        return (h.transport == {"status": "needs_confirmation", "person": None, "for_date": None}
                and h.week.return_status == "needs_confirmation"
                and h.week.return_version is None and h.week.return_person is None)

    def shared_changed(self, action):
        s = self.state
        if s["active"] and s["status"] in ("preparing", "ready_to_leave") and (
                not self._current() or not self._shared_evidence_matches()):
            s["status"] = "invalidated"
            s["robot"].update(status="stopped", report="Shared appointment, travel, or item facts changed; pending movement stopped.")
            self._record("system", "mission_shared_changed", "Shared facts changed outside this mission; replay is required before further mission actions.")

    def dump(self):
        return deepcopy(self.state)

    @classmethod
    def restore(cls, host, data):
        """Validate a local snapshot without changing household facts or replaying actions."""
        mission = cls(host)
        mission._validate(data)
        mission.state = deepcopy(data)
        if data["active"] and data["status"] in ("preparing", "ready_to_leave", "overdue") and (not mission._current() or not mission._shared_evidence_matches()):
            raise ValueError("Saved mission does not match the current shared facts.")
        if data["status"] == "ready_to_leave" and not mission._ready():
            raise ValueError("Saved readiness lacks matching evidence.")
        return mission

    @staticmethod
    def _validate(data):
        error = "Saved mission state is malformed or inconsistent."
        def fail():
            raise ValueError(error)
        def shape(value, template):
            if type(template) is dict:
                if type(value) is not dict or set(value) != set(template):
                    fail()
                for key in template:
                    shape(value[key], template[key])
            elif template is None:
                if value is not None and (type(value) is not str or len(value) > 120):
                    fail()
            elif type(template) is list:
                if type(value) is not list or len(value) > 200:
                    fail()
            elif type(value) is not type(template) or (type(value) is str and len(value) > 600):
                fail()
        shape(data, _blank())
        s, k, r, w = data, data["known"], data["robot"], data["world"]
        if (s["schema"] != 1 or not 0 <= s["clock_minutes"] <= 1440 or not 1 <= s["deadline_minutes"] <= 1440
                or not 0 <= s["appointment_version"] <= 1_000_000 or not len(s["events"]) <= s["event_count"] <= 1_000_000
                or s["status"] not in ("idle", "preparing", "ready_to_leave", "cancelled", "overdue", "invalidated")
                or s["active"] != (s["status"] != "idle")):
            fail()
        try:
            day = date.fromisoformat(s["appointment"]["date"])
            if day.strftime("%A") != s["appointment"]["day"]:
                fail()
            for key in ("time", "pickup"):
                if datetime.strptime(s["appointment"][key], "%H:%M").strftime("%H:%M") != s["appointment"][key]:
                    fail()
        except (ValueError, TypeError):
            fail()
        for key in ("primary", "backup"):
            if k[key] not in ("not_requested", "requested", "accepted", "declined", "cancelled"):
                fail()
        if (k["primary"] == "accepted" or k["travel"] not in ("not_confirmed", "confirmed")
                or k["main_route"] not in ("unknown", "blocked") or k["alternate_route"] not in ("unknown", "usable", "unavailable")
                or r["capability"] != "carry_preloaded_bag" or r["status"] not in ("empty", "loaded", "moving", "blocked", "stopped", "delivered", "cancelled")
                or r["position"] not in ("Storage", "Hall", "R1", "Departure") or r["route"] not in (None, "main", "alternate")
                or not 0 <= r["step"] <= 2 or w["primary_available"] or not w["main_blocked"]
                or w["bag_zone"] not in ("Storage", "Robot", "Departure")
                or w["documents_zone"] not in ("Storage", "R1", "Robot", "Departure")):
            fail()
        for item in ("bag", "documents"):
            observed = k[item]
            if observed["status"] not in ("last_known", "not_found", "located", "staged", "loaded", "delivered"):
                fail()
            if ((observed["status"] in ("last_known", "not_found")) != (observed["location"] is None)
                    or (observed["status"] != "last_known" and not k["search_requested"])):
                fail()
            if observed["status"] in ("last_known", "not_found") and observed["last_known"] == w[item + "_zone"]:
                fail()
            if observed["status"] == "located" and observed["location"] != w[item + "_zone"]:
                fail()
        if (k["travel"] == "confirmed" and k["backup"] != "accepted"
                or k["documents_staged"] and (k["backup"] != "accepted" or not k["loading_requested"])
                or k["helper_loaded"] and not k["documents_staged"]
                or r["status"] in ("loaded", "moving", "blocked", "delivered") and not k["helper_loaded"]
                or r["status"] == "moving" and (not s["opted_in"] or not s["permissions"]["coordinator"]
                    or not s["permissions"]["robot_transport"] or r["route"] is None or not s["permissions"][r["route"] + "_route"])
                or r["route"] == "alternate" and (k["alternate_route"] != "usable" or not w["alternate_usable"])
                or r["status"] == "delivered" and (r["position"] != "Departure" or w["bag_zone"] != "Departure" or w["documents_zone"] != "Departure")
                or s["status"] == "preparing" and s["clock_minutes"] >= s["deadline_minutes"]
                or s["status"] == "overdue" and s["clock_minutes"] < s["deadline_minutes"]):
            fail()
        if k["documents_staged"]:
            if k["documents"]["status"] not in ("staged", "loaded", "delivered") or not k["search_requested"]:
                fail()
        elif k["documents"]["status"] in ("staged", "loaded", "delivered"):
            fail()
        if k["helper_loaded"]:
            if r["status"] == "empty":
                fail()
            delivered = k["bag"]["status"] == "delivered"
            expected = ("delivered", "Departure", "Inside bag at Departure", "Departure") if delivered else (
                "loaded", "Robot", "Inside bag on robot", "Robot")
            if (k["bag"]["status"] != expected[0] or k["documents"]["status"] != expected[0]
                    or k["bag"]["location"] != expected[1] or k["documents"]["location"] != expected[2]
                    or w["bag_zone"] != expected[3] or w["documents_zone"] != expected[3]):
                fail()
        elif k["documents_staged"]:
            if (k["bag"]["status"] != "located" or k["bag"]["location"] != w["bag_zone"]
                    or k["documents"]["status"] != "staged" or w["documents_zone"] != w["bag_zone"]
                    or k["documents"]["location"] != "Inside bag at " + w["bag_zone"]):
                fail()
        elif k["bag"]["status"] in ("staged", "loaded", "delivered"):
            fail()
        if (s["status"] in ("cancelled", "overdue", "invalidated") and r["status"] == "moving"
                or r["status"] == "blocked" and (k["main_route"] != "blocked" or r["position"] != "Hall")
                or r["status"] == "moving" and r["step"] == 2
                or r["status"] == "moving" and r["position"] != (
                    ("Storage" if r["route"] == "main" else "Hall") if r["step"] == 0 else (
                        "Hall" if r["route"] == "main" else "R1"))):
            fail()
        previous_time = 0
        for event in s["events"]:
            if (type(event) is not dict or set(event) != {"actor", "action", "result", "time"}
                    or event["actor"] not in ("resident", "family", "coordinator", "system")
                    or type(event["action"]) is not str or not event["action"].startswith("mission_") or len(event["action"]) > 80
                    or type(event["result"]) is not str or len(event["result"]) > 1200
                    or type(event["time"]) is not int or not previous_time <= event["time"] <= s["clock_minutes"]):
                fail()
            previous_time = event["time"]
