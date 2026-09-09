"""Resident-authored product and room planning; published specifications do not prove fit."""

from copy import deepcopy
from hashlib import sha256
import json
from math import isfinite

from .real_world import NEEDS, match_options


STRATEGIES = {
    "keep": ("Keep", "Continue using the existing item; check whether it meets the stated need."),
    "relocate": ("Relocate", "Try a different place for the existing item before buying anything."),
    "adapt": ("Adapt", "Describe a change to the existing item; assess the work and its cost first."),
    "replace": ("Replace", "Compare sourced products after checking the existing item and the stated need."),
}
ACTIONS = ("assessment_need", "assessment_observation", "assessment_strategy", "assessment_existing",
           "assessment_add", "assessment_remove", "assessment_constraints", "assessment_setup_reply")
NOTICE = ("Planning draft based on the resident's stated need and published product information. "
          "Room placement is an intention, not a measured fit or an installed result. "
          "Prices are source snapshots; stock, condition, shipping, tax, setup, removal, dates, and final total remain unconfirmed. "
          "No purchase or booking occurs; setup help requires the named person's own reply.")

# Source-specific requirements; unknown specifications must not become inferred room dimensions.
ASSEMBLY = {"ikea_nissafors", "moen_dn7060_shower_chair"}
DRILLING = {"moen_r8716d1gch_grab_bar"}

# Sparse resident-reported updates; omitted fields keep their saved values.
DRAFT_SCHEMA = {"type": "object", "additionalProperties": False, "properties": {
    "need": {"type": "string", "enum": list(NEEDS)},
    "observation": {"type": "string", "maxLength": 500},
    "budget_cents": {"type": ["integer", "null"], "minimum": 0, "maximum": 100000000},
    "space": {"type": "object", "additionalProperties": False, "properties": {
        "room_id": {"type": ["string", "null"]},
        **{key: {"type": ["number", "null"], "exclusiveMinimum": 0, "maximum": 10000}
           for key in ("width_in", "depth_in", "height_in")}}},
    "preferences": {"type": "object", "additionalProperties": False, "properties": {
        **{key: {"type": ["boolean", "null"]} for key in ("prefer_existing", "allow_assembly", "allow_drilling")},
        "notes": {"type": "string", "maxLength": 300}}},
    "setup": {"type": "string", "enum": ["unknown", "resident", "family", "professional"]},
    "existing_item": {"type": "object", "additionalProperties": False, "properties": {
        "description": {"type": "string", "maxLength": 200},
        **{key: {"type": ["string", "null"]} for key in ("current_room_id", "target_room_id")}}}}}


def _products(need=None):
    return {item["id"]: item for key in ([need] if need is not None else NEEDS)
            for item in match_options(key)["options"] if item["kind"] == "product"}


class Assessment:
    def __init__(self, host):
        self.host = host
        self.state = {"need": "home_storage", "observation": "", "selections": [], "strategy": "keep",
                      "existing_item": {"description": "", "home_id": host.home["id"],
                                        "current_room_id": None, "target_room_id": None},
                      "constraints": {"budget_cents": None,
                          "space": {"home_id": host.home["id"], "room_id": None, "basis": "unknown",
                                    "width_in": None, "depth_in": None, "height_in": None},
                          "preferences": {"prefer_existing": None, "allow_assembly": None,
                                          "allow_drilling": None, "notes": ""},
                          "setup": "unknown", "recorded_by": "resident"},
                      "setup_acceptance": None}

    def _rooms(self, home_id=None):
        home = self.host.home
        if home_id is not None and home_id != home["id"]:
            # Imported only during validation after simulation has finished loading.
            from .simulation import home_context
            home = home_context(home_id)
        return [{"id": room["label"], "label": room["label"], "use": room["use"]}
                for room in home["rooms"]]

    def _validate(self, data):
        error = "The saved assessment is malformed or refers to an unavailable product or room."
        if (type(data) is not dict or set(data) != set(self.state)
                or type(data["need"]) is not str or data["need"] not in NEEDS
                or type(data["strategy"]) is not str or data["strategy"] not in STRATEGIES
                or type(data["observation"]) is not str or len(data["observation"]) > 500
                or type(data["selections"]) is not list or len(data["selections"]) > 10):
            raise ValueError(error)
        constraints = data["constraints"]
        if (type(constraints) is not dict or set(constraints) != {"budget_cents", "space", "preferences", "setup", "recorded_by"}
                or constraints["budget_cents"] is not None and (type(constraints["budget_cents"]) is not int
                    or not 0 <= constraints["budget_cents"] <= 100000000)
                or type(constraints["setup"]) is not str or constraints["setup"] not in ("unknown", "resident", "family", "professional")
                or type(constraints["recorded_by"]) is not str or constraints["recorded_by"] not in ("resident", "alex", "morgan")):
            raise ValueError(error)
        space, prefs = constraints["space"], constraints["preferences"]
        if (type(space) is not dict or set(space) != {"home_id", "room_id", "basis", "width_in", "depth_in", "height_in"}
                or type(space["home_id"]) is not str or space["home_id"] not in ("demo", "sketch")
                or type(space["basis"]) is not str or space["basis"] not in ("unknown", "reported", "measured")
                or space["room_id"] is not None and (type(space["room_id"]) is not str
                    or space["room_id"] not in {room["id"] for room in self._rooms(space["home_id"])})
                or any(space[key] is not None and (type(space[key]) not in (int, float)
                    or not isfinite(space[key]) or not 0 < space[key] <= 10000)
                    for key in ("width_in", "depth_in", "height_in"))
                or space["basis"] == "measured" and space["room_id"] is None
                or space["basis"] == "unknown" and any(space[key] is not None for key in ("width_in", "depth_in", "height_in"))):
            raise ValueError(error)
        if (type(prefs) is not dict or set(prefs) != {"prefer_existing", "allow_assembly", "allow_drilling", "notes"}
                or any(prefs[key] is not None and type(prefs[key]) is not bool
                       for key in ("prefer_existing", "allow_assembly", "allow_drilling"))
                or type(prefs["notes"]) is not str or len(prefs["notes"]) > 300):
            raise ValueError(error)
        acceptance = data["setup_acceptance"]
        if acceptance is not None and (type(acceptance) is not dict or set(acceptance) != {"actor_id", "scope", "accepted"}
                or type(acceptance["actor_id"]) is not str or acceptance["actor_id"] not in ("alex", "morgan")
                or type(acceptance["accepted"]) is not bool or type(acceptance["scope"]) is not str
                or len(acceptance["scope"]) != 64 or any(c not in "0123456789abcdef" for c in acceptance["scope"])):
            raise ValueError(error)
        existing = data["existing_item"]
        if (type(existing) is not dict or set(existing) != {"description", "home_id", "current_room_id", "target_room_id"}
                or type(existing["description"]) is not str or len(existing["description"]) > 200
                or type(existing["home_id"]) is not str or existing["home_id"] not in ("demo", "sketch")):
            raise ValueError(error)
        if existing["description"]:
            if not existing["description"].strip():
                raise ValueError(error)
            try:
                original_rooms = {room["id"] for room in self._rooms(existing["home_id"])}
            except (OSError, ValueError, KeyError, TypeError):
                raise ValueError(error) from None
            if any(existing[key] is not None and (type(existing[key]) is not str or existing[key] not in original_rooms)
                   for key in ("current_room_id", "target_room_id")):
                raise ValueError(error)
        elif existing["current_room_id"] is not None or existing["target_room_id"] is not None:
            raise ValueError(error)
        products, seen = _products(), set()
        for selection in data["selections"]:
            if (type(selection) is not dict or set(selection) != {"option_id", "quantity", "room_id", "home_id"}
                    or type(selection["option_id"]) is not str or selection["option_id"] not in products
                    or selection["option_id"] in seen or type(selection["quantity"]) is not int
                    or not 1 <= selection["quantity"] <= 10 or type(selection["home_id"]) is not str
                    or selection["home_id"] not in ("demo", "sketch") or type(selection["room_id"]) is not str):
                raise ValueError(error)
            try:
                room_ids = {room["id"] for room in self._rooms(selection["home_id"])}
            except (OSError, ValueError, KeyError, TypeError):
                raise ValueError(error) from None
            if selection["room_id"] not in room_ids:
                raise ValueError(error)
            seen.add(selection["option_id"])

    def _setup_scope(self):
        data = {key: value for key, value in self.state.items() if key != "setup_acceptance"}
        data.update(current_home=self.host.home["id"], day=getattr(getattr(self.host, "coordination", None), "day", None))
        return sha256(json.dumps(data, sort_keys=True, allow_nan=False).encode()).hexdigest()

    def _accepted_setup(self):
        acceptance = self.state["setup_acceptance"]
        coordination = getattr(self.host, "coordination", None)
        if (acceptance and acceptance["accepted"] and acceptance["scope"] == self._setup_scope()
                and coordination is not None and coordination.available(acceptance["actor_id"])):
            return deepcopy(acceptance)
        return None

    def evaluate(self, option_id, quantity=1, room_id=None):
        products = _products()
        if (type(option_id) is not str or option_id not in products or type(quantity) is not int
                or not 1 <= quantity <= 10 or room_id is not None and (type(room_id) is not str
                    or room_id not in {room["id"] for room in self._rooms()})):
            raise ValueError("Choose a listed product, a current room, and a quantity from 1 to 10.")
        source, constraints = products[option_id], self.state["constraints"]
        space, prefs = constraints["space"], constraints["preferences"]
        checks = {}
        def check(key, status, reason):
            checks[key] = {"status": status, "reason": reason}
        others = [item for item in self.state["selections"] if item["option_id"] != option_id]
        items = others + [{"option_id": option_id, "quantity": quantity}]
        known = sum((products[item["option_id"]]["published_price_cents"] or 0) * item["quantity"] for item in items)
        budget = constraints["budget_cents"]
        check("budget", "conflict" if budget is not None and known > budget else "unknown",
              f"Published items total at least ${known / 100:.2f}, above the ${budget / 100:.2f} overall budget."
              if budget is not None and known > budget else
              "Supply an overall budget, including delivery, tax, setup, and removal." if budget is None else
              f"Published items total at least ${known / 100:.2f}; delivery, tax, setup, removal, and final total remain unconfirmed.")
        check("space", "unknown", "Supply available space for this room; a placement drawing does not establish fit.")
        dimensions = source.get("dimensions_in")
        if space["home_id"] == self.host.home["id"] and room_id == space["room_id"] and room_id is not None and space["basis"] != "unknown":
            if type(dimensions) is dict and set(dimensions) == {"length", "width", "height"}:
                # Compare the published orientation only; turning a product or fitting multiple units needs a layout review.
                pairs = [("width_in", "width"), ("depth_in", "length"), ("height_in", "height")]
                too_large = [key for key, source_key in pairs if space[key] is not None and dimensions[source_key] > space[key]]
                if too_large:
                    check("space", "conflict", "Product exceeds the supplied " + ", ".join(key.replace("_in", "") for key in too_large) + " in its published orientation.")
                elif all(space[key] is not None for key, _ in pairs) and space["basis"] == "measured" and quantity == 1:
                    check("space", "suitable_to_review", "Published outer dimensions are within the supplied measurements; access, clearances, and practical fit still need review.")
                else:
                    check("space", "unknown", "Reported or incomplete space, or several units, needs a measured layout and clearance review.")
            else:
                check("space", "unknown", "The source does not give a complete outer footprint for this comparison; component dimensions cannot establish fit.")
        restrictions = []
        if prefs["prefer_existing"] is True:
            restrictions.append("The household prefers using the existing item.")
        if option_id in ASSEMBLY and prefs["allow_assembly"] is False:
            restrictions.append("Assembly is required, but the household wants to avoid assembly.")
        if option_id in DRILLING and prefs["allow_drilling"] is False:
            restrictions.append("Mounted installation conflicts with the no-drilling preference.")
        check("preferences", "conflict" if restrictions else "unknown" if prefs["notes"] or prefs["prefer_existing"] is None else "suitable_to_review",
              " ".join(restrictions) if restrictions else "Review the stated preferences and notes with the resident." if prefs["notes"] or prefs["prefer_existing"] is None else "No recorded structured preference rules out this option.")
        existing = self.state["existing_item"]
        check("existing_item", "suitable_to_review" if existing["description"] and existing["home_id"] == self.host.home["id"] else "unknown",
              "Existing item: " + existing["description"] + "; compare keeping, moving, or adapting it before replacement."
              if existing["description"] and existing["home_id"] == self.host.home["id"] else "Record the current equipment, or that there is no existing item, before choosing a replacement.")
        accepted = self._accepted_setup()
        selected = next((item for item in self.state["selections"] if item["option_id"] == option_id), None)
        accepted_for_item = (accepted and self.state["strategy"] == "replace" and selected
                             and selected["quantity"] == quantity and selected["room_id"] == room_id
                             and selected["home_id"] == self.host.home["id"])
        if option_id in DRILLING or source["review_required"]:
            check("setup", "unknown", "An individual fit or installation assessment is required; a family reply does not establish installer competence or safe fit.")
        elif constraints["setup"] == "family" and accepted_for_item:
            check("setup", "suitable_to_review", accepted["actor_id"].title() + " accepted setup help for this exact draft; completion is still unreported.")
        elif constraints["setup"] == "resident":
            check("setup", "suitable_to_review" if constraints["recorded_by"] == "resident" else "unknown",
                  "Resident plans to handle setup; confirm the instructions and ability to complete it."
                  if constraints["recorded_by"] == "resident" else
                  "Family proposed resident setup; confirm this with the resident and review the instructions.")
        else:
            check("setup", "unknown", "Choose who handles setup and obtain their agreement." if constraints["setup"] == "unknown" else
                  "Family setup help is not currently accepted for this exact item, quantity, room, and constraints." if constraints["setup"] == "family" else
                  "Professional setup needs a provider's scope, quote, and acceptance.")
        if option_id == "serene-hd40p":
            check("setup", "unknown", "An analog phone line, compatibility check, and button programming are required; these are unconfirmed.")
        elif option_id in ("jasco-ge-26140", "dayclocks-digital-8-black"):
            check("setup", "unknown", "Confirm a suitable power outlet and the intended location before setup.")
        status = "conflict" if any(item["status"] == "conflict" for item in checks.values()) else "unknown" if any(item["status"] == "unknown" for item in checks.values()) else "suitable_to_review"
        return {"status": status, "reasons": [item["reason"] for item in checks.values()], "checks": checks,
                "known_items_cents": known, "total_cents": None}

    def view(self, role, actor_id=None):
        if role not in ("resident", "family"):
            raise ValueError("Choose resident or family.")
        products, rooms = _products(), self._rooms()
        room_ids = {room["id"] for room in rooms}
        strategy, existing = self.state["strategy"], self.state["existing_item"]
        replacing = strategy == "replace"
        accepted_setup = self._accepted_setup() if replacing and self.state["constraints"]["setup"] == "family" else None
        existing_before = {"home_id": existing["home_id"], "room_id": existing["current_room_id"]} if existing["description"] else None
        existing_after = (None if replacing or existing_before is None else dict(existing_before,
                          room_id=existing["current_room_id"] if strategy == "keep" else existing["target_room_id"]))
        existing_review = existing["home_id"] != self.host.home["id"] or any(
            existing[key] is not None and existing[key] not in room_ids for key in ("current_room_id", "target_room_id"))
        existing_placement = {"before": existing_before, "after": existing_after,
            "status": "needs_review" if existing_review else "needs_checks", "condition": "unknown", "accepted": False,
            "annotation": "Home changed; check the existing item and its rooms again." if existing_review else
                          "Resident-reported item and proposed change; condition, measurements, fit, and completion are unverified."}
        selections, known_subtotal, unknown_count = [], 0, 0
        for saved in self.state["selections"]:
            source = products[saved["option_id"]]
            price = source["published_price_cents"]
            subtotal = None if price is None else price * saved["quantity"]
            if replacing and subtotal is None:
                unknown_count += saved["quantity"]
            elif replacing:
                known_subtotal += subtotal
            dimensions = {key: value for key, value in source.get("specs", {}).items()
                          if "dimension" in key or key.endswith(("_in", "_inches"))}
            if "dimensions_in" in source:
                dimensions["dimensions_in"] = source["dimensions_in"]
            needs_review = saved["home_id"] != self.host.home["id"] or saved["room_id"] not in room_ids
            evaluation = self.evaluate(saved["option_id"], saved["quantity"], saved["room_id"] if not needs_review else None)
            selections.append({**saved, "active": replacing, "source": source, "item_subtotal_cents": subtotal,
                "source_dimensions": dimensions, "evaluation": evaluation,
                "fit_status": "assessment_required" if source["review_required"] else "needs_checks",
                "condition": "unknown",
                "rationale": source["match_reason"] + " Selected by the resident; the current observation is unverified context, not proof this product will help.",
                "placement": {"before": None,
                    "after": {"home_id": saved["home_id"], "room_id": saved["room_id"]} if replacing else None,
                    "status": "needs_review" if needs_review else "needs_checks",
                    "annotation": "Home changed; choose the placement again." if needs_review else
                                  "Saved replacement option; not part of the current strategy." if not replacing else
                                  "Proposed for " + saved["room_id"] + "; measurements and fit still need checking."},
                "responsibility": {"actor": accepted_setup["actor_id"] if accepted_setup and not needs_review else "resident",
                    "task": "Help with setup; confirm any specialist assessment separately" if accepted_setup and not needs_review else "Review fit and choose who receives and sets up the item",
                    "accepted": bool(accepted_setup and not needs_review)}})
        steps = {"keep": {"fit", "feedback"}, "relocate": {"fit", "quote", "setup", "feedback"},
                 "adapt": {"fit", "quote", "setup", "feedback"},
                 "replace": {"fit", "quote", "delivery", "setup", "removal", "feedback"}}[strategy]
        timeline = [{"id": key, "label": label, "date": None, "status": "not_scheduled", "actor": actor,
                     "accepted": False} for key, label, actor in (
            ("fit", "Check fit and room measurements", "resident"),
            ("quote", "Confirm the full delivered price" if replacing else "Confirm any assessment and work costs", "resident"),
            ("delivery", "Confirm delivery and who receives it", "helper_or_provider"),
            ("setup", "Arrange setup if needed", "helper_or_provider"),
            ("removal", "Arrange removal if needed", "helper_or_provider"),
            ("feedback", "Review usefulness with the resident", "resident")) if key in steps]
        if accepted_setup:
            for step in timeline:
                if step["id"] == "setup":
                    step.update(actor=accepted_setup["actor_id"], accepted=True)
        evaluated = []
        for source in _products(self.state["need"]).values():
            saved = next((item for item in self.state["selections"] if item["option_id"] == source["id"]), None)
            candidate_room = saved["room_id"] if saved and saved["home_id"] == self.host.home["id"] else self.state["constraints"]["space"]["room_id"]
            evaluated.append({**source, "evaluation": self.evaluate(source["id"], saved["quantity"] if saved else 1,
                                                                     candidate_room if candidate_room in room_ids else None)})
        identified_family = role == "family" and actor_id in ("alex", "morgan")
        coordination = getattr(self.host, "coordination", None)
        can_reply = bool(identified_family and replacing and selections and self.state["constraints"]["setup"] == "family"
                         and all(item["home_id"] == self.host.home["id"] for item in selections)
                         and coordination is not None and coordination.available(actor_id))
        actions = [action for action in ACTIONS if action != "assessment_setup_reply" and (replacing or action != "assessment_add")] if role == "resident" else []
        if identified_family:
            actions.append("assessment_constraints")
        if can_reply:
            actions.append("assessment_setup_reply")
        return deepcopy({"need": self.state["need"], "observation": self.state["observation"], "strategy": strategy,
            "strategies": [{"id": key, "label": values[0], "rationale": values[1]} for key, values in STRATEGIES.items()],
            "existing_item": existing, "existing_placement": existing_placement,
            "needs": [{"id": key, "label": label} for key, label in NEEDS.items()],
            "candidates": evaluated if replacing else [], "evaluated_candidates": evaluated, "rooms": rooms, "selections": selections,
            "constraints": self.state["constraints"], "setup_scope": self._setup_scope(),
            "setup_acceptance": self.state["setup_acceptance"], "accepted_setup": self._accepted_setup(),
            "costs": {"currency": "USD", "known_item_subtotal_cents": known_subtotal,
                "unknown_item_count": unknown_count, "item_subtotal_cents": None if unknown_count else known_subtotal,
                "partial_known_subtotal": bool(unknown_count), "delivery_cents": None, "setup_cents": None,
                "removal_cents": None, "tax_cents": None, "assessment_cents": None,
                "one_time_total_cents": None, "total_cents": None, "recurring_cents": None, "recurring_period": None},
            "timeline": timeline, "controls": {"can_edit": role == "resident",
                "can_edit_constraints": role == "resident" or identified_family, "can_reply_setup": can_reply,
                "actions": actions}, "notice": NOTICE})

    def apply(self, action, role, payload, actor_id=None):
        if role not in ("resident", "family") or role == "resident" and actor_id not in (None, "resident"):
            raise ValueError("Choose the person making this assessment update.")
        if role != "resident" and not (actor_id in ("alex", "morgan") and action in ("assessment_constraints", "assessment_setup_reply")):
            raise ValueError("Only the resident can change this assessment draft.")
        if type(action) is not str or action not in ACTIONS or type(payload) is not dict:
            raise ValueError("Choose a supported assessment action and its fields.")
        data = self.dump()
        if action == "assessment_setup_reply":
            if (role != "family" or set(payload) != {"accepted", "scope"} or type(payload["accepted"]) is not bool
                    or type(payload["scope"]) is not str or payload["scope"] != self._setup_scope()
                    or not self.view(role, actor_id)["controls"]["can_reply_setup"]):
                raise ValueError("Only the named family member can reply to the current setup draft.")
            current = self._accepted_setup()
            if current and current["actor_id"] != actor_id:
                raise ValueError("Another person accepted this setup draft; they must withdraw their own reply first.")
            data["setup_acceptance"] = {"actor_id": actor_id, **payload}
            text = actor_id.title() + (" accepted setup help for this draft." if payload["accepted"] else " declined setup help for this draft.")
        elif action == "assessment_constraints":
            if (set(payload) != {"budget_cents", "space", "preferences", "setup"} or type(payload["space"]) is not dict
                    or set(payload["space"]) != {"room_id", "basis", "width_in", "depth_in", "height_in"}):
                raise ValueError("Supply the overall budget, room space, preferences, and setup plan.")
            data["constraints"] = {**deepcopy(payload), "space": {**payload["space"], "home_id": self.host.home["id"]},
                                   "recorded_by": "resident" if role == "resident" else actor_id}
            text = "Updated the shared household constraints; product comparisons now use these inputs."
        elif action == "assessment_strategy":
            if set(payload) != {"strategy"} or type(payload["strategy"]) is not str or payload["strategy"] not in STRATEGIES:
                raise ValueError("Choose keep, relocate, adapt, or replace.")
            data["strategy"] = payload["strategy"]
            text = "Updated the strategy. Saved product choices remain drafts; no work or purchase was arranged."
        elif action == "assessment_existing":
            if (set(payload) != {"description", "current_room_id", "target_room_id"}
                    or type(payload["description"]) is not str or not payload["description"].strip()
                    or len(payload["description"]) > 200 or any(type(payload[key]) is not str
                        or payload[key] not in {room["id"] for room in self._rooms()}
                        for key in ("current_room_id", "target_room_id"))):
                raise ValueError("Describe the existing item in 1 to 200 characters and choose its current and proposed rooms.")
            data["existing_item"] = {**payload, "home_id": self.host.home["id"]}
            text = "Recorded the existing item and room intentions from the resident's report; fit and completion are unverified."
        elif action == "assessment_need":
            if set(payload) != {"need"} or type(payload["need"]) is not str or payload["need"] not in NEEDS:
                raise ValueError("Choose a listed need.")
            data["need"] = payload["need"]
            text = "Updated the stated need. Existing selections remain in the draft."
        elif action == "assessment_observation":
            if set(payload) != {"text"} or type(payload["text"]) is not str or len(payload["text"]) > 500:
                raise ValueError("Use a resident observation of at most 500 characters.")
            data["observation"] = payload["text"]
            text = "Recorded the resident's observation; no measurements or fit were inferred."
        elif action == "assessment_add":
            if (data["strategy"] != "replace" or set(payload) != {"option_id", "quantity", "room_id"} or type(payload["option_id"]) is not str
                    or payload["option_id"] not in _products(data["need"]) or type(payload["quantity"]) is not int
                    or not 1 <= payload["quantity"] <= 10 or type(payload["room_id"]) is not str
                    or payload["room_id"] not in {room["id"] for room in self._rooms()}):
                raise ValueError("Choose a product for this need, a room, and a quantity from 1 to 10.")
            if len(data["selections"]) >= 10 or any(item["option_id"] == payload["option_id"] for item in data["selections"]):
                raise ValueError("Keep at most 10 different products. Remove an existing selection before changing it.")
            data["selections"].append({**payload, "home_id": self.host.home["id"]})
            text = "Added a product and proposed room to the draft. Fit, costs, and arrangements still need checking."
        elif action == "assessment_remove":
            if (set(payload) != {"option_id"} or type(payload["option_id"]) is not str
                    or not any(item["option_id"] == payload["option_id"] for item in data["selections"])):
                raise ValueError("Choose a product already in this draft.")
            data["selections"] = [item for item in data["selections"] if item["option_id"] != payload["option_id"]]
            text = "Removed the product from the draft."
        if action != "assessment_setup_reply":
            data["setup_acceptance"] = None
        self._validate(data)
        self.state = data
        return text

    def dump(self):
        return deepcopy(self.state)

    def proposed(self, draft):
        """Validate a partial report in isolation; the coordinator decides when to commit it."""
        self.validate_draft(draft)
        proposed = type(self).restore(self.host, self.dump())
        data = proposed.state
        for key in ("need", "observation"):
            if key in draft:
                data[key] = deepcopy(draft[key])
        constraints = data["constraints"]
        for key in ("budget_cents", "setup"):
            if key in draft:
                constraints[key] = deepcopy(draft[key])
        if "preferences" in draft:
            constraints["preferences"].update(deepcopy(draft["preferences"]))
        if "space" in draft:
            space = constraints["space"]
            if (space["home_id"] != self.host.home["id"] or space["room_id"] is not None
                    and draft["space"].get("room_id", space["room_id"]) != space["room_id"]):
                space.update(home_id=self.host.home["id"], room_id=None, basis="unknown", width_in=None, depth_in=None, height_in=None)
            space.update(deepcopy(draft["space"]))
            if any(key in draft["space"] for key in ("width_in", "depth_in", "height_in")):
                space["basis"] = "reported" if any(space[key] is not None for key in ("width_in", "depth_in", "height_in")) else "unknown"
        if "existing_item" in draft:
            item = data["existing_item"]
            if item["home_id"] != self.host.home["id"]:
                item.update(home_id=self.host.home["id"], current_room_id=None, target_room_id=None)
            item.update(deepcopy(draft["existing_item"]))
            if item["description"] == "":
                item.update(current_room_id=None, target_room_id=None)
        # This existing provenance field also controls whether resident setup was
        # their own intention. An unrelated budget correction cannot confer that.
        if "setup" in draft:
            constraints["recorded_by"] = "resident"
        if data != self.state:
            data["setup_acceptance"] = None
        proposed._validate(data)
        return proposed

    def validate_draft(self, draft):
        """Also validate historical reports without applying them to today's draft."""
        types = {"object": (dict,), "string": (str,), "integer": (int,), "number": (int, float),
                 "boolean": (bool,), "null": (type(None),)}
        def check(value, schema):
            kinds = schema["type"] if type(schema["type"]) is list else [schema["type"]]
            if type(value) not in tuple(t for kind in kinds for t in types[kind]):
                raise ValueError("Use the supplied equipment field types.")
            if value is None:
                return
            if ("enum" in schema and value not in schema["enum"]
                    or type(value) is str and len(value) > schema.get("maxLength", 64)
                    or type(value) in (int, float) and (type(value) is float and not isfinite(value)
                        or value < schema.get("minimum", 0) or value > schema.get("maximum", 100000000)
                        or "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"])):
                raise ValueError("An equipment draft value is outside its allowed choices or range.")
            if type(value) is dict:
                if not value or set(value) - set(schema["properties"]):
                    raise ValueError("Use only the supplied equipment draft fields.")
                for key, part in value.items():
                    check(part, schema["properties"][key])
        check(draft, DRAFT_SCHEMA)
        rooms = {room["id"] for home_id in ("demo", "sketch") for room in self._rooms(home_id)}
        for group, keys in (("space", ("room_id",)), ("existing_item", ("current_room_id", "target_room_id"))):
            if any(draft.get(group, {}).get(key) is not None and draft[group][key] not in rooms for key in keys):
                raise ValueError("Choose a supplied home room.")

    def context(self):
        view = self.view("resident")
        # New needs must be resolved from supplied catalog IDs before changing the draft.
        view["catalog_products"] = list(_products().values())
        return view

    @classmethod
    def restore(cls, host, data):
        assessment = cls(host)
        if type(data) is dict and set(data) == {"need", "observation", "selections", "strategy", "existing_item"}:
            data = {**deepcopy(data), "constraints": assessment.state["constraints"], "setup_acceptance": None}
        assessment._validate(data)
        assessment.state = deepcopy(data)
        return assessment
