"""Fictional provider retrieval and administrative commitments, with explicit reports."""
from copy import deepcopy
from datetime import date, datetime, timedelta


ACTORS = {"alex": "Alex", "morgan": "Morgan"}
PERMISSIONS = ("retrieve_records", "visit_requests", "backup_requests", "refill_requests", "pickup_requests")
NOTICE = "Fictional hospital and pharmacy. Retrieval, requests and replies are simulated. No clinical advice, attendance or medication ingestion is established."


def _visit():
    return {"id": "visit-001", "source_id": "harbor-hospital-visit-001", "source_version": 1,
            "source_timestamp": "2026-09-15T08:00:00Z", "provenance": "fictional_provider_record",
            "appointment": {"date": "2026-09-17", "time": "11:00", "pickup": "10:15",
                "location": "Harbor Example Hospital, North reception", "purpose": "Private supplied follow-up purpose",
                "paperwork": ["Supplied appointment letter", "Requested identification"]}}


def _pharmacy():
    return {"id": "rx-001", "source_id": "harbor-pharmacy-rx-001", "source_version": 1,
            "source_timestamp": "2026-09-15T08:00:00Z", "provenance": "fictional_provider_record",
            "status": "authorization_pending", "pharmacy": "Harbor Example Pharmacy",
            "existing_prescription": "Private existing prescription record RX-001; no drug or dose decisions"}


def _text(value, maximum=500):
    return type(value) is str and 0 < len(value.strip()) <= maximum


def _source(record, prescription=False):
    template = _pharmacy() if prescription else _visit()
    if type(record) is not dict or set(record) != set(template):
        raise ValueError("Use the complete supported source record fields.")
    if (record["id"] != template["id"] or not _text(record["source_id"], 100)
            or type(record["source_version"]) is not int or not 1 <= record["source_version"] <= 100000
            or record["provenance"] not in ("fictional_provider_record", "supplied_record")):
        raise ValueError("Source identity, version or provenance is invalid.")
    try:
        stamp = datetime.fromisoformat(record["source_timestamp"].replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise ValueError("Provide a source timestamp including its timezone.") from None
    if prescription:
        if record["status"] not in ("authorization_pending", "ready", "unavailable") or not all(
                _text(record[key]) for key in ("pharmacy", "existing_prescription")):
            raise ValueError("Use a supplied pharmacy status for an existing prescription.")
    else:
        appointment = record["appointment"]
        if type(appointment) is not dict or set(appointment) != set(template["appointment"]):
            raise ValueError("Provide the complete appointment and supplied paperwork fields.")
        try:
            if date.fromisoformat(appointment["date"]).isoformat() != appointment["date"]:
                raise ValueError()
            for key in ("time", "pickup"):
                if datetime.strptime(appointment[key], "%H:%M").strftime("%H:%M") != appointment[key]:
                    raise ValueError()
        except (TypeError, ValueError):
            raise ValueError("Use a valid appointment date and 24-hour times.") from None
        if (not _text(appointment["location"]) or not _text(appointment["purpose"])
                or type(appointment["paperwork"]) is not list or not 1 <= len(appointment["paperwork"]) <= 12
                or any(not _text(item, 200) for item in appointment["paperwork"])):
            raise ValueError("Location, supplied purpose and paperwork must be bounded text.")
    return deepcopy(record)


class Hospital:
    def __init__(self, host):
        self.host = host
        self.state = {"schema": 1, "day": getattr(getattr(host, "coordination", None), "day", 1), "sequence": 0,
            "permissions": dict.fromkeys(PERMISSIONS, False),
            "provider_visit": _visit(), "provider_pharmacy": _pharmacy(),
            "retrieved_visit": None, "retrieved_pharmacy": None, "reconciled_version": None,
            "shared_version": None, "shared_appointment": None, "requests": {},
            "commitments": [], "refills": {}, "events": []}

    def _record(self, text):
        self.state["sequence"] += 1
        self.state["events"].append({"sequence": self.state["sequence"], "day": self.state["day"], "text": text})
        self.state["events"] = self.state["events"][-200:]
        return text

    def _retrieved(self, source):
        result = deepcopy(source)
        result["retrieved_at"] = {"day": self.state["day"], "sequence": self.state["sequence"] + 1,
                                  "basis": "simulation_clock"}
        return result

    def _known_helpers(self, request):
        helpers = dict(request["helpers"])
        for kind in ("driver", "companion", "return"):
            matches = [c for c in self.state["commitments"] if c["id"] in request["commitment_ids"]
                       and c["kind"] == kind and c["status"] in ("accepted", "requested")]
            accepted = [c for c in matches if c["status"] == "accepted"]
            if accepted or matches:
                helpers[kind] = (accepted or matches)[-1]["actor_id"]
        return helpers

    def _current_visit(self, on_date):
        appointment = self.state["shared_appointment"]
        return (appointment is not None and appointment["date"] >= on_date
                and self.state["shared_version"] == self.host.week.appointment_version
                and all(self.host.appointment.get(key, "") == appointment[key]
                        for key in ("date", "time", "pickup", "location")))

    def context(self):
        """Only last-retrieved facts, never the newer private provider source."""
        visit = deepcopy(self.state["retrieved_visit"])
        if visit:
            visit["appointment"].pop("purpose")
        pharmacy = deepcopy(self.state["retrieved_pharmacy"])
        if pharmacy:
            pharmacy.pop("existing_prescription")
        visits = [r for r in self.state["requests"].values() if r["intent"] == "hospital_coordination" and r["status"] != "cancelled"]
        return {"sources": [{"id": "visit-001", "label": "Harbor Example Hospital visit record"},
                            {"id": "rx-001", "label": "Existing prescription refill administration"}],
                "current_visit_helpers": self._known_helpers(visits[-1]) if visits else None,
                "retrieved_visit": visit, "retrieved_pharmacy": pharmacy,
                "permissions": deepcopy(self.state["permissions"]),
                "requests": deepcopy(list(self.state["requests"].values())),
                "notice": NOTICE}

    def _result(self, request, changed):
        status = {"planning": "running", "waiting": "waiting_helper", "waiting_permission": "waiting_permission", "stale": "paused",
                  "cancelled": "paused", "completed": "completed", "arranged": "waiting_helper"}[request["status"]]
        if request["status"] == "arranged" and request["phase"] == "done":
            status = "completed"
        return {"changed": changed, "status": status, "result": request["result"]}

    def start_request(self, request_id, proposal):
        if not _text(request_id, 100) or type(proposal) is not dict:
            raise ValueError("Use a bounded request identity and structured proposal.")
        if request_id in self.state["requests"]:
            return self._result(self.state["requests"][request_id], False)
        intent = proposal.get("intent")
        if intent not in ("hospital_coordination", "prescription_refill") or proposal.get("item") != (
                "visit-001" if intent == "hospital_coordination" else "rx-001"):
            raise ValueError("Select the existing visit or prescription record.")
        helper = proposal.get("helper")
        recipients = proposal.get("recipients")
        supplied = proposal.get("visit_helpers")
        if supplied is not None:
            if (intent != "hospital_coordination" or type(supplied) is not dict or set(supplied) != {"driver", "companion", "return"}
                    or any(type(value) is not str or value not in ("", "alex", "morgan") for value in supplied.values())):
                raise ValueError("Use separate named driver, companion and return assignments; blank roles use the default helper.")
            if helper == "" and all(supplied.values()):
                helper = supplied["driver"]
        if type(helper) is not str or helper not in ACTORS or type(recipients) is not list or len(recipients) > 2 or any(
                type(actor) is not str or actor not in ACTORS for actor in recipients) or len(set(recipients)) != len(recipients):
            raise ValueError("Choose the named helper and recipients.")
        helpers = {kind: (supplied or {}).get(kind) or helper for kind in ("driver", "companion", "return")} if intent == "hospital_coordination" else {}
        if len(self.state["requests"]) >= 40:
            raise ValueError("This local rehearsal has reached its 40-request limit.")
        if intent == "prescription_refill" and any(r["intent"] == intent and r["item"] == proposal["item"]
                and r["day"] == self.state["day"] and r["status"] != "cancelled" for r in self.state["requests"].values()):
            raise ValueError("This existing prescription already has a refill request for this day.")
        request = {"id": request_id, "intent": intent, "item": proposal["item"], "helper": helper, "helpers": helpers,
            "recipients": list(recipients), "day": self.state["day"], "status": "planning",
            "phase": "retrieve" if intent == "hospital_coordination" else "refill_request",
            "source_version": None, "commitment_ids": [], "result": "Administrative request prepared; no provider fact retrieved or helper accepted yet."}
        self.state["requests"][request_id] = request
        self._record("Prepared hospital or pharmacy administration request " + request_id + ".")
        return self._result(request, True)

    def _waiting(self, request, text, permission=False):
        status = "waiting_permission" if permission else "waiting"
        changed = request["status"] != status or request["result"] != text
        request.update(status=status, result=text)
        return self._result(request, changed)

    def _cancel_message(self, commitment):
        if commitment["message_id"]:
            self.host.coordination.cancel_domain_message(commitment["message_id"])

    def _invalidate(self, reason):
        for request in self.state["requests"].values():
            if request["intent"] == "hospital_coordination":
                request["helpers"] = self._known_helpers(request)
        affected = set()
        for commitment in self.state["commitments"]:
            if commitment["kind"] != "pickup" and commitment["status"] in ("requested", "accepted"):
                self._cancel_message(commitment)
                commitment.update(status="invalidated", evidence=reason)
                affected.add(commitment["id"])
        for request in self.state["requests"].values():
            if affected.intersection(request["commitment_ids"]) and request["status"] != "cancelled":
                request.update(status="stale", result=reason)

    def _reconcile(self, request):
        source = self.state["retrieved_visit"]
        if source is None or source["source_version"] != request["source_version"]:
            return self._waiting(request, "Retrieved source changed; start a fresh retrieval before reconciliation.")
        appointment = source["appointment"]
        old = self.state["shared_appointment"]
        logistics_changed = any(self.host.appointment.get(key, "") != appointment[key]
                                for key in ("date", "time", "pickup", "location"))
        paperwork_changed = old is None or old["paperwork"] != appointment["paperwork"]
        if logistics_changed:
            self._invalidate("A retrieved hospital time or location update invalidated this commitment.")
        else:
            affected = set()
            for commitment in self.state["commitments"]:
                if (commitment["kind"] != "pickup" and commitment["status"] in ("requested", "accepted")
                        and commitment["actor_id"] != request["helpers"][commitment["kind"]]):
                    self._clear_travel(commitment)
                    self._cancel_message(commitment)
                    commitment.update(status="invalidated", evidence="A new request names a different helper for only this responsibility.")
                    affected.add(commitment["id"])
            for previous in self.state["requests"].values():
                if affected.intersection(previous["commitment_ids"]) and previous["id"] != request["id"]:
                    previous.update(status="stale", result="A requested helper assignment changed; unchanged responsibilities remain recorded.")
        self.host.appointment.update({key: appointment[key] for key in ("date", "time", "pickup", "location")})
        self.host.appointment.update(day=date.fromisoformat(appointment["date"]).strftime("%A"), reason=appointment["purpose"])
        if logistics_changed:
            self.host.week.legacy_changed("reschedule")
        self.host.week.appointment_evidence = (f"Retrieved {source['source_id']} version {source['source_version']}, "
                                              f"source timestamp {source['source_timestamp']}; the hospital supplied this appointment.")
        if paperwork_changed:
            self.host.week.papers_needed = True
            self.host.week.papers_staged = False
            self.host.week.papers_evidence = "Hospital supplied a paperwork checklist; physical checking and packing remain unreported."
        self.state.update(reconciled_version=source["source_version"], shared_version=self.host.week.appointment_version,
                          shared_appointment=deepcopy(appointment))
        # Reuse still-current named agreements when a repeat retrieval only changes
        # paperwork or confirms the same notice; never request the same role twice.
        current_ids = [c["id"] for c in self.state["commitments"]
            if c["kind"] != "pickup" and c["status"] in ("requested", "accepted")
            and c["for_version"] == self.state["shared_version"] and self._current_visit(self.host.coordination.state["date"])]
        request["commitment_ids"] = list(dict.fromkeys(request["commitment_ids"] + current_ids))
        request.update(phase="arrange", status="planning", result="Retrieved hospital record reconciled; driver, companion and return travel still need separate acceptance.")
        self._record("Reconciled retrieved hospital source version " + str(source["source_version"]) + ".")
        return self._result(request, True)

    def _new_commitment(self, request, kind, actor, attempt):
        if len(self.state["commitments"]) >= 120:
            raise ValueError("This local rehearsal has reached its commitment limit.")
        identity = "hospital-" + str(len(self.state["commitments"]) + 1)
        version = self.state["shared_version"] if kind != "pickup" else request["source_version"]
        if kind == "pickup":
            details = ("Continue delivery of the previously collected pharmacy package; prior collection evidence is retained."
                       if self.state["refills"][request["id"]]["status"] == "collected" else
                       "Collect a ready pharmacy package for the resident. Collection and delivery need separate reports.")
        else:
            appointment = self.state["shared_appointment"]
            duty = {"driver": "outbound driving", "companion": "in-hospital accompaniment", "return": "return travel"}[kind]
            timing = (f"pickup {appointment['pickup']} for the {appointment['time']} visit" if kind == "driver" else
                      "after the visit; the provider has not supplied the return pickup time" if kind == "return" else
                      f"the visit at {appointment['time']}")
            details = f"Request for {duty}: {appointment['date']}, {timing}, {appointment['location']}. Accept only this responsibility."
        message_id = self.host.coordination.post_domain_message(request["id"], actor, identity, details,
            {"domain": "hospital", "commitment_id": identity, "kind": kind, "version": version})
        commitment = {"id": identity, "request_id": request["id"], "kind": kind, "actor_id": actor,
            "status": "requested", "day": self.state["day"], "for_version": version,
            "attempt": attempt, "message_id": message_id, "details": details,
            "evidence": "Addressed request is available to the named recipient; acceptance is pending."}
        self.state["commitments"].append(commitment)
        request["commitment_ids"].append(identity)
        request.update(status="planning", result=f"{ACTORS[actor]} has an addressed {kind} request; own acceptance remains pending.")
        self._record("Requested named " + kind + " commitment for " + request["id"] + ".")
        return self._result(request, True)

    def _arrange(self, request, kinds):
        if kinds != ("pickup",) and not self._current_visit(self.host.coordination.state["date"]):
            return self._waiting(request, "The hospital visit is past or changed; retrieve and reconcile a current visit first.")
        if not self.state["permissions"]["pickup_requests" if kinds == ("pickup",) else "visit_requests"]:
            return self._waiting(request, "Standing permission for these named requests is missing.", True)
        expected_version = request["source_version"] if kinds == ("pickup",) else self.state["shared_version"]
        on_date = self.host.coordination.state["date"] if kinds == ("pickup",) else self.state["shared_appointment"]["date"]
        responsibilities = []
        for kind in kinds:
            relevant = [c for c in self.state["commitments"] if c["id"] in request["commitment_ids"] and c["kind"] == kind
                        and c["for_version"] == expected_version and (kind != "pickup" or c["day"] == self.state["day"])
                        and c["status"] not in ("cancelled", "invalidated")]
            if kind != "pickup":
                label = {"driver": "Outbound driver", "companion": "Hospital companion", "return": "Return driver"}[kind]
                responsibilities.append(label + ": " + ", ".join(
                    ACTORS[c["actor_id"]] + " " + ("pending" if c["status"] == "requested" else c["status"])
                    for c in relevant) + ".")
            if any(c["status"] == "accepted" for c in relevant):
                continue
            if any(c["status"] == "requested" for c in relevant):
                continue  # Issue other independent responsibilities before waiting.
            primary = request["helper"] if kind == "pickup" else request["helpers"][kind]
            if not relevant and self.host.coordination.availability_for(primary, on_date) is not False:
                return self._new_commitment(request, kind, primary, len(request["commitment_ids"]))
            tried = {c["actor_id"] for c in relevant} | {primary}
            backup = next((actor for actor in ACTORS if actor not in tried
                           and self.host.coordination.availability_for(actor, on_date) is not False), None)
            if backup and self.state["permissions"]["backup_requests"]:
                return self._new_commitment(request, kind, backup, len(request["commitment_ids"]))
            if kind != "pickup":
                responsibilities[-1] += (" Backup permission required; unresolved." if backup
                                         else " No eligible untried helper; unresolved.")
        accepted = {c["kind"] for c in self.state["commitments"] if c["id"] in request["commitment_ids"]
                    and c["status"] == "accepted" and (c["kind"] != "pickup" or c["day"] == self.state["day"])
                    and c["for_version"] == expected_version}
        visit_summary = ("Fictional visit. " + " ".join(responsibilities)
                         + " Return pickup time is unknown. Attendance and physical paperwork preparation remain unreported.")
        if all(kind in accepted for kind in kinds):
            collected = kinds == ("pickup",) and self.state["refills"][request["id"]]["status"] == "collected"
            request.update(status="arranged", phase="reports" if kinds == ("pickup",) else "done",
                result="Named helper accepted today's delivery responsibility; prior collection evidence is preserved." if collected else
                       "Pickup helper accepted; collection and delivery remain unreported." if kinds == ("pickup",)
                       else visit_summary)
            self._record("Named administrative arrangements accepted for " + request["id"] + ".")
            return self._result(request, True)
        return self._waiting(request, "One or more separate responsibilities remain unaccepted. A declined helper is not automatically responsible; backup requests require permission."
                             if kinds == ("pickup",) else visit_summary + " Coordination is pending.")

    def advance_request(self, request_id):
        if not _text(request_id, 100):
            raise ValueError("Use a bounded hospital request identity.")
        request = self.state["requests"].get(request_id)
        if request is None:
            raise ValueError("Unknown hospital administration request.")
        if request["status"] in ("cancelled", "completed", "stale") or request["phase"] == "done":
            return self._result(request, False)
        if request["day"] != self.state["day"] and not (request["intent"] == "hospital_coordination"
                and self._current_visit(self.host.coordination.state["date"])):
            return self._waiting(request, "This request belongs to an earlier day; current helper commitments are required.")
        permissions = self.state["permissions"]
        if request["intent"] == "prescription_refill" and request["phase"] in ("pickup", "reports"):
            refill = self.state["refills"][request_id]
            if (refill["status"] == "ready" and permissions["retrieve_records"]
                    and refill["source_version"] != self.state["provider_pharmacy"]["source_version"]):
                for commitment in self.state["commitments"]:
                    if commitment["request_id"] == request_id and commitment["kind"] == "pickup" and commitment["status"] in ("requested", "accepted"):
                        self._cancel_message(commitment)
                        commitment.update(status="invalidated", evidence="A fresh authorized pharmacy retrieval is pending; old pickup readiness must be reconciled.")
                request.update(phase="pharmacy_response", status="planning", result="Checking the supplied pharmacy source again before unreported collection.")
                return self._result(request, True)
        if request["phase"] == "retrieve":
            if not permissions["retrieve_records"]:
                return self._waiting(request, "Permission to retrieve the hospital record is missing.", True)
            self.state["retrieved_visit"] = self._retrieved(self.state["provider_visit"])
            request.update(source_version=self.state["retrieved_visit"]["source_version"], phase="reconcile", status="planning",
                           result="Hospital record retrieved with its source version and retrieval stamp; household reconciliation is next.")
            self._record("Retrieved hospital record version " + str(request["source_version"]) + ".")
            return self._result(request, True)
        if request["phase"] == "reconcile":
            return self._reconcile(request)
        if request["phase"] == "arrange":
            return self._arrange(request, ("driver", "companion", "return"))
        if request["phase"] == "refill_request":
            if not permissions["refill_requests"]:
                return self._waiting(request, "Permission for existing-prescription refill administration is missing.", True)
            self.state["refills"][request_id] = {"request_id": request_id, "prescription_id": "rx-001", "status": "requested",
                "provider_status": "not_retrieved", "source_version": None, "collected_by": None, "delivered_by": None,
                "evidence": "Harbor Example Pharmacy received an administrative refill request; authorization and readiness are not established."}
            request.update(phase="pharmacy_response", status="waiting", result="Refill administration requested; retrieve the supplied pharmacy response next.")
            self._record("Submitted existing-prescription administrative request " + request_id + ".")
            return self._result(request, True)
        if request["phase"] == "pharmacy_response":
            if not permissions["retrieve_records"]:
                return self._waiting(request, "Permission to retrieve the pharmacy response is missing.", True)
            refill = self.state["refills"][request_id]
            source = self.state["provider_pharmacy"]
            if refill["source_version"] == source["source_version"]:
                return self._waiting(request, "Pharmacy authorization or availability is still pending; no new supplied response has been retrieved.")
            self.state["retrieved_pharmacy"] = self._retrieved(source)
            refill.update(status=source["status"], provider_status=source["status"], source_version=source["source_version"],
                          evidence=f"Retrieved pharmacy source version {source['source_version']}: {source['status']}; no collection or ingestion established.")
            request.update(source_version=source["source_version"], phase="pickup" if source["status"] == "ready" else "pharmacy_response",
                           status="planning" if source["status"] == "ready" else "waiting", result=refill["evidence"])
            self._record("Retrieved supplied pharmacy response for " + request_id + ".")
            return self._result(request, True)
        if request["phase"] == "pickup":
            return self._arrange(request, ("pickup",))
        return self._result(request, False)  # Accepted pickup waits for explicit physical reports.

    def recipient_reply(self, commitment_id, actor_id, status):
        commitment = next((c for c in self.state["commitments"] if c["id"] == commitment_id), None)
        if commitment is None or actor_id != commitment["actor_id"] or status not in ("accepted", "declined"):
            raise ValueError("Only the named recipient may accept or decline this responsibility.")
        request = self._active_request(commitment)
        allowed = commitment["status"] == "requested" or (commitment["status"] == "accepted" and status == "declined")
        if (not allowed or request["status"] in ("cancelled", "stale")
                or commitment["kind"] == "pickup" and commitment["day"] != self.state["day"]):
            raise ValueError("This request is stale, cancelled or already answered.")
        if commitment["kind"] != "pickup" and (commitment["for_version"] != self.host.week.appointment_version
                or not self._current_visit(self.host.coordination.state["date"])):
            raise ValueError("The appointment changed; refresh before accepting responsibility.")
        permission = "pickup_requests" if commitment["kind"] == "pickup" else "visit_requests"
        if status == "accepted" and not self.state["permissions"][permission]:
            raise ValueError("Permission for this pending responsibility was revoked.")
        if status == "accepted":
            on_date = self.host.appointment["date"] if commitment["kind"] != "pickup" else self.host.coordination.state["date"]
            availability = self.host.coordination.availability_for(actor_id, on_date)
            if availability is False or commitment["kind"] == "pickup" and availability is not True:
                raise ValueError("The named helper must be available for this responsibility's date.")
        if commitment["kind"] == "pickup" and self.state["refills"][request["id"]]["status"] in ("collected", "delivered") and status == "declined":
            raise ValueError("Physical collection is already recorded; preserve that responsibility and report.")
        commitment.update(status=status, evidence=ACTORS[actor_id] + " explicitly " + status + " only the " + commitment["kind"] + " responsibility.")
        if commitment["kind"] in ("driver", "return") and status == "accepted":
            if commitment["kind"] == "driver":
                self.host.transport.update(status="confirmed", person=ACTORS[actor_id], for_date=self.host.appointment["date"])
                self.host.week.backup_version = commitment["for_version"]
            else:
                self.host.week.return_status = "confirmed"
                self.host.week.return_version = commitment["for_version"]
                self.host.week.return_person = ACTORS[actor_id]
            self.host.week.ride_evidence = "Hospital visit travel roles are accepted separately; see named commitment evidence."
        if status == "declined":
            self._clear_travel(commitment)
            for linked in self.state["requests"].values():
                if commitment_id in linked["commitment_ids"] and linked["status"] not in ("cancelled", "stale"):
                    linked.update(status="waiting", phase="pickup" if commitment["kind"] == "pickup" else "arrange",
                                  result="A named helper declined or withdrew this responsibility; an authorized alternative is pending.")
                    if linked["id"] != request["id"]:
                        self.host.coordination.resume_domain_request(linked["id"])
        self._record(commitment["evidence"])
        return self._result(request, True)

    def _active_request(self, commitment):
        request = self.state["requests"][commitment["request_id"]]
        if request["status"] == "stale":
            return next((r for r in reversed(list(self.state["requests"].values()))
                         if commitment["id"] in r["commitment_ids"] and r["status"] not in ("cancelled", "stale")), request)
        return request

    def _clear_travel(self, commitment):
        if commitment["for_version"] != self.host.week.appointment_version:
            return
        if commitment["kind"] == "driver" and self.host.transport.get("person") == ACTORS[commitment["actor_id"]]:
            self.host.transport.update(status="needs_confirmation", person=None, for_date=None)
            self.host.week.backup_version = None
        if commitment["kind"] == "return" and self.host.week.return_person == ACTORS[commitment["actor_id"]]:
            self.host.week.return_status = "needs_confirmation"
            self.host.week.return_version = None
            self.host.week.return_person = None

    def cancel_request(self, request_id):
        if not _text(request_id, 100):
            raise ValueError("Use a bounded hospital request identity.")
        request = self.state["requests"].get(request_id)
        if request is None:
            raise ValueError("Unknown hospital request.")
        if request["status"] == "cancelled":
            return self._result(request, False)
        for commitment in self.state["commitments"]:
            if commitment["request_id"] == request_id and commitment["status"] in ("requested", "accepted"):
                self._clear_travel(commitment)
                self._cancel_message(commitment)
                commitment.update(status="cancelled", evidence="Coordination cancelled; prior physical/provider evidence remains recorded.")
                for linked in self.state["requests"].values():
                    if linked["id"] != request_id and commitment["id"] in linked["commitment_ids"] and linked["status"] != "cancelled":
                        linked.update(status="stale", result="A reused named commitment was cancelled; fresh coordination is required.")
        request.update(status="cancelled", result="Future coordination stopped. Prior provider acknowledgments or physical reports are preserved; cancellation does not reverse them.")
        self._record("Cancelled future administration for " + request_id + ".")
        return self._result(request, True)

    def shared_changed(self):
        appointment = self.state["shared_appointment"]
        if appointment is not None and self.state["shared_version"] is not None and (self.state["shared_version"] != self.host.week.appointment_version or any(
                self.host.appointment.get(key, "") != appointment[key] for key in ("date", "time", "pickup", "location"))):
            self._invalidate("Shared appointment changed outside the retrieved hospital plan.")
            for request in self.state["requests"].values():
                if request["intent"] == "hospital_coordination" and request["status"] != "cancelled":
                    request.update(status="stale", result="Shared appointment changed; retrieve and reconcile before requesting current commitments.")
            self.state["shared_version"] = None
            return True
        return False

    def next_day(self, day):
        if type(day) is not int or day <= self.state["day"]:
            raise ValueError("Advance to a later day.")
        on_date = (date.fromisoformat(self.host.coordination.state["date"])
                   + timedelta(days=day - self.host.coordination.day)).isoformat()
        preserved = {identity for request in self.state["requests"].values()
                     if self._current_visit(on_date) and request["intent"] == "hospital_coordination"
                     and request["status"] not in ("cancelled", "stale") and request["phase"] in ("arrange", "done")
                     for identity in request["commitment_ids"]}
        preserved &= {c["id"] for c in self.state["commitments"] if c["kind"] != "pickup"
                      and c["for_version"] == self.state["shared_version"] and c["status"] in ("requested", "accepted")}
        self.state["day"] = day
        for commitment in self.state["commitments"]:
            if commitment["status"] in ("requested", "accepted") and commitment["id"] not in preserved:
                self._clear_travel(commitment)
                self._cancel_message(commitment)
                commitment.update(status="invalidated", evidence="The next day requires fresh named helper availability.")
        for request in self.state["requests"].values():
            if request["status"] not in ("completed", "cancelled") and not preserved.intersection(request["commitment_ids"]):
                request.update(status="stale", result="Earlier-day requests are preserved; fresh day-specific coordination is required.")
        return self._record("Advanced hospital administration to day " + str(day) + ".")

    def view(self, role, actor_id=None):
        if role not in ("resident", "family", "coordinator") or (role == "family" and (actor_id or "alex") not in ACTORS):
            raise ValueError("Choose an available household perspective.")
        public = self.context()
        if role == "resident":
            public["retrieved_visit"] = deepcopy(self.state["retrieved_visit"])
            public["retrieved_pharmacy"] = deepcopy(self.state["retrieved_pharmacy"])
        commitments = deepcopy(self.state["commitments"])
        refills = deepcopy(list(self.state["refills"].values()))
        controls = []
        if role == "resident":
            controls = [{"action": "hospital_publish_visit", "label": "Harbor Example Hospital: publish a time/location update", "payload": {"fixture": "time_location_change"}},
                        {"action": "hospital_publish_pharmacy", "label": "Harbor Example Pharmacy: authorization pending", "payload": {"status": "authorization_pending"}},
                        {"action": "hospital_publish_pharmacy", "label": "Harbor Example Pharmacy: supplied ready response", "payload": {"status": "ready"}},
                        {"action": "hospital_publish_pharmacy", "label": "Harbor Example Pharmacy: item unavailable", "payload": {"status": "unavailable"}}]
            controls += [{"action": "hospital_resume", "label": "Resume this existing administrative request with current facts",
                          "payload": {"request_id": r["id"]}} for r in self.state["requests"].values() if r["status"] == "stale"]
        if role == "family":
            actor_id = actor_id or "alex"
            commitments = [c for c in commitments if c["actor_id"] == actor_id]
            public = {"notice": NOTICE}
            refills = []
            for commitment in commitments:
                request = self._active_request(commitment)
                if commitment["status"] == "accepted" and request["status"] not in ("cancelled", "stale") and (
                        commitment["kind"] != "pickup" or self.state["refills"][request["id"]]["status"] == "ready"):
                    controls.append({"action": "hospital_withdraw", "label": "Withdraw my " + commitment["kind"] + " commitment",
                                     "payload": {"commitment_id": commitment["id"]}})
                if commitment["kind"] == "pickup" and commitment["status"] == "accepted" and request["status"] not in ("cancelled", "stale"):
                    refill = self.state["refills"][request["id"]]
                    if refill["status"] in ("ready", "collected"):
                        controls.append({"action": "hospital_collect" if refill["status"] == "ready" else "hospital_deliver",
                            "label": "Report pharmacy package collected" if refill["status"] == "ready" else "Report pharmacy package delivered to the resident",
                            "payload": {"request_id": request["id"]}})
        public.update(permission_fields=list(PERMISSIONS), visit_commitments=[c for c in commitments if c["kind"] != "pickup"],
                      pickup_commitments=[c for c in commitments if c["kind"] == "pickup"], refills=refills, controls=controls)
        return public

    def apply(self, action, role, payload=None, actor_id=None):
        payload = {} if payload is None else payload
        if type(payload) is not dict or role not in ("resident", "family"):
            raise ValueError("Use a supported household action and structured details.")
        if action == "hospital_resume":
            if role != "resident" or set(payload) != {"request_id"} or not _text(payload["request_id"], 100):
                raise ValueError("The resident resumes an existing administrative request.")
            request = self.state["requests"].get(payload["request_id"])
            if request is None or request["status"] != "stale":
                raise ValueError("Only a stale existing request can be resumed with current facts.")
            phase = "retrieve"
            if request["intent"] == "prescription_refill":
                refill = self.state["refills"].get(request["id"])
                phase = "refill_request" if refill is None else "pickup" if refill["status"] in ("ready", "collected") else "pharmacy_response"
                if refill and refill["status"] == "collected":
                    request["helper"] = refill["collected_by"]
            request.update(day=self.state["day"], phase=phase, status="planning",
                           result="Existing administrative request resumed; previous provider/physical evidence is preserved and current helper acceptance is required.")
            self.host.coordination.resume_domain_request(request["id"])
            return self._record(request["result"])
        if action in ("hospital_permissions", "hospital_publish_visit", "hospital_supply_notice", "hospital_publish_pharmacy", "hospital_supply_pharmacy"):
            if role != "resident":
                raise ValueError("Only the resident controls permissions and supplied scenario records.")
            if action == "hospital_permissions":
                if not payload or set(payload) - set(PERMISSIONS) or any(type(v) is not bool for v in payload.values()):
                    raise ValueError("Use supported boolean hospital permissions.")
                if all(self.state["permissions"][key] == value for key, value in payload.items()):
                    raise ValueError("Those permissions are already recorded.")
                self.state["permissions"].update(payload)
                for commitment in self.state["commitments"]:
                    permission = "pickup_requests" if commitment["kind"] == "pickup" else "visit_requests"
                    if commitment["status"] == "requested" and not self.state["permissions"][permission]:
                        self._cancel_message(commitment)
                        commitment.update(status="cancelled", evidence="Standing permission revoked before acceptance.")
                return self._record("Updated hospital and pharmacy permissions.")
            pharmacy = action in ("hospital_publish_pharmacy", "hospital_supply_pharmacy")
            key = "provider_pharmacy" if pharmacy else "provider_visit"
            if action in ("hospital_supply_notice", "hospital_supply_pharmacy"):
                if set(payload) != {"record"}:
                    raise ValueError("Provide one structured supplied record.")
                record = _source(payload["record"], pharmacy)
            else:
                record = deepcopy(self.state[key])
                record["source_version"] += 1
                record["source_timestamp"] = "2026-09-15T09:00:00Z"
                if pharmacy:
                    if set(payload) != {"status"} or payload["status"] not in ("authorization_pending", "ready", "unavailable"):
                        raise ValueError("Choose a supplied pharmacy response.")
                    record["status"] = payload["status"]
                else:
                    if payload != {"fixture": "time_location_change"}:
                        raise ValueError("Choose the authored hospital notice fixture.")
                    record["appointment"].update(date="2026-09-18", time="14:00", pickup="13:15",
                        location="Harbor Example Hospital, South reception, Level 2",
                        paperwork=["Updated appointment letter", "Requested identification", "Supplied visit form"])
            if record["source_version"] <= self.state[key]["source_version"]:
                raise ValueError("A supplied source update must have a newer version.")
            self.state[key] = record
            return self._record("Provider source updated. Household facts remain unchanged until authorized retrieval.")
        if action == "hospital_withdraw" and role == "family" and actor_id in ACTORS and set(payload) == {"commitment_id"}:
            self.recipient_reply(payload["commitment_id"], actor_id, "declined")
            commitment = next(c for c in self.state["commitments"] if c["id"] == payload["commitment_id"])
            self._cancel_message(commitment)
            self.host.coordination.resume_domain_request(self._active_request(commitment)["id"])
            return "Named helper withdrew only this responsibility; alternatives remain subject to permission and acceptance."
        if role != "family" or type(actor_id) is not str or actor_id not in ACTORS or set(payload) != {"request_id"} or not _text(payload["request_id"], 100):
            raise ValueError("Only the named accepted pickup helper can report this physical action.")
        request = self.state["requests"].get(payload["request_id"])
        if request is None or request["status"] in ("cancelled", "stale") or request["day"] != self.state["day"]:
            raise ValueError("This pharmacy request is not current.")
        commitment = next((c for c in self.state["commitments"] if c["request_id"] == request["id"] and c["kind"] == "pickup"
                           and c["actor_id"] == actor_id and c["status"] == "accepted" and c["day"] == self.state["day"]), None)
        refill = self.state["refills"].get(request["id"])
        expected = "ready" if action == "hospital_collect" else "collected" if action == "hospital_deliver" else None
        if commitment is None or refill is None or expected is None or refill["status"] != expected:
            raise ValueError("Provider readiness, pickup acceptance and prior physical reports are required in order.")
        if action == "hospital_collect" and self.state["provider_pharmacy"]["status"] != "ready":
            raise ValueError("The pharmacy no longer supplies a ready response; retrieve its current record before collection.")
        refill.update(status="collected" if action == "hospital_collect" else "delivered",
                      evidence=ACTORS[actor_id] + (" reports collecting the ready pharmacy package." if action == "hospital_collect"
                                                  else " reports delivery to the resident; ingestion is not established."))
        refill["collected_by" if action == "hospital_collect" else "delivered_by"] = actor_id
        if action == "hospital_deliver":
            request.update(status="completed", phase="done", result=refill["evidence"])
            self.host.coordination.complete_domain_message(commitment["message_id"])
        self.host.coordination.resume_domain_request(request["id"])
        return self._record(refill["evidence"])

    def dump(self):
        return deepcopy(self.state)

    @classmethod
    def restore(cls, host, data):
        """Validate a snapshot without writing shared facts, inboxes or provider effects."""
        try:
            return cls._restore_checked(host, data)
        except (KeyError, TypeError, AttributeError):
            raise ValueError("Malformed hospital snapshot.") from None

    @classmethod
    def _restore_checked(cls, host, data):
        instance = cls(host)
        data = deepcopy(data)
        # Older saved requests had one default helper. Expanding that existing
        # intention to three roles changes no acceptance, inbox or provider effect.
        if type(data) is dict and type(data.get("requests")) is dict:
            for request in data["requests"].values():
                if type(request) is dict and "helpers" not in request:
                    request["helpers"] = dict.fromkeys(("driver", "companion", "return"), request.get("helper")) if request.get("intent") == "hospital_coordination" else {}
        if type(data) is not dict or set(data) != set(instance.state) or type(data.get("schema")) is not int or data["schema"] != 1:
            raise ValueError("Malformed hospital snapshot.")
        for key in ("day", "sequence"):
            if type(data[key]) is not int or not 0 <= data[key] <= 100000:
                raise ValueError("Malformed hospital snapshot clock.")
        if type(data["permissions"]) is not dict or set(data["permissions"]) != set(PERMISSIONS) or any(type(v) is not bool for v in data["permissions"].values()):
            raise ValueError("Malformed hospital permissions.")
        _source(data["provider_visit"])
        _source(data["provider_pharmacy"], True)
        for key in ("reconciled_version", "shared_version"):
            if data[key] is not None and (type(data[key]) is not int or not 1 <= data[key] <= 100000):
                raise ValueError("Malformed hospital source linkage.")
        if data["shared_appointment"] is not None:
            _source(dict(_visit(), appointment=data["shared_appointment"]))
        elif data["shared_version"] is not None or data["reconciled_version"] is not None:
            raise ValueError("A reconciled version needs the shared appointment facts.")
        for name, pharmacy in (("retrieved_visit", False), ("retrieved_pharmacy", True)):
            record = deepcopy(data[name])
            if record is not None:
                if type(record) is not dict or "retrieved_at" not in record:
                    raise ValueError("Retrieved records require retrieval evidence.")
                stamp = record.pop("retrieved_at")
                if (type(stamp) is not dict or set(stamp) != {"day", "sequence", "basis"} or stamp["basis"] != "simulation_clock"
                        or type(stamp["day"]) is not int or not 0 <= stamp["day"] <= data["day"]
                        or type(stamp["sequence"]) is not int or not 0 <= stamp["sequence"] <= data["sequence"]):
                    raise ValueError("Malformed retrieval evidence.")
                _source(record, pharmacy)
                provider = data["provider_pharmacy" if pharmacy else "provider_visit"]
                if record["source_version"] > provider["source_version"]:
                    raise ValueError("Retrieved version cannot be ahead of its supplied provider source.")
        if (type(data["requests"]) is not dict or len(data["requests"]) > 40
                or type(data["commitments"]) is not list or len(data["commitments"]) > 120
                or type(data["refills"]) is not dict or type(data["events"]) is not list or len(data["events"]) > 200):
            raise ValueError("Malformed hospital history.")
        for request_id, request in data["requests"].items():
            if (type(request) is not dict or set(request) != {"id", "intent", "item", "helper", "helpers", "recipients", "day", "status", "phase", "source_version", "commitment_ids", "result"}
                    or request.get("id") != request_id or not _text(request_id, 100)
                    or request.get("intent") not in ("hospital_coordination", "prescription_refill") or request.get("helper") not in ACTORS
                    or request.get("status") not in ("planning", "waiting", "waiting_permission", "arranged", "cancelled", "completed", "stale")
                    or request.get("phase") not in ("retrieve", "reconcile", "arrange", "refill_request", "pharmacy_response", "pickup", "reports", "done")
                    or type(request.get("commitment_ids")) is not list or any(not _text(v, 160) for v in request["commitment_ids"])
                    or len(set(request["commitment_ids"])) != len(request["commitment_ids"])
                    or type(request.get("day")) is not int or not 0 <= request["day"] <= data["day"]
                    or not _text(request.get("result"), 1500) or type(request.get("recipients")) is not list
                    or any(v not in ACTORS for v in request["recipients"]) or len(set(request["recipients"])) != len(request["recipients"])
                    or request.get("item") != ("visit-001" if request.get("intent") == "hospital_coordination" else "rx-001")
                    or request["source_version"] is not None and (type(request["source_version"]) is not int or request["source_version"] < 1)):
                raise ValueError("Malformed hospital request.")
            if (type(request["helpers"]) is not dict or set(request["helpers"]) != ({"driver", "companion", "return"} if request["intent"] == "hospital_coordination" else set())
                    or any(type(value) is not str or value not in ACTORS for value in request["helpers"].values())):
                raise ValueError("Malformed per-role hospital helper assignments.")
        ids = set()
        for commitment in data["commitments"]:
            if (type(commitment) is not dict or set(commitment) != {"id", "request_id", "kind", "actor_id", "status", "day", "for_version", "attempt", "message_id", "details", "evidence"}
                    or not _text(commitment.get("id"), 160) or commitment.get("id") in ids
                    or commitment.get("request_id") not in data["requests"] or commitment.get("actor_id") not in ACTORS
                    or commitment.get("kind") not in ("driver", "companion", "return", "pickup")
                    or commitment.get("status") not in ("requested", "accepted", "declined", "cancelled", "invalidated")
                    or type(commitment.get("for_version")) is not int or commitment["for_version"] < 1
                    or type(commitment.get("day")) is not int or not 0 <= commitment["day"] <= data["day"]
                    or type(commitment.get("attempt")) is not int or not 0 <= commitment["attempt"] <= 120
                    or not _text(commitment.get("message_id"), 300) or not _text(commitment.get("details"), 600)
                    or not _text(commitment.get("evidence"), 1500)
                    or commitment["id"] not in data["requests"][commitment["request_id"]]["commitment_ids"]):
                raise ValueError("Malformed named hospital commitment.")
            ids.add(commitment["id"])
            if commitment["status"] in ("requested", "accepted") and commitment["kind"] != "pickup" and (
                    commitment["for_version"] != data["shared_version"] or data["shared_version"] != host.week.appointment_version
                    or any(host.appointment.get(key, "") != data["shared_appointment"][key] for key in ("date", "time", "pickup", "location"))):
                raise ValueError("An active commitment needs the current shared appointment.")
        for request in data["requests"].values():
            if set(request["commitment_ids"]) - ids:
                raise ValueError("A hospital request references a missing commitment.")
            if request["status"] == "arranged" and request["intent"] == "hospital_coordination":
                accepted = {c["kind"] for c in data["commitments"] if c["id"] in request["commitment_ids"] and c["status"] == "accepted"}
                if not {"driver", "companion", "return"} <= accepted:
                    raise ValueError("Arranged visits require distinct accepted responsibilities.")
        for request_id, refill in data["refills"].items():
            if (type(refill) is not dict or set(refill) != {"request_id", "prescription_id", "status", "provider_status", "source_version", "collected_by", "delivered_by", "evidence"}
                    or request_id not in data["requests"] or refill.get("request_id") != request_id
                    or refill.get("prescription_id") != "rx-001" or refill.get("status") not in
                    ("requested", "authorization_pending", "unavailable", "ready", "collected", "delivered")
                    or refill.get("provider_status") not in ("not_retrieved", "authorization_pending", "ready", "unavailable")
                    or not _text(refill.get("evidence"), 1500)):
                raise ValueError("Malformed pharmacy administration state.")
            if refill["status"] in ("collected", "delivered") and refill.get("collected_by") not in ACTORS:
                raise ValueError("Collection requires a named physical report.")
            if refill["status"] == "delivered" and refill.get("delivered_by") not in ACTORS:
                raise ValueError("Delivery requires a separate named report.")
            if refill["status"] in ("ready", "collected", "delivered") and (refill["provider_status"] != "ready"
                    or type(refill["source_version"]) is not int or refill["source_version"] < 1):
                raise ValueError("Readiness needs a retrieved pharmacy-ready response.")
            if refill["status"] in ("collected", "delivered") and not any(c["request_id"] == request_id and c["kind"] == "pickup"
                    and c["actor_id"] == refill["collected_by"] and c["status"] in ("accepted", "cancelled", "invalidated") for c in data["commitments"]):
                raise ValueError("Collection requires the accepted pickup helper's report.")
        previous = -1
        for event in data["events"]:
            if (type(event) is not dict or set(event) != {"sequence", "day", "text"} or type(event["sequence"]) is not int
                    or not previous < event["sequence"] <= data["sequence"] or type(event["day"]) is not int
                    or not 0 <= event["day"] <= data["day"] or not _text(event["text"], 1500)):
                raise ValueError("Malformed hospital audit history.")
            previous = event["sequence"]
        instance.state = deepcopy(data)
        return instance
