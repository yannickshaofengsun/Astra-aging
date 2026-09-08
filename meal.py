"""An authored ordinary meal, with person movement separate from coordination."""

from collections import deque
from copy import deepcopy
import re

ACTORS = {"resident": "Resident", "alex": "Alex", "morgan": "Morgan"}
ANCHORS = ("resident_start", "entry", "kitchen_entry", "pantry", "preparation", "table_approach", "table_seat", "sink")
EDGES = (("resident_start", "table_approach"), ("entry", "kitchen_entry"),
         ("kitchen_entry", "pantry"), ("pantry", "preparation"),
         ("preparation", "kitchen_entry"), ("kitchen_entry", "table_approach"),
         ("table_approach", "table_seat"), ("kitchen_entry", "sink"))
PHASES = ("idle", "go_kitchen", "retrieve", "go_prepare", "prepare", "waiting_help", "go_recover",
          "go_table_loaded", "go_table_empty", "serve", "sit", "eat", "collect", "go_sink", "clear", "complete", "stopped")
FEEDBACK = ("keep_routine", "prefer_independent", "help_was_useful", "help_did_not_help")


def _person(key):
    position = "resident_start" if key == "resident" else "entry"
    return {"name": ACTORS[key], "position": position, "path": [position], "path_index": 0,
            "phase": "idle", "carry": [], "visible": key == "resident"}


def _episode(episode_id=1, day=1):
    return {"schema": 1, "episode_id": episode_id, "day": day, "status": "idle", "phase": "idle", "step": 0,
            "choice": {"meal": "The resident's already chosen meal", "utensils": "Usual bowl and utensils"},
            "actors": {key: _person(key) for key in ACTORS},
            "objects": {key: {"label": label, "location": "pantry", "state": "stored"} for key, label in
                        (("meal", "Chosen meal in its bowl"), ("utensils", "Usual utensils"))},
            "help": {"request_id": None, "helper": None, "episode_id": episode_id, "day": day, "status": "none"},
            "events": [], "history": [], "feedback": []}


def _interaction_anchor(actor, location):
    return "table_seat" if location == "table_approach" and actor == "resident" else location


def _path(start, end):
    queue = deque([[start]])
    seen = {start}
    while queue:
        path = queue.popleft()
        if path[-1] == end:
            return path
        for a, b in EDGES:
            neighbour = b if a == path[-1] else a if b == path[-1] else None
            if neighbour and neighbour not in seen:
                seen.add(neighbour)
                queue.append(path + [neighbour])
    raise ValueError("No authored path connects these scene anchors.")


class Meal:
    def __init__(self, host):
        self.host = host
        self.state = _episode(day=getattr(getattr(host, "coordination", None), "day", 1))

    def _event(self, actor, action, text):
        s = self.state
        s["events"].append({"actor": actor, "action": action, "text": text, "step": s["step"]})
        s["events"] = s["events"][-100:]
        return text

    def _walk(self, actor, destination):
        person = self.state["actors"][actor]
        person.update(path=_path(person["position"], destination), path_index=0, phase="walking", visible=True)

    def _move(self, actor):
        person = self.state["actors"][actor]
        if person["path_index"] < len(person["path"]) - 1:
            person["path_index"] += 1
            person["position"] = person["path"][person["path_index"]]
            self._event(actor, "arrive", person["name"] + " reached " + person["position"] + " on the authored path.")
        arrived = person["path_index"] == len(person["path"]) - 1
        if arrived:
            person["phase"] = "arrived"
        return arrived

    def _take(self, actor, location):
        s, person = self.state, self.state["actors"][actor]
        allowed_position = _interaction_anchor(actor, location)
        if person["position"] != allowed_position or any(obj["location"] != location for obj in s["objects"].values()):
            raise ValueError("A person must arrive at the objects before picking them up.")
        person["carry"] = ["meal", "utensils"]
        for obj in s["objects"].values():
            obj["location"] = actor
        self._event(actor, "pick_up", person["name"] + " picked up the bowl and utensils after arriving.")

    def _place(self, actor, location, state=None):
        s, person = self.state, self.state["actors"][actor]
        allowed_position = _interaction_anchor(actor, location)
        if person["position"] != allowed_position or set(person["carry"]) != {"meal", "utensils"}:
            raise ValueError("A carrying person must arrive before placing the objects.")
        for obj in s["objects"].values():
            obj["location"] = location
            if state:
                obj["state"] = state
        person["carry"] = []
        self._event(actor, "place", person["name"] + " placed the bowl and utensils at " + location + ".")

    def _archive(self, outcome):
        s = self.state
        if any(row["episode_id"] == s["episode_id"] for row in s["history"]):
            return
        s["history"].append({"episode_id": s["episode_id"], "day": s["day"], "outcome": outcome,
                             "steps": s["step"], "help_status": s["help"]["status"]})
        # ponytail: retain 30 local episodes and feedback entries; this is not a longitudinal care record.
        s["history"] = s["history"][-30:]

    def _cancel_help(self):
        help_state = self.state["help"]
        if help_state["status"] not in ("requested", "accepted"):
            return
        request_id = help_state["request_id"]
        self.helper_reply(request_id, help_state["helper"], "cancelled")
        coordination = getattr(self.host, "coordination", None)
        if coordination is not None and hasattr(coordination, "cancel_help"):
            coordination.cancel_help(request_id)

    def _new_episode(self, day=None, playing=False):
        previous = self.state
        if previous["episode_id"] >= 100000:
            raise ValueError("The local rehearsal episode limit has been reached.")
        self._cancel_help()
        if previous["status"] != "idle":
            self._archive("completed" if previous["status"] == "completed" else "stopped")
        self.state = _episode(previous["episode_id"] + 1, previous["day"] if day is None else day)
        for key in ("choice", "history", "feedback"):
            self.state[key] = deepcopy(previous[key])
        if playing:
            self.state.update(status="running", phase="go_kitchen")
            self._walk("resident", "pantry")

    def next_day(self, day):
        if type(day) is not int or not self.state["day"] < day <= 100000:
            raise ValueError("Advance to a later supported fictional day.")
        self._new_episode(day=day)
        return self._event("system", "next_day", "A new fictional day starts with a fresh meal episode and no accepted helper carried forward.")

    def help_context(self):
        s = self.state
        can_request = (s["status"] in ("idle", "running", "paused")
                       and s["phase"] in ("idle", "go_kitchen", "retrieve", "go_prepare", "prepare", "waiting_help")
                       and s["help"]["status"] == "none")
        return {"episode_id": s["episode_id"], "day": s["day"], "can_request": can_request,
                "phase": s["phase"], "help": deepcopy(s["help"]),
                "reason": "Optional carrying help can be requested before independent carrying starts." if can_request else
                          "This episode already has a request or carrying has begun; continue the current routine or replay."}

    def request_help(self, request_id, helper):
        if type(request_id) is not str or re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", request_id) is None or helper not in ("alex", "morgan"):
            raise ValueError("Use a bounded request ID and a named helper.")
        s = self.state
        if s["help"]["request_id"] == request_id and s["help"]["helper"] == helper:
            return deepcopy(s["help"])
        if not self.help_context()["can_request"]:
            raise ValueError("Carrying help is not available at this point in the meal.")
        s["help"].update(request_id=request_id, helper=helper, status="requested")
        self._event("resident", "request_help", "Resident explicitly requested " + ACTORS[helper] + " for carrying help in this episode.")
        return deepcopy(s["help"])

    def helper_reply(self, request_id, helper, status):
        s, help_state = self.state, self.state["help"]
        if (helper not in ("alex", "morgan") or status not in ("accepted", "declined", "cancelled")
                or help_state["request_id"] != request_id or help_state["helper"] != helper
                or help_state["episode_id"] != s["episode_id"] or help_state["day"] != s["day"]
                or s["status"] not in ("idle", "running", "paused")
                or help_state["status"] not in (("requested", "accepted") if status == "cancelled" else ("requested",))):
            raise ValueError("This helper reply does not match a pending current-episode responsibility.")
        if status == "accepted":
            coordination = getattr(self.host, "coordination", None)
            if coordination is None or not coordination.available(helper):
                raise ValueError("The helper's availability must be established for this day.")
        help_state["status"] = status
        person = s["actors"][helper]
        if status == "accepted":
            self._walk(helper, "preparation")
        elif person["carry"]:
            person["phase"] = "stopping"
        else:
            person["phase"] = "cancelled" if status == "cancelled" else "declined"
        self._event(helper, "helper_reply", ACTORS[helper] + " " + status + " the carrying request; agreement alone is not physical completion.")
        return deepcopy(help_state)

    def _helper_tick(self):
        s, help_state = self.state, self.state["help"]
        helper = help_state["helper"]
        if helper is None:
            return
        person = s["actors"][helper]
        if person["phase"] == "stopping":
            self._place(helper, person["position"])
            person["phase"] = "cancelled"
            return
        if help_state["status"] != "accepted":
            return
        if person["phase"] == "walking":
            self._move(helper)
            return
        if person["phase"] == "arrived" and person["carry"]:
            self._place(helper, "table_approach", "served")
            help_state["status"] = "completed"
            person["phase"] = "completed"
            self.host.coordination.complete_help(help_state["request_id"])
        elif person["position"] == "preparation" and s["phase"] == "waiting_help" and all(
                obj["location"] == "preparation" and obj["state"] == "prepared" for obj in s["objects"].values()):
            self._take(helper, "preparation")
            self._walk(helper, "table_approach")

    def _independent_carry(self):
        s, person = self.state, self.state["actors"]["resident"]
        location = s["objects"]["meal"]["location"]
        if location in ACTORS:
            return  # A cancelled helper must first put the load down on a later authorized tick.
        target = _interaction_anchor("resident", location)
        if person["position"] != target:
            self._walk("resident", target)
            s["phase"] = "go_recover"
        else:
            self._take("resident", location)
            self._walk("resident", "table_seat")
            s["phase"] = "go_table_loaded"

    def can_tick(self):
        s = self.state
        if s["status"] != "running" or s["step"] >= 100000:
            return False
        return not (s["phase"] == "waiting_help" and s["help"]["status"] == "requested")

    def _tick(self):
        s, person = self.state, self.state["actors"]["resident"]
        s["step"] += 1
        self._helper_tick()
        phase = s["phase"]
        destinations = {"go_kitchen": "retrieve", "go_prepare": "prepare", "go_recover": "recover",
                        "go_table_loaded": "serve", "go_table_empty": "sit", "go_sink": "clear"}
        if phase in destinations:
            if self._move("resident"):
                next_phase = destinations[phase]
                if next_phase == "recover":
                    self._independent_carry()
                else:
                    s["phase"] = next_phase
        elif phase == "retrieve":
            self._take("resident", "pantry")
            for obj in s["objects"].values():
                obj["state"] = "retrieved"
            self._walk("resident", "preparation")
            s["phase"] = "go_prepare"
        elif phase == "prepare":
            self._place("resident", "preparation", "prepared")
            person["phase"] = "preparing"
            self._event("resident", "prepare", "Resident performed the authored preparation/reheating of their already chosen meal.")
            s["phase"] = "waiting_help"
        elif phase == "waiting_help":
            if s["help"]["status"] == "completed":
                self._walk("resident", "table_seat")
                s["phase"] = "go_table_empty"
            elif s["help"]["status"] in ("none", "declined", "cancelled"):
                self._independent_carry()
        elif phase == "serve":
            self._place("resident", "table_approach", "served")
            s["phase"] = "sit"
        elif phase == "sit":
            person["phase"] = "seated"
            s["phase"] = "eat"
            self._event("resident", "sit", "Resident sat at their usual eating place after arriving.")
        elif phase == "eat":
            person["phase"] = "eating"
            for obj in s["objects"].values():
                obj["state"] = "used"
            s["phase"] = "collect"
            self._event("resident", "eat", "The authored meal-eating step completed; no real intake or health outcome is inferred.")
        elif phase == "collect":
            self._take("resident", "table_approach")
            self._walk("resident", "sink")
            s["phase"] = "go_sink"
        elif phase == "clear":
            self._place("resident", "sink", "cleared")
            person["phase"] = "completed"
            s.update(status="completed", phase="complete")
            self._event("resident", "clear", "Resident cleared the used dishes. The ordinary authored meal is complete.")
            self._archive("completed")
        return "Ordinary meal advanced by one authored simulation step."

    def apply(self, action, role, payload=None):
        payload = {} if payload is None else payload
        if role != "resident" or type(action) is not str or type(payload) is not dict:
            raise ValueError("The resident controls this ordinary routine.")
        s = self.state
        if action == "meal_tick":
            if (set(payload) != {"episode_id", "step"} or any(type(value) is not int for value in payload.values())
                    or payload != {"episode_id": s["episode_id"], "step": s["step"]} or not self.can_tick()):
                raise ValueError("The meal is paused, waiting, finished, or this episode step is stale.")
            return self._tick()
        if action == "meal_feedback":
            if set(payload) != {"feedback"} or payload["feedback"] not in FEEDBACK or s["status"] not in ("completed", "stopped"):
                raise ValueError("Choose a supported reflection after the episode.")
            if any(row["episode_id"] == s["episode_id"] for row in s["feedback"]):
                raise ValueError("Feedback for this episode is already recorded.")
            s["feedback"].append({"episode_id": s["episode_id"], "day": s["day"], "feedback": payload["feedback"]})
            s["feedback"] = s["feedback"][-30:]
            return "Resident feedback recorded without inferring a health or safety outcome."
        if payload or action not in {control["action"] for control in self.view(role)["controls"]}:
            raise ValueError("This meal control is not available in the current state.")
        if action == "meal_start":
            s.update(status="running", phase="go_kitchen")
            self._walk("resident", "pantry")
        elif action == "meal_play":
            s["status"] = "running"
        elif action == "meal_pause":
            s["status"] = "paused"
        elif action == "meal_stop":
            self._cancel_help()
            s.update(status="stopped", phase="stopped")
            self._archive("stopped")
        elif action == "meal_replay":
            self._new_episode(playing=True)
        elif action == "meal_continue_independently":
            self._cancel_help()
        return self._event("resident", action, {
            "meal_start": "Resident started their ordinary meal routine.", "meal_play": "Resident resumed the authored routine.",
            "meal_pause": "Resident paused; no movement or object action executes while paused.",
            "meal_stop": "Resident stopped this episode; incomplete actions remain incomplete.",
            "meal_replay": "A new authored episode began; previous results and feedback are retained.",
            "meal_continue_independently": "Resident chose to continue independently; requested help was cancelled."
        }[action])

    def view(self, role, actor_id=None):
        allowed = {"resident": (None, "resident"), "family": (None, "alex", "morgan"), "coordinator": (None, "coordinator")}
        if role not in allowed or actor_id not in allowed[role]:
            raise ValueError("Choose a supported household perspective.")
        s = self.state
        controls = []
        if role == "resident":
            if s["status"] == "idle":
                controls.append({"action": "meal_start", "label": "Start ordinary meal"})
            if s["status"] == "paused":
                controls.append({"action": "meal_play", "label": "Play"})
            if s["status"] == "running":
                controls.append({"action": "meal_pause", "label": "Pause"})
            if s["status"] in ("running", "paused"):
                controls.append({"action": "meal_stop", "label": "Stop this episode"})
            if s["status"] != "idle":
                controls.append({"action": "meal_replay", "label": "Replay ordinary meal"})
            if s["help"]["status"] in ("requested", "accepted") and s["status"] in ("idle", "running", "paused"):
                controls.append({"action": "meal_continue_independently", "label": "Continue independently"})
        return deepcopy({**{key: s[key] for key in s if key != "schema"}, "can_tick": self.can_tick(),
                         "controls": controls, "feedback_options": list(FEEDBACK), "help_context": self.help_context(),
                         "scene": {"image": "/assets/meal-room.png", "layout": "/assets/meal-scene.json", "anchors": list(ANCHORS)},
                         "notice": "Authored fictional movement and object interactions; paths and timing are illustrative. "
                                   "No physical clearance, nutrition, intake monitoring, health or safety score is claimed."})

    def dump(self):
        return deepcopy(self.state)

    @classmethod
    def restore(cls, host, data):
        cls._validate(data)
        if getattr(getattr(host, "coordination", None), "day", data["day"]) != data["day"]:
            raise ValueError("Saved meal day does not match the shared household day.")
        meal = cls(host)
        meal.state = deepcopy(data)
        return meal

    @staticmethod
    def _validate(data):
        def bad():
            raise ValueError("Saved meal state is malformed or inconsistent.")
        def shape(value, template):
            if type(value) is not type(template) and template is not None:
                bad()
            if type(template) is dict:
                if set(value) != set(template):
                    bad()
                for key in template:
                    shape(value[key], template[key])
            elif template is None and value is not None and (type(value) is not str or len(value) > 80):
                bad()
            elif type(template) is str and len(value) > 300:
                bad()
        shape(data, _episode())
        s, help_state = data, data["help"]
        if (s["schema"] != 1 or not 1 <= s["episode_id"] <= 100000 or not 1 <= s["day"] <= 100000
                or not 0 <= s["step"] <= 100000 or s["status"] not in ("idle", "running", "paused", "completed", "stopped")
                or s["phase"] not in PHASES or len(s["events"]) > 100 or len(s["history"]) > 30 or len(s["feedback"]) > 30
                or help_state["episode_id"] != s["episode_id"] or help_state["day"] != s["day"]
                or help_state["status"] not in ("none", "requested", "accepted", "declined", "cancelled", "completed")):
            bad()
        if (help_state["status"] == "none") != (help_state["request_id"] is None and help_state["helper"] is None):
            bad()
        if help_state["status"] != "none" and (help_state["helper"] not in ("alex", "morgan") or type(help_state["request_id"]) is not str
                or re.fullmatch(r"[A-Za-z0-9_.:-]{1,80}", help_state["request_id"]) is None):
            bad()
        if ((s["status"] == "idle") != (s["phase"] == "idle") or (s["status"] == "completed") != (s["phase"] == "complete")
                or (s["status"] == "stopped") != (s["phase"] == "stopped")):
            bad()
        for actor, person in s["actors"].items():
            if (person["name"] != ACTORS[actor] or person["position"] not in ANCHORS or not 1 <= len(person["path"]) <= len(ANCHORS)
                    or any(anchor not in ANCHORS for anchor in person["path"]) or not 0 <= person["path_index"] < len(person["path"])
                    or person["path"][person["path_index"]] != person["position"]
                    or person["phase"] not in ("idle", "walking", "arrived", "preparing", "seated", "eating", "completed", "stopping", "cancelled", "declined")
                    or any(obj not in ("meal", "utensils") for obj in person["carry"]) or len(person["carry"]) != len(set(person["carry"]))):
                bad()
            if any((a, b) not in EDGES and (b, a) not in EDGES for a, b in zip(person["path"], person["path"][1:])):
                bad()
            if actor != "resident" and person["visible"] and help_state["helper"] != actor:
                bad()
        for key, obj in s["objects"].items():
            if obj["location"] not in ANCHORS + tuple(ACTORS) or obj["state"] not in ("stored", "retrieved", "prepared", "served", "used", "cleared"):
                bad()
            carriers = [actor for actor, person in s["actors"].items() if key in person["carry"]]
            if carriers != ([obj["location"]] if obj["location"] in ACTORS else []):
                bad()
        if (s["objects"]["meal"]["location"] != s["objects"]["utensils"]["location"]
                or s["objects"]["meal"]["state"] != s["objects"]["utensils"]["state"]):
            bad()
        if s["status"] == "completed" and (s["objects"]["meal"] ["location"] != "sink" or s["objects"]["meal"]["state"] != "cleared"
                or s["actors"]["resident"]["position"] != "sink" or s["actors"]["resident"]["phase"] != "completed"):
            bad()
        if help_state["status"] == "completed" and (s["actors"][help_state["helper"]]["phase"] != "completed"
                or s["actors"][help_state["helper"]]["position"] != "table_approach"
                or s["actors"][help_state["helper"]]["carry"]
                or s["objects"]["meal"]["state"] not in ("served", "used", "cleared")):
            bad()
        if help_state["status"] == "accepted":
            helper = s["actors"][help_state["helper"]]
            target = "table_approach" if helper["carry"] else "preparation"
            if (not helper["visible"] or helper["phase"] not in ("walking", "arrived")
                    or helper["path"][-1] != target or helper["phase"] == "arrived" and helper["position"] != target
                    or s["status"] in ("completed", "stopped")):
                bad()
        if help_state["status"] == "cancelled":
            helper = s["actors"][help_state["helper"]]
            if helper["phase"] not in ("cancelled", "stopping") or bool(helper["carry"]) != (helper["phase"] == "stopping"):
                bad()
        obj, person, phase = s["objects"]["meal"], s["actors"]["resident"], s["phase"]
        if s["status"] != "stopped":
            # Each resumable phase pins the physical prerequisites of its next authored action.
            expected = {
                "idle": ("stored", "pantry"), "go_kitchen": ("stored", "pantry"), "retrieve": ("stored", "pantry"),
                "go_prepare": ("retrieved", "resident"), "prepare": ("retrieved", "resident"),
                "go_recover": ("prepared", None), "go_table_loaded": ("prepared", "resident"), "serve": ("prepared", "resident"),
                "go_table_empty": ("served", "table_approach"), "sit": ("served", "table_approach"), "eat": ("served", "table_approach"),
                "collect": ("used", "table_approach"), "go_sink": ("used", "resident"), "clear": ("used", "resident"),
                "complete": ("cleared", "sink")}
            if phase in expected:
                state, location = expected[phase]
                if obj["state"] != state or location is not None and obj["location"] != location:
                    bad()
            required_anchor = {"idle": "resident_start", "retrieve": "pantry", "prepare": "preparation",
                               "waiting_help": "preparation", "serve": "table_seat", "sit": "table_seat",
                               "eat": "table_seat", "collect": "table_seat", "clear": "sink", "complete": "sink"}
            if phase in required_anchor and person["position"] != required_anchor[phase]:
                bad()
            targets = {"go_kitchen": "pantry", "go_prepare": "preparation", "go_table_loaded": "table_seat",
                       "go_table_empty": "table_seat", "go_sink": "sink"}
            if phase == "go_recover":
                if obj["location"] not in ANCHORS:
                    bad()
                targets[phase] = _interaction_anchor("resident", obj["location"])
            if phase in targets and (person["phase"] != "walking" or person["path"][-1] != targets[phase]):
                bad()
            if phase == "waiting_help" and (obj["state"] != "prepared" or obj["location"] not in ("preparation", "alex", "morgan")):
                bad()
        if help_state["status"] == "completed" and obj["state"] == "served" and obj["location"] != "table_approach":
            bad()
        for event in s["events"]:
            if (type(event) is not dict or set(event) != {"actor", "action", "text", "step"} or event["actor"] not in tuple(ACTORS) + ("system",)
                    or type(event["action"]) is not str or len(event["action"]) > 80 or type(event["text"]) is not str or len(event["text"]) > 600
                    or type(event["step"]) is not int or not 0 <= event["step"] <= s["step"]):
                bad()
        for rows, keys in ((s["history"], {"episode_id", "day", "outcome", "steps", "help_status"}),
                           (s["feedback"], {"episode_id", "day", "feedback"})):
            seen = set()
            for row in rows:
                if (type(row) is not dict or set(row) != keys or type(row["episode_id"]) is not int or type(row["day"]) is not int
                        or not 1 <= row["episode_id"] <= s["episode_id"] or not 1 <= row["day"] <= s["day"] or row["episode_id"] in seen):
                    bad()
                seen.add(row["episode_id"])
                if "feedback" in row:
                    if row["feedback"] not in FEEDBACK:
                        bad()
                elif (row["outcome"] not in ("completed", "stopped") or type(row["steps"]) is not int or not 0 <= row["steps"] <= 100000
                      or row["help_status"] not in ("none", "requested", "accepted", "declined", "cancelled", "completed")):
                    bad()
