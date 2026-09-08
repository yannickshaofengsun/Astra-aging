"""Synthetic household state. Human confirmation, never generated text, changes facts."""

from copy import deepcopy
import json
from pathlib import Path
from threading import RLock
from week import WeekPlan
from real_world import NEEDS, match_options

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
    return {"id": "demo", "label": "Example household", "image": "/assets/home.png",
            "blend": "/assets/home.blend", "glb": "/assets/home.glb",
            "scale_status": "Illustrative synthetic layout; not a measured real home.",
            "rooms": [{"label": name, "use": name.lower()} for name in
                      ("Bedroom", "Living room", "Hall", "Bathroom", "Entrance")],
            "confirmed": [], "assumptions": ["All room geometry and household facts are synthetic."],
            "unknowns": ["No real mobility or safety assessment has been performed."]}


class InvalidAction(ValueError):
    pass


class Household:
    def __init__(self):
        self._lock = RLock()
        self.revision = 0
        self.context_revision = 0
        self.home = home_context("demo")
        self._reset()

    def _reset(self):
        self.appointment = {
            "day": "Tuesday", "date": "2026-09-15", "time": "10:00",
            "pickup": "09:15", "reason": "Private follow-up — synthetic example",
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

    def _reset_game(self):
        self.outing = {"choice": "undecided", "support": "not_requested",
                       "completed_steps": [], "position": "invitation"}

    def _outing_view(self):
        result = deepcopy(self.outing)
        steps = ("invitation", "bag", "entrance")
        choice, done = result["choice"], len(result["completed_steps"])
        result["activity"] = {
            "title": "Neighbourhood garden open hour", "when": "Saturday, 14:00",
            "place": "Example community garden", "is_sample": True,
            "description": "A fictional local activity to try in the simulation. No signup or booking occurs.",
        }
        result["next_hotspot"] = steps[done] if choice == "joined" and done < 3 else None
        result["outcome"] = ("staying_home" if choice == "declined" else "choose" if choice == "undecided"
                             else "preparing" if done < 3 else "waiting_for_support"
                             if result["support"] == "requested" else "ready")
        result["message"] = {
            "choose": "Try the sample activity, or keep your usual routine. Both choices are valid.",
            "staying_home": "You chose your usual routine. Nothing else is required.",
            "preparing": "Click the highlighted room marker to prepare at your own pace.",
            "waiting_for_support": "Preparation is complete. Your requested companion still needs to accept.",
            "ready": "Ready in this simulation. No real activity signup, route, or support has been arranged.",
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
            return "A family member accepted the fictional companion request."
        if role != "resident":
            raise InvalidAction("The resident chooses their activity and preparation steps.")
        if action in ("join_activity", "keep_routine", "restart_game"):
            self._reset_game()
            self.outing["choice"] = {"join_activity": "joined", "keep_routine": "declined",
                                     "restart_game": "undecided"}[action]
            return {"join_activity": "Resident chose to try the fictional local activity.",
                    "keep_routine": "Resident chose their usual routine; no further action is needed.",
                    "restart_game": "The household game is ready to replay."}[action]
        if game["choice"] != "joined":
            raise InvalidAction("Choose to try the sample activity before preparing or requesting help.")
        if action == "request_support":
            if game["support"] != "not_requested":
                raise InvalidAction("The support request is already recorded.")
            game["support"] = "requested"
            return "Resident requested a companion for the fictional activity; acceptance is pending."
        step = action.removeprefix("game_")
        expected = self._outing_view()["next_hotspot"]
        if step != expected:
            raise InvalidAction("Choose the highlighted preparation step first.")
        game["completed_steps"].append(step)
        game["position"] = step
        return {"invitation": "Read the fictional invitation in the living room.",
                "bag": "Collected the fictional tote in the bedroom.",
                "entrance": "Reached the illustrative departure point in the simulation."}[step]

    @staticmethod
    def _role(role):
        if role not in ("resident", "family"):
            raise InvalidAction("Choose resident or family.")

    def view(self, role):
        self._role(role)
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
                "role": role, "revision": self.revision, "context_revision": self.context_revision,
                "appointment": appointment, "transport": self.transport,
                "documents": self.documents,
                "plan_status": "needs_attention" if steps else "ready",
                "next_steps": steps, "activity": self.activity[-12:],
                "home": self.home,
                "outing": self._outing_view(),
                "week": self.week.view(role),
                "public_discovery": PUBLIC_DISCOVERY,
                "sketch_available": (ASSETS / "sketch-home.png").is_file() and
                                    (ASSETS / "sketch-layout.json").is_file(),
                "notice": "The appointment, transport, and document-location scenario is fictional, "
                          "including when viewing your house sketch. Chat sends this role's scenario "
                          "and selected house context to OpenAI. House dimensions remain unmeasured.",
            })

    def comparison(self):
        from comparison import compare_households
        return compare_households()

    def event(self, action, role, expected_revision=None, payload=None):
        self._role(role)
        if not isinstance(action, str):
            raise InvalidAction("Choose a supported action.")
        with self._lock:
            game_actions = ("join_activity", "keep_routine", "restart_game", "request_support",
                            "confirm_support", "game_invitation", "game_bag", "game_entrance")
            if action.startswith("week_") or action in ("confirm_ride", "decline_ride", "confirm_documents") + game_actions:
                if type(expected_revision) is not int or expected_revision != self.revision:
                    raise InvalidAction("The plan changed or its version is missing. Refresh before confirming.")
            if action in ("confirm_ride", "decline_ride") and role != "family":
                raise InvalidAction("A family member must confirm their own availability.")
            if action == "confirm_documents" and role != "resident":
                raise InvalidAction("The resident must confirm the document location.")

            if action == "reset":
                self.revision += 1
                self.context_revision += 1
                self._reset()
                return self.view(role)
            if action.startswith("week_"):
                try:
                    text = self.week.apply(action, role, payload)
                except ValueError as error:
                    raise InvalidAction(str(error)) from None
                if action in ("week_select_profile", "week_reset"):
                    self.activity = []
                if action in ("week_select_profile", "week_reset", "week_mode", "week_configure"):
                    self.context_revision += 1
            elif action in game_actions:
                text = self._play(action, role)
            elif action in ("select_sketch", "select_demo"):
                self.home = home_context("sketch" if action == "select_sketch" else "demo")
                self.context_revision += 1
                self._reset_game()
                text = f"Viewing {self.home['label']}. Appointment and document facts remain a fictional scenario."
            elif action == "reschedule":
                if self.appointment["date"] == "2026-09-17":
                    return self.view(role)
                self.appointment.update(day="Thursday", date="2026-09-17", time="11:00", pickup="10:15")
                self.transport.update(status="needs_confirmation", person=None, for_date=None)
                text = "Appointment moved to Thursday at 11:00. The 10:15 pickup needs confirmation."
            elif action in ("confirm_ride", "decline_ride"):
                accepted = action == "confirm_ride"
                self.transport.update(
                    status="confirmed" if accepted else "declined",
                    person="Alex" if accepted else None,
                    for_date=self.appointment["date"] if accepted else None,
                )
                text = (f"Alex confirmed the {self.appointment['day']} {self.appointment['pickup']} pickup."
                        if accepted else "Alex cannot drive. The pickup still needs another person.")
            elif action == "move_documents":
                self._actual_document_location = "Bedroom drawer"
                self.documents["status"] = "last_known"
                text = "Documents moved in the scenario. Their recorded location is now last known."
            elif action == "confirm_documents":
                self.documents.update(location=self._actual_document_location, status="confirmed",
                                      recorded_at=f"Resident confirmation, update {self.revision + 1}")
                text = f"The resident confirmed the documents are at: {self._actual_document_location}."
            else:
                raise InvalidAction("Choose a supported action.")
            if not action.startswith("week_"):
                self.week.legacy_changed(action)
            self.revision += 1
            self.activity.append({"text": text, "revision": self.revision})
            return self.view(role)
