"""Synthetic household state. Human confirmation, never generated text, changes facts."""

from copy import deepcopy
import json
from pathlib import Path
from threading import RLock
from week import WeekPlan
from real_world import NEEDS, match_options
from mission import Mission
from coordination import Coordination, ACTORS
from meal import Meal
from assessment import Assessment
from hospital import Hospital
from family_edition import FamilyEdition

ASSETS = Path(__file__).resolve().parent / "assets"
PUBLIC_DISCOVERY = [match_options(need) for need in NEEDS]


def home_context(home_id):
    if home_id == "sketch":
        if not (ASSETS / "sketch-home.png").is_file():
            raise InvalidAction("The sketch model is still being prepared.")
        try:
            layout = json.loads((ASSETS / "sketch-layout.json").read_text())
            facts = {key: layout[key] for key in ("confirmed", "assumptions", "unknowns")}
            rooms = [{"label": room["label"], "use": room["use"]} for room in layout["rooms"]]
        except (OSError, ValueError, KeyError, TypeError):
            raise InvalidAction("The sketch model context is not ready.") from None
        return {"id": "sketch", "label": "Your house sketch", "image": "/assets/sketch-home.png",
                "blend": "/assets/sketch-home.blend", "glb": "/assets/sketch-home.glb",
                "scale_status": "Approximate layout; dimensions and clearances unmeasured.",
                "rooms": rooms, **facts}
    return {"id": "demo", "label": "One-bedroom household", "image": "/assets/home.png",
            "blend": "/assets/home.blend", "glb": "/assets/home.glb",
            "scale_status": "Demo layout; room dimensions have not been measured.",
            "rooms": [{"label": name, "use": name.lower()} for name in
                      ("Bedroom", "Living room", "Hall", "Bathroom", "Entrance")],
            "confirmed": [], "assumptions": ["Rooms and household facts are authored for the demo."],
            "unknowns": ["No real mobility or safety assessment has been performed."]}


class InvalidAction(ValueError):
    pass


class Household:
    def __init__(self, save_path=None):
        self._lock = RLock()
        self.save_path = Path(save_path) if save_path is not None else None
        self.mission_persistence = {"enabled": self.save_path is not None,
                                    "status": "not_saved", "message": "No mission saved yet."}
        self.revision = 0
        self.context_revision = 0
        self.home = home_context("demo")
        self._reset()
        if self.save_path is not None and self.save_path.exists():
            try:
                self._restore_mission()
            except (OSError, ValueError):
                self.mission_persistence.update(status="load_error", message="Saved mission could not be validated; a fresh household is shown.")

    def _reset(self):
        self.appointment = {
            "day": "Tuesday", "date": "2026-09-15", "time": "10:00",
            "pickup": "09:15", "reason": "Private follow-up", "location": "",
        }
        self.transport = {
            "status": "confirmed", "person": "Alex", "for_date": "2026-09-15",
        }
        self.documents = {
            "location": "Entrance shelf", "status": "confirmed",
            "recorded_at": "Tuesday, 08:00",
        }
        self._actual_document_location = "Entrance shelf"
        self.activity = [{"text": "Tuesday appointment and pickup confirmed.",
                          "revision": self.revision}]
        self._reset_game()
        self.week = WeekPlan(self)
        self.mission = Mission(self)
        self.mission_proposals = []
        self.coordination = Coordination(self)
        self._observed_memory_revision = self.coordination.state.get("memory_revision", 0)
        self.meal = Meal(self)
        self.hospital = Hospital(self)
        self.assessment = Assessment(self)
        self.family_edition = FamilyEdition(self)

    def _reset_game(self):
        self.outing = {"choice": "undecided", "support": "not_requested",
                       "completed_steps": [], "position": "invitation"}

    def _outing_view(self):
        result = deepcopy(self.outing)
        steps = ("invitation", "bag", "entrance")
        choice, done = result["choice"], len(result["completed_steps"])
        result["activity"] = {
            "title": "Neighbourhood garden open hour", "when": "Saturday, 14:00",
            "place": "Neighbourhood garden", "is_sample": True,
            "description": "A garden visit with time to prepare a bag and arrange company. No event is booked.",
        }
        result["next_hotspot"] = steps[done] if choice == "joined" and done < 3 else None
        result["outcome"] = ("staying_home" if choice == "declined" else "choose" if choice == "undecided"
                             else "preparing" if done < 3 else "waiting_for_support"
                             if result["support"] == "requested" else "ready")
        result["message"] = {
            "choose": "Visit the garden, or keep your usual routine. The choice is yours.",
            "staying_home": "You chose your usual routine. Nothing else is required.",
            "preparing": "Click the highlighted room marker to prepare at your own pace.",
            "waiting_for_support": "Preparation is complete. Your requested companion still needs to accept.",
            "ready": "Garden-visit preparation is complete in the demo. Event access and real support still need arranging.",
        }[result["outcome"]]
        try:
            result["hotspots"] = json.loads((ASSETS / "game-hotspots.json").read_text())[self.home["id"]]
        except (OSError, ValueError, KeyError):
            result["hotspots"] = []
        return result

    def _play(self, action, role):
        game = self.outing
        if action == "confirm_support":
            if role != "family" or game["choice"] != "joined" or game["support"] != "requested":
                raise InvalidAction("Only a family member can accept an outstanding support request.")
            game["support"] = "confirmed"
            return "A family member accepted the garden companion request in the demo."
        if role != "resident":
            raise InvalidAction("The resident chooses their activity and preparation steps.")
        if action in ("join_activity", "keep_routine", "restart_game"):
            self._reset_game()
            self.outing["choice"] = {"join_activity": "joined", "keep_routine": "declined",
                                     "restart_game": "undecided"}[action]
            return {"join_activity": "Resident chose the neighbourhood garden visit.",
                    "keep_routine": "Resident chose their usual routine; no further action is needed.",
                    "restart_game": "The garden visit is ready to start again."}[action]
        if game["choice"] != "joined":
            raise InvalidAction("Choose the garden visit before preparing or requesting help.")
        if action == "request_support":
            if game["support"] != "not_requested":
                raise InvalidAction("The support request is already recorded.")
            game["support"] = "requested"
            return "Resident requested company for the garden visit; acceptance is pending."
        step = action.removeprefix("game_")
        expected = self._outing_view()["next_hotspot"]
        if step != expected:
            raise InvalidAction("Choose the highlighted preparation step first.")
        game["completed_steps"].append(step)
        game["position"] = step
        return {"invitation": "Read the garden invitation in the living room.",
                "bag": "Collected the tote bag in the bedroom.",
                "entrance": "Reached the entrance in the demo."}[step]

    @staticmethod
    def _role(role):
        if role not in ("resident", "family"):
            raise InvalidAction("Choose resident or family.")

    @classmethod
    def _actor(cls, role, actor_id=None):
        cls._role(role)
        actor_id = actor_id or ("resident" if role == "resident" else "alex")
        if actor_id not in (("resident",) if role == "resident" else ("alex", "morgan")):
            raise InvalidAction("Choose a named actor in this perspective.")
        return actor_id

    def view(self, role, actor_id=None):
        actor_id = self._actor(role, actor_id)
        with self._lock:
            appointment = dict(self.appointment)
            if role == "family":
                appointment.pop("reason")
            steps = []
            if self.transport["status"] != "confirmed":
                steps.append("Ask a family member to confirm the "
                             f"{appointment['day']} {appointment['pickup']} pickup.")
            if self.documents["status"] != "confirmed":
                steps.append("Ask the resident to check where the documents are now.")
            return deepcopy({
                "role": role, "actor_id": actor_id, "revision": self.revision, "context_revision": self.context_revision,
                "appointment": appointment, "transport": self.transport,
                "documents": self.documents,
                "plan_status": "needs_attention" if steps else "ready",
                "next_steps": steps, "activity": self.activity[-12:],
                "home": self.home,
                "outing": self._outing_view(),
                "week": self.week.view(role),
                "mission": dict(self.mission.view(role), proposals=deepcopy(self.mission_proposals)),
                "mission_persistence": self.mission_persistence,
                "coordination": self.coordination.view(role, actor_id),
                "meal": self.meal.view(role, actor_id),
                "assessment": self.assessment.view(role, actor_id),
                "hospital": self.hospital.view(role, actor_id),
                "family_edition": self.family_edition.view(role, actor_id),
                "public_discovery": PUBLIC_DISCOVERY,
                "sketch_available": (ASSETS / "sketch-home.png").is_file() and
                                    (ASSETS / "sketch-layout.json").is_file(),
                "notice": "Demo household: appointments, travel, and item locations are fictional, even on your house sketch. "
                          "Chat sends this role's plan and selected house context to OpenAI. Room dimensions are unmeasured.",
            })

    def comparison(self):
        from comparison import compare_households
        return compare_households()

    def _sync_memory_context(self):
        current = self.coordination.state.get("memory_revision", 0)
        if current != self._observed_memory_revision:
            self.context_revision += 1
            self._observed_memory_revision = current

    def _coordination_changed(self):
        self.hospital.shared_changed()
        self.mission.shared_changed("coordination_update")
        self.coordination.shared_changed()
        self._sync_memory_context()
        self.revision += 1
        self._persist_mission()

    def begin_coordination(self, request_id, message, expected_revision, replace_request_id=None, *, initiated_by="resident"):
        with self._lock:
            duplicate = any(item["id"] == request_id for item in self.coordination.view("resident")["requests"])
            if not duplicate and (type(expected_revision) is not int or expected_revision != self.revision):
                raise InvalidAction("The plan changed. Refresh before starting this request.")
            try:
                result = self.coordination.begin(request_id, message, replace_request_id, initiated_by=initiated_by)
            except ValueError as error:
                raise InvalidAction(str(error)) from None
            if not result["duplicate"]:
                self._coordination_changed()
            return deepcopy(result)

    def coordination_context(self, request_id):
        with self._lock:
            try:
                return deepcopy(self.coordination.context(request_id))
            except ValueError as error:
                raise InvalidAction(str(error)) from None

    def accept_coordination(self, request_id, proposal, expected_version):
        with self._lock:
            try:
                result = self.coordination.accept(request_id, proposal, expected_version)
            except ValueError as error:
                raise InvalidAction(str(error)) from None
            self._coordination_changed()
            return deepcopy(result)

    def advance_coordination(self, request_id):
        with self._lock:
            try:
                changed = self.coordination.advance(request_id)
            except ValueError as error:
                raise InvalidAction(str(error)) from None
            if changed:
                self._coordination_changed()
            return changed

    def fail_coordination(self, request_id, message):
        with self._lock:
            before = self.coordination.dump()
            self.coordination.fail(request_id, message)
            if self.coordination.dump() != before:
                self._coordination_changed()

    def recipient_context(self, actor_id, expected_revision):
        actor_id = self._actor("family", actor_id)
        with self._lock:
            if type(expected_revision) is not int or expected_revision != self.revision:
                raise InvalidAction("The plan changed. Refresh before replying.")
            return deepcopy(self.coordination.reply_context(actor_id))

    def accept_recipient_reply(self, reply_id, actor_id, message, proposal, expected_version):
        actor_id = self._actor("family", actor_id)
        with self._lock:
            before = self.coordination.version
            try:
                result = self.coordination.apply_reply(reply_id, actor_id, message, proposal, expected_version)
            except ValueError as error:
                raise InvalidAction(str(error)) from None
            if self.coordination.version != before:
                message_ids = {decision["message_id"] for decision in result["decisions"]}
                affected = {item["request_id"] for item in self.coordination.state["messages"] if item["id"] in message_ids}
                self._resume_requests(affected)
                self._coordination_changed()
            return deepcopy(result)

    def _resume_requests(self, request_ids):
        """A supplied human reply resumes only its existing, already permitted plan."""
        for request_id in request_ids:
            for _ in range(12):
                try:
                    changed = self.coordination.advance(request_id)
                except ValueError:
                    self.coordination.fail(request_id, "A plan step could not continue. Review the pending arrangement.")
                    break
                if not changed:
                    break

    def coordinator_view(self):
        """Only observed mission facts and permitted coordinator actions reach Astra."""
        with self._lock:
            return dict(self.mission.coordinator_view(), revision=self.revision,
                        identity="Astra coordinator")

    def apply_mission_proposal(self, proposal, expected_revision):
        with self._lock:
            valid = (type(proposal) is dict and set(proposal) == {"action", "reason"}
                     and type(proposal["action"]) is str and 0 < len(proposal["action"]) <= 80
                     and type(proposal["reason"]) is str and 0 < len(proposal["reason"]) <= 1000)
            record = {"action": proposal["action"] if valid else "invalid_proposal",
                      "reason": proposal["reason"] if valid else "Invalid structured proposal.",
                      "accepted": False, "result": "", "rejection": None}
            if type(expected_revision) is not int or expected_revision != self.revision:
                record.update(rejection="stale", result="The mission changed while Astra was choosing. No action was applied.")
            elif not valid:
                record.update(rejection="invalid", result="Astra must select one bounded action and supply a reason.")
            else:
                try:
                    record["result"] = self.mission.apply(proposal["action"], "coordinator", {})
                    record["accepted"] = True
                except ValueError as error:
                    record.update(rejection="invalid", result=str(error))
            self.revision += 1
            record.update(revision=self.revision, actor="Astra coordinator", engine="gpt-6-astra")
            self.mission_proposals.append(record)
            self.mission_proposals = self.mission_proposals[-40:]
            self._persist_mission()
            return deepcopy(record)

    def _persist_mission(self):
        if self.save_path is None:
            return
        from persistence import save_household
        try:
            save_household(self, self.save_path)
            self.mission_persistence.update(status="saved", message="Household saved locally. Restart restores facts without repeating actions.")
        except (OSError, ValueError):
            self.mission_persistence.update(status="save_error", message="The household changed, but its local save failed.")

    def _restore_mission(self):
        from persistence import load_household
        restored = load_household(self.save_path)
        revision, context = max(self.revision, restored.revision) + 1, max(self.context_revision, restored.context_revision) + 1
        for name in ("home", "appointment", "transport", "documents", "_actual_document_location",
                     "activity", "outing", "week", "mission", "mission_proposals", "coordination", "meal", "assessment", "hospital", "family_edition"):
            setattr(self, name, getattr(restored, name))
        self.week.host = self
        self.mission.host = self
        self.coordination.host = self
        self.meal.host = self
        self.assessment.host = self
        self.hospital.host = self
        self.family_edition.host = self
        self._observed_memory_revision = self.coordination.state.get("memory_revision", 0)
        self.revision, self.context_revision = revision, context
        self._persist_mission()
        if self.mission_persistence["status"] != "save_error":
            self.mission_persistence.update(status="restored", message="Saved mission restored. No requests, movement or confirmations were replayed.")

    def event(self, action, role, expected_revision=None, payload=None, actor_id=None):
        actor_id = self._actor(role, actor_id)
        if not isinstance(action, str):
            raise InvalidAction("Choose a supported action.")
        if payload is not None and type(payload) is not dict:
            raise InvalidAction("Action details must be an object.")
        with self._lock:
            game_actions = ("join_activity", "keep_routine", "restart_game", "request_support",
                            "confirm_support", "game_invitation", "game_bag", "game_entrance")
            if type(expected_revision) is not int or expected_revision != self.revision:
                raise InvalidAction("The plan changed or its version is missing. Refresh before confirming.")
            if action == "reset" and role != "resident":
                raise InvalidAction("The resident controls the household reset.")
            if action in ("confirm_ride", "decline_ride") and role != "family":
                raise InvalidAction("A family member must confirm their own availability.")
            if action == "confirm_documents" and role != "resident":
                raise InvalidAction("The resident must confirm the document location.")

            if action == "reset":
                self.revision += 1
                self.context_revision += 1
                self._reset()
                self._persist_mission()
                return self.view(role, actor_id)
            if action in ("mission_save", "mission_restore"):
                if role != "resident" or payload not in (None, {}):
                    raise InvalidAction("The resident controls the saved mission.")
                if self.save_path is None:
                    raise InvalidAction("Local mission saving is not enabled for this household.")
                if action == "mission_restore":
                    try:
                        self._restore_mission()
                    except (OSError, ValueError):
                        raise InvalidAction("The saved mission is missing or could not be validated.") from None
                else:
                    self.revision += 1
                    self._persist_mission()
                return self.view(role, actor_id)
            if action.startswith(("coordination_", "meal_", "assessment_", "hospital_", "family_edition_")):
                details = dict(payload or {})
                if "actor_id" in details and details["actor_id"] != actor_id:
                    raise InvalidAction("The reply must come from the selected named person.")
                if action.startswith("coordination_") and role == "family":
                    details["actor_id"] = actor_id
                domain = (self.coordination if action.startswith("coordination_") else
                          self.meal if action.startswith("meal_") else
                          self.hospital if action.startswith("hospital_") else
                          self.family_edition if action.startswith("family_edition_") else self.assessment)
                accepted_messages = {item["id"]: item["request_id"] for item in self.coordination.state["messages"]
                    if action in ("coordination_availability", "coordination_set_availability")
                    and details.get("available") is False
                    and item["recipient"] == actor_id and item["status"] == "accepted"}
                try:
                    text = (domain.apply(action, role, details, actor_id=actor_id)
                            if domain is not self.meal else domain.apply(action, role, details))
                except ValueError as error:
                    raise InvalidAction(str(error)) from None
                if action in ("coordination_availability", "coordination_set_availability") and details.get("available") is False:
                    acceptance = self.assessment.state.get("setup_acceptance")
                    if (acceptance and acceptance.get("actor_id") == actor_id
                            and self.coordination.availability_for(actor_id) is False):
                        self.assessment.state["setup_acceptance"] = None
                    self._resume_requests({request_id for message_id, request_id in accepted_messages.items()
                        if self.coordination._get("messages", message_id)["status"] == "declined"})
                if action == "coordination_reply":
                    request_ids = {item["request_id"] for item in self.coordination.state["messages"]
                                   if item["id"] == details.get("message_id")}
                    self._resume_requests(request_ids)
                elif action in ("hospital_resume", "hospital_collect", "hospital_deliver", "hospital_withdraw"):
                    request_ids = {details["request_id"]} if "request_id" in details else {
                        item["request_id"] for item in self.hospital.state["commitments"]
                        if item["id"] == details.get("commitment_id")}
                    self._resume_requests(request_ids)
                self.coordination.shared_changed(force=action.startswith(("assessment_", "hospital_", "family_edition_")))
                self._sync_memory_context()
                self.hospital.shared_changed()
                self.mission.shared_changed(action)
                self.revision += 1
                # Movement is authored simulation state; it is not a human intervention.
                if action != "meal_tick":
                    self.activity.append({"text": "Household routine or arrangement updated.", "revision": self.revision})
                    self.activity = self.activity[-120:]
                self._persist_mission()
                return self.view(role, actor_id)
            if action.startswith("mission_"):
                try:
                    text = self.mission.apply(action, role, payload)
                except ValueError as error:
                    raise InvalidAction(str(error)) from None
                if action in ("mission_start", "mission_reset"):
                    self.mission_proposals = []
                    self.context_revision += 1
            elif action.startswith("week_"):
                try:
                    text = self.week.apply(action, role, payload)
                except ValueError as error:
                    raise InvalidAction(str(error)) from None
                if action in ("week_select_profile", "week_reset"):
                    self.activity = []
                    self.coordination = Coordination(self)
                    self._observed_memory_revision = self.coordination.state.get("memory_revision", 0)
                    self.meal = Meal(self)
                    self.hospital = Hospital(self)
                    self.assessment = Assessment(self)
                    self.family_edition = FamilyEdition(self)
                if action in ("week_select_profile", "week_reset", "week_mode", "week_configure"):
                    self.context_revision += 1
            elif action in game_actions:
                text = self._play(action, role)
            elif action in ("select_sketch", "select_demo"):
                previous_home = self.home["id"]
                self.home = home_context("sketch" if action == "select_sketch" else "demo")
                if self.home["id"] != previous_home:
                    self.assessment.state["setup_acceptance"] = None
                self.context_revision += 1
                self._reset_game()
                text = f"Viewing {self.home['label']}. The demo appointment and document plan is unchanged."
            elif action == "reschedule":
                if self.appointment["date"] == "2026-09-17":
                    return self.view(role, actor_id)
                self.appointment.update(day="Thursday", date="2026-09-17", time="11:00", pickup="10:15")
                self.transport.update(status="needs_confirmation", person=None, for_date=None)
                text = "Appointment moved to Thursday at 11:00. The 10:15 pickup needs confirmation."
            elif action in ("confirm_ride", "decline_ride"):
                accepted = action == "confirm_ride"
                person = ACTORS[actor_id]
                if not accepted and self.transport["person"] not in (None, person):
                    raise InvalidAction("Only the named driver can withdraw their pickup commitment.")
                self.transport.update(
                    status="confirmed" if accepted else "declined",
                    person=person if accepted else None,
                    for_date=self.appointment["date"] if accepted else None,
                )
                text = (f"{person} confirmed the {self.appointment['day']} {self.appointment['pickup']} pickup."
                        if accepted else f"{person} cannot drive. The pickup still needs another person.")
            elif action == "move_documents":
                self._actual_document_location = "Bedroom drawer"
                self.documents["status"] = "last_known"
                text = "The documents have moved. Check their current location before preparing for departure."
            elif action == "confirm_documents":
                self.documents.update(location=self._actual_document_location, status="confirmed",
                                      recorded_at=f"Resident confirmation, update {self.revision + 1}")
                text = f"The resident confirmed the documents are at: {self._actual_document_location}."
            else:
                raise InvalidAction("Choose a supported action.")
            if not action.startswith(("week_", "mission_")):
                self.week.legacy_changed(action)
            if not action.startswith("mission_"):
                self.mission.shared_changed(action)
            self.coordination.shared_changed(force=action in ("select_sketch", "select_demo"))
            self.hospital.shared_changed()
            self.revision += 1
            self.activity.append({"text": text, "revision": self.revision})
            self.activity = self.activity[-120:]
            self._persist_mission()
            return self.view(role, actor_id)
