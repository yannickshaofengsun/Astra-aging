"""Opt-in family news for a paper edition; no private sources or real fulfillment."""

from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import tempfile

EDITION_DIR = Path(__file__).resolve().parent / ".runtime" / "editions"
ACTORS = {"alex": "Alex", "morgan": "Morgan"}
FIXTURES = {
    "alex_tomatoes": {"owner": "alex", "kind": "photo", "title": "Tomatoes on the balcony",
        "text": "The balcony tomatoes finally turned red. We picked six this week and put them on toast. I thought you would enjoy seeing how much the plants have grown.",
        "caption": "Alex's first tomatoes of the season.", "plan": "reported", "photo_label": "Fictional placeholder: tomatoes on a balcony"},
    "morgan_bread": {"owner": "morgan", "kind": "photo", "title": "The bread rose this time",
        "text": "I tried the bread recipe again. This loaf rose properly! I saved a photo of the first slice to share with you.",
        "caption": "A fictional photo of Morgan's homemade bread.", "plan": "reported", "photo_label": "Fictional placeholder: a loaf of bread"},
    "morgan_visit": {"owner": "morgan", "kind": "note", "title": "A possible October visit",
        "text": "I hope to visit one Sunday in October. No date is agreed yet. I will check with you before making plans.",
        "caption": "", "plan": "tentative", "photo_label": ""},
    "alex_walk": {"owner": "alex", "kind": "photo", "title": "A walk by the water",
        "text": "I went for a walk by the water after the rain and watched the ducks. I wanted to share a small moment from the day.",
        "caption": "An authored fictional walk, contributed only by Alex.", "plan": "reported", "photo_label": "Fictional placeholder: ducks beside the water"},
}


def _task():
    return {"helper": None, "status": "not_requested", "edition_revision": 0, "request_id": None, "attempts": []}


def _initial():
    return {"schema": 1, "edition_revision": 1, "cancelled": False,
            "preferences": {"recipient": "resident", "month": "2026-09", "cadence": "off", "language": "English",
                            "type_size": 20, "allow_print_help": False, "allow_delivery_help": False, "budget_cents": 200},
            "sharing": {"alex": False, "morgan": False},
            "items": {key: {**deepcopy(value), "version": 0, "month": "2026-09", "submitted": False,
                             "approved_version": None, "approval": None} for key, value in FIXTURES.items()},
            "selected": [], "artifact": None, "tasks": {"print": _task(), "delivery": _task()}, "history": [], "events": []}


def _pdf_string(text):
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


# Standard PDF Helvetica glyph widths in thousandths of an em; no runtime font dependency.
_WIDTHS = (278,278,355,556,556,889,667,191,333,333,389,584,278,333,278,278,556,556,556,556,556,556,556,556,556,556,278,278,584,584,584,556,1015,667,667,722,722,667,611,778,722,278,500,667,556,833,722,778,667,778,722,667,611,722,667,944,667,667,611,278,278,278,469,556,333,556,556,500,556,556,278,556,556,222,222,500,222,833,556,556,556,556,333,500,278,556,500,722,500,500,500,334,260,334,584)
_BOLD_WIDTHS = (278,333,474,556,556,889,722,238,333,333,389,584,278,333,278,278,556,556,556,556,556,556,556,556,556,556,333,333,584,584,584,611,975,722,722,722,722,667,611,778,722,278,556,722,611,833,722,778,667,778,722,667,611,722,667,944,667,667,611,333,278,333,584,556,333,556,611,556,611,556,333,611,611,278,278,556,278,889,611,611,611,611,389,556,333,611,556,778,556,556,500,389,280,389,584)


def _wrap(value, size, bold=False):
    widths = _BOLD_WIDTHS if bold else _WIDTHS
    def fits(text):
        return sum(widths[ord(ch) - 32] for ch in text) * size / 1000 <= 528
    lines, line = [], ""
    for word in value.split():
        if line and fits(line + " " + word):
            line += " " + word
            continue
        if line:
            lines.append(line)
        while not fits(word):
            cut = 1
            while cut < len(word) and fits(word[:cut + 1]):
                cut += 1
            lines.append(word[:cut])
            word = word[cut:]
        line = word
    if line:
        lines.append(line)
    return lines


def _pdf_document(items, month, type_size, revision):
    """Small ASCII/Helvetica PDF writer with measured wrapping and two-page maximum."""
    pages, chunks, used = [], [[]], 0
    for item in items:
        height = len(_wrap(item["title"], 22, True)) * 25 + 27 + len(_wrap(item["text"], type_size)) * (type_size + 5) + 23
        if item["kind"] == "photo":
            height += 85 + len(_wrap(item["caption"], 16)) * 20
        if used + height > 576:
            chunks.append([])
            used = 0
        chunks[-1].append(item)
        used += height
    if len(chunks) > 2 or not items:
        raise ValueError("Choose a shorter selection or shorter notes so this large-text edition fits two pages.")
    for page_number, chunk in enumerate(chunks, 1):
        commands = []
        def text(x, y, value, size=type_size, bold=False):
            commands.append(f"BT /{'F2' if bold else 'F1'} {size} Tf 0 g 1 0 0 1 {x} {y} Tm ({_pdf_string(value)}) Tj ET")
        def rule(y):
            commands.append(f"0.65 G 0.6 w 42 {y} m 570 {y} l S")
        text(42, 751, "A little news from the family", 25, True)
        text(42, 723, datetime.strptime(month, "%Y-%m").strftime("%B %Y") + f"  |  Edition {revision}", 17)
        text(42, 699, "Fictional demo: shared notes and labeled photo placeholders.", 12)
        rule(687)
        y = 661
        for item in chunk:
            for line in _wrap(item["title"], 22, True):
                text(42, y, line, 22, True)
                y -= 25
            attribution = ACTORS[item["owner"]] + " - " + ("Tentative plan; no date agreed" if item["plan"] == "tentative" else "Fictional contributed note")
            text(42, y, attribution, 13)
            y -= 27
            for line in _wrap(item["text"], type_size):
                text(42, y, line)
                y -= type_size + 5
            if item["kind"] == "photo":
                y -= 5
                commands.append(f"0.95 g 42 {y - 57} 528 57 re f 0.55 G 0.7 w 42 {y - 57} 528 57 re S")
                text(54, y - 33, item["photo_label"], 15)
                y -= 80
                for line in _wrap(item["caption"], 16):
                    text(42, y, line, 16)
                    y -= 20
            y -= 23
        if page_number == len(chunks):
            # Space belongs to the resident; no questionnaire or compulsory response.
            text(42, max(73, y), "A note back, if you feel like writing:", 16)
            rule(max(53, y - 21))
        text(42, 24, "Prepared paper edition only. No printing, delivery, reading or enjoyment is inferred.", 9)
        text(516, 40, f"{page_number} / {len(chunks)}", 12)
        pages.append("\n".join(commands).encode("ascii"))
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"", b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>"]
    page_ids = []
    for content in pages:
        page_id = len(objects) + 1
        stream_id = page_id + 1
        page_ids.append(page_id)
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {stream_id} 0 R >>".encode())
        objects.append(b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream")
    objects[1] = f"<< /Type /Pages /Kids [{' '.join(str(key) + ' 0 R' for key in page_ids)}] /Count {len(pages)} >>".encode()
    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(output))
        output.extend(f"{number} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(output), len(pages)


class FamilyEdition:
    def __init__(self, host):
        self.host = host
        self.state = _initial()

    def _enabled(self):
        return self.state["preferences"]["cadence"] != "off" and not self.state["cancelled"]

    def _record(self, actor, action, text):
        self.state["events"].append({"actor": actor, "action": action, "text": text, "edition_revision": self.state["edition_revision"]})
        self.state["events"] = self.state["events"][-100:]
        return text

    def _approved(self, item):
        return (item["submitted"] and item["month"] == self.state["preferences"]["month"]
                and item["approved_version"] == item["version"] and item["approval"] in ("explicit", "standing"))

    def _archive(self, reason):
        s = self.state
        if s["artifact"] is None or any(row["edition_revision"] == s["edition_revision"] for row in s["history"]):
            return
        s["history"].append({"edition_revision": s["edition_revision"], "month": s["preferences"]["month"],
                             "filename": s["artifact"]["filename"], "printed": s["tasks"]["print"]["status"] == "printed",
                             "delivered": s["tasks"]["delivery"]["status"] == "delivered",
                             "print_helper": s["tasks"]["print"]["helper"], "delivery_helper": s["tasks"]["delivery"]["helper"],
                             "reason": reason})
        self.state["history"] = self.state["history"][-40:]

    def _invalidate(self, reason):
        self._archive(reason)
        self.state["edition_revision"] += 1
        self.state["artifact"] = None
        self.state["tasks"] = {"print": _task(), "delivery": _task()}

    def _item(self, identity, actor, version=None):
        item = self.state["items"].get(identity) if type(identity) is str else None
        if item is None or item["owner"] != actor or version is not None and (type(version) is not int or version != item["version"]):
            raise ValueError("Use your own contribution and its current version.")
        return item

    def _content(self):
        s = self.state
        if not self._enabled() or not s["selected"] or s["preferences"]["language"] != "English":
            raise ValueError("An opted-in English edition needs at least one approved selected contribution. Other language preferences need an approved translation.")
        if not all(self._approved(s["items"][key]) for key in s["selected"]):
            raise ValueError("The selected contribution approvals have changed.")
        return [s["items"][key] for key in s["selected"]]

    def _generate(self):
        s = self.state
        items = self._content()
        if s["artifact"] is not None:
            raise ValueError("The current edition file is already prepared.")
        pdf, pages = _pdf_document(items, s["preferences"]["month"], s["preferences"]["type_size"], s["edition_revision"])
        digest = hashlib.sha256(pdf).hexdigest()
        filename = f"family-{s['preferences']['month']}-r{s['edition_revision']}-{digest[:12]}.pdf"
        EDITION_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
        target = EDITION_DIR / filename
        with tempfile.NamedTemporaryFile(dir=EDITION_DIR, prefix=".edition-", suffix=".tmp", delete=False) as file:
            temporary = Path(file.name)
            file.write(pdf)
        temporary.replace(target)
        s["artifact"] = {"filename": filename, "sha256": digest, "edition_revision": s["edition_revision"], "pages": pages,
                         "selected_versions": {key: s["items"][key]["version"] for key in s["selected"]}, "mock_cost_cents": pages * 50}
        return "The current approved family edition PDF is prepared. Printing and delivery remain unreported."

    def current_pdf_path(self, download_name=None):
        s, artifact = self.state, self.state["artifact"]
        if artifact is None or not self._enabled() or download_name is not None and download_name != artifact["filename"]:
            raise ValueError("Only the current permitted family edition is available.")
        items = self._content()
        expected_pdf, _ = _pdf_document(items, s["preferences"]["month"], s["preferences"]["type_size"], s["edition_revision"])
        if hashlib.sha256(expected_pdf).hexdigest() != artifact["sha256"]:
            raise ValueError("The approved edition content no longer matches its prepared file.")
        if artifact["edition_revision"] != s["edition_revision"] or artifact["selected_versions"] != {
                key: s["items"][key]["version"] for key in s["selected"]}:
            raise ValueError("The edition file was superseded by a contribution change.")
        path = EDITION_DIR / artifact["filename"]
        if path.is_symlink() or not path.is_file() or path.parent.resolve() != EDITION_DIR.resolve() or hashlib.sha256(path.read_bytes()).hexdigest() != artifact["sha256"]:
            raise ValueError("The current edition file is missing or changed; no physical completion is established.")
        return path

    def _permitted(self, kind):
        s = self.state
        if not self._enabled() or s["artifact"] is None:
            return False
        p = s["preferences"]
        return p["allow_print_help"] and s["artifact"]["mock_cost_cents"] <= p["budget_cents"] if kind == "print" else p["allow_delivery_help"]

    def _request(self, kind, helper, edition_revision, actor="coordinator"):
        s, task = self.state, self.state["tasks"][kind]
        if helper not in ACTORS or type(edition_revision) is not int or edition_revision != s["edition_revision"] or not self._permitted(kind):
            raise ValueError("The current edition and resident's permission must cover this named request.")
        if task["helper"] == helper and task["edition_revision"] == edition_revision and task["status"] in ("requested", "accepted", "printed", "delivered"):
            return deepcopy(task)
        if task["status"] not in ("not_requested", "declined", "cancelled") or helper in task["attempts"]:
            raise ValueError("This responsibility is already assigned or that helper already responded for this edition.")
        self.current_pdf_path()
        task.update(helper=helper, status="requested", edition_revision=edition_revision,
                    request_id=f"family-{s['preferences']['month']}-r{edition_revision}-{kind}-{helper}")
        task["attempts"].append(helper)
        self._record(actor, "request_" + kind, ACTORS[helper] + " was asked about " + kind + "; no acceptance is assumed.")
        return deepcopy(task)

    def request_print(self, helper, edition_revision):
        return self._request("print", helper, edition_revision)

    def request_delivery(self, helper, edition_revision):
        return self._request("delivery", helper, edition_revision)

    @staticmethod
    def _actor(role, actor_id):
        if role == "resident" and actor_id in (None, "resident"):
            return "resident"
        if role == "family" and actor_id in (None, "alex", "morgan"):
            return actor_id or "alex"
        if role == "coordinator" and actor_id in (None, "coordinator"):
            return "coordinator"
        raise ValueError("Choose a supported named household perspective.")

    def apply(self, action, role, payload=None, actor_id=None):
        actor = self._actor(role, actor_id)
        payload = {} if payload is None else payload
        if type(action) is not str or type(payload) is not dict or actor == "coordinator":
            raise ValueError("Use a supported human family-edition action.")
        s = self.state
        if action == "family_edition_preferences":
            allowed = set(s["preferences"]) - {"recipient"}
            if actor != "resident" or not payload or set(payload) - allowed:
                raise ValueError("The resident controls their paper-edition preferences.")
            p = {**s["preferences"], **payload}
            self._validate_preferences(p)
            if p == s["preferences"]:
                raise ValueError("Those preferences are already recorded.")
            layout_changed = any(p[key] != s["preferences"][key] for key in ("month", "language", "type_size"))
            stopped = p["cadence"] == "off"
            if layout_changed or stopped:
                self._invalidate("Resident changed the edition preference or opted out.")
            if p["month"] != s["preferences"]["month"]:
                s["selected"] = []
            s["preferences"] = p
            s["cancelled"] = stopped
            for kind, task in s["tasks"].items():
                if not self._permitted(kind) and task["status"] in ("requested", "accepted"):
                    task["status"] = "cancelled"
            return self._record(actor, action, "Resident updated the paper-edition preference. No real printing, payment or mailing occurs.")
        if action == "family_edition_sharing":
            if actor not in ACTORS or set(payload) != {"enabled"} or type(payload["enabled"]) is not bool or s["sharing"][actor] == payload["enabled"]:
                raise ValueError("Change your own standing sharing preference for this resident.")
            s["sharing"][actor] = payload["enabled"]
            affected = []
            if not payload["enabled"]:
                for key, item in s["items"].items():
                    if item["owner"] == actor and item["approval"] == "standing":
                        item.update(approved_version=None, approval=None)
                        if key in s["selected"]:
                            affected.append(key)
                if affected:
                    self._invalidate("Contributor withdrew standing sharing for selected items.")
                    s["selected"] = [key for key in s["selected"] if key not in affected]
            return self._record(actor, action, ACTORS[actor] + " updated sharing only for their own contributions to this resident.")
        if action in ("family_edition_contribute", "family_edition_edit", "family_edition_approve", "family_edition_withdraw"):
            keys = {"item_id"} if action == "family_edition_contribute" else {"item_id", "item_version"}
            if action == "family_edition_edit":
                keys |= {"title", "text", "caption"}
            if set(payload) != keys or actor not in ACTORS:
                raise ValueError("Use your own contribution and supported fields.")
            if action != "family_edition_contribute" and type(payload["item_version"]) is not int:
                raise ValueError("Use the exact whole-number contribution version.")
            item = self._item(payload["item_id"], actor, payload.get("item_version"))
            if action == "family_edition_contribute":
                if item["submitted"] and item["month"] == s["preferences"]["month"]:
                    raise ValueError("That current-month contribution is already supplied.")
            elif not item["submitted"] or item["month"] != s["preferences"]["month"]:
                raise ValueError("Contribute your current-month item before editing or approving it.")
            if action == "family_edition_approve":
                if self._approved(item):
                    raise ValueError("This exact contribution is already approved.")
                item.update(approved_version=item["version"], approval="explicit")
            elif action == "family_edition_withdraw":
                if not self._approved(item):
                    raise ValueError("No current approval exists to withdraw.")
                if payload["item_id"] in s["selected"]:
                    self._invalidate("Contributor withdrew a selected item's approval.")
                    s["selected"].remove(payload["item_id"])
                item.update(approved_version=None, approval=None)
            else:
                if action == "family_edition_edit":
                    for key, maximum in (("title", 40), ("text", 180), ("caption", 60)):
                        self._validate_text(payload[key], maximum, allow_empty=key == "caption")
                    if item["kind"] == "note" and payload["caption"]:
                        raise ValueError("The note fixture does not contain a photo caption.")
                    if all(item[key] == payload[key] for key in ("title", "text", "caption")):
                        raise ValueError("That contribution content is unchanged.")
                if payload["item_id"] in s["selected"]:
                    self._invalidate("A selected contribution changed; its previous draft is superseded.")
                    s["selected"].remove(payload["item_id"])
                if action == "family_edition_edit":
                    item.update({key: payload[key] for key in ("title", "text", "caption")})
                item.update(version=item["version"] + 1, submitted=True, month=s["preferences"]["month"],
                            approved_version=None, approval=None)
                if s["sharing"][actor]:
                    item.update(approved_version=item["version"], approval="standing")
            return self._record(actor, action, ACTORS[actor] + " updated their own contribution. Only an approved current version can enter the paper edition.")
        if action == "family_edition_select":
            ids = payload.get("item_ids")
            if (set(payload) != {"item_ids"} or type(ids) is not list or not 1 <= len(ids) <= 4
                    or any(type(key) is not str or key not in s["items"] or not self._approved(s["items"][key]) for key in ids)
                    or len(set(ids)) != len(ids) or ids == s["selected"] or not self._enabled()):
                raise ValueError("Select one to four distinct approved current contributions; a shorter edition is welcome.")
            self._invalidate("Selection changed; earlier unprinted draft superseded.")
            s["selected"] = list(ids)
            return self._record(actor, action, "Selected approved contributions for the resident's paper edition; missing contributions are optional.")
        if action == "family_edition_generate":
            if payload:
                raise ValueError("Generate the current approved selection without extra fields.")
            return self._record(actor, action, self._generate())
        if action in ("family_edition_request_print", "family_edition_request_delivery"):
            if set(payload) != {"helper", "edition_revision"}:
                raise ValueError("Request a named responsibility within the resident's current permission.")
            self._request("print" if action.endswith("print") else "delivery", payload["helper"], payload["edition_revision"], actor)
            return "Named responsibility requested; a human reply and physical report are still required."
        if action == "family_edition_cancel":
            if payload or actor != "resident" or s["cancelled"]:
                raise ValueError("The resident can cancel the current edition once.")
            self._invalidate("Resident cancelled this edition; previous physical reports retained in history.")
            s["cancelled"] = True
            return self._record(actor, action, "Edition cancelled; no further printing or delivery can be reported for its old revision.")
        match = re.fullmatch(r"family_edition_(print|delivery)_(accept|decline|report)", action)
        if match is None or actor not in ACTORS or set(payload) != {"edition_revision"} or type(payload["edition_revision"]) is not int:
            raise ValueError("Use an available named family-edition control.")
        kind, operation = match.groups()
        task = s["tasks"][kind]
        if (task["helper"] != actor or task["edition_revision"] != payload["edition_revision"] or payload["edition_revision"] != s["edition_revision"]
                or not self._permitted(kind) or task["status"] != ("accepted" if operation == "report" else "requested")):
            raise ValueError("Only the named helper can answer or report their current permitted responsibility.")
        self.current_pdf_path()
        if operation == "report" and kind == "delivery" and s["tasks"]["print"]["status"] != "printed":
            raise ValueError("Delivery needs a separate current-edition printed report first.")
        task["status"] = {"accept": "accepted", "decline": "declined", "report": "printed" if kind == "print" else "delivered"}[operation]
        return self._record(actor, action, ACTORS[actor] + " reports " + task["status"] + " for " + kind + ". File generation, printing and delivery remain distinct.")

    def view(self, role, actor_id=None):
        actor = self._actor(role, actor_id)
        s, controls = self.state, []
        def button(action, label, payload=None):
            controls.append({"action": action, "label": label, **({"payload": payload} if payload is not None else {})})
        if actor in ACTORS:
            for key, item in s["items"].items():
                if item["owner"] != actor:
                    continue
                if not item["submitted"] or item["month"] != s["preferences"]["month"]:
                    button("family_edition_contribute", "Contribute my fictional " + item["title"], {"item_id": key})
                elif not self._approved(item):
                    button("family_edition_approve", "Approve my " + item["title"] + " for the resident", {"item_id": key, "item_version": item["version"]})
                else:
                    button("family_edition_withdraw", "Withdraw my " + item["title"], {"item_id": key, "item_version": item["version"]})
            button("family_edition_sharing", "Stop standing sharing" if s["sharing"][actor] else "Share my future contributions with this resident",
                   {"enabled": not s["sharing"][actor]})
            for kind, task in s["tasks"].items():
                if task["helper"] == actor and self._permitted(kind):
                    if task["status"] == "requested":
                        for operation in ("accept", "decline"):
                            button(f"family_edition_{kind}_{operation}", operation.title() + " my " + kind + " responsibility", {"edition_revision": s["edition_revision"]})
                    elif task["status"] == "accepted" and (kind == "print" or s["tasks"]["print"]["status"] == "printed"):
                        button(f"family_edition_{kind}_report", "Report " + ("printed" if kind == "print" else "delivered"), {"edition_revision": s["edition_revision"]})
        if actor != "coordinator" and self._enabled() and s["selected"] and s["artifact"] is None and s["preferences"]["language"] == "English":
            button("family_edition_generate", "Prepare the approved paper edition")
        if actor == "resident":
            if not s["cancelled"]:
                button("family_edition_cancel", "Cancel this edition")
        if actor != "coordinator":
            for kind, task in s["tasks"].items():
                if self._permitted(kind) and task["status"] in ("not_requested", "declined", "cancelled"):
                    for helper in ACTORS:
                        if helper not in task["attempts"]:
                            button("family_edition_request_" + kind, "Ask " + ACTORS[helper] + " about " + kind,
                                   {"helper": helper, "edition_revision": s["edition_revision"]})
        visible = {key: deepcopy(item) for key, item in s["items"].items() if item["owner"] == actor or self._approved(item)}
        artifact = deepcopy(s["artifact"])
        if artifact:
            artifact["download_url"] = "/api/family-edition/pdf/" + artifact["filename"]
        unresolved = []
        if s["preferences"]["language"] != "English":
            unresolved.append("This language preference needs an explicitly approved translation; the local renderer supports English fixtures only.")
        if not s["selected"]:
            unresolved.append("No approved contributions selected; relatives are not required to fill a quota.")
        if s["artifact"] and s["tasks"]["print"]["status"] != "printed" and not self._permitted("print"):
            unresolved.append("Named printing needs permission and the authored mock cost within the resident's allowance.")
        return {"edition_revision": s["edition_revision"], "enabled": self._enabled(), "cancelled": s["cancelled"],
                "preferences": deepcopy(s["preferences"]), "standing_sharing": s["sharing"].get(actor), "items": visible,
                "selected": list(s["selected"]), "artifact": artifact, "tasks": deepcopy(s["tasks"]), "controls": controls,
                "history": deepcopy(s["history"]), "events": deepcopy(s["events"]), "unresolved": unresolved,
                "notice": "Fictional family news to the resident, not a care report. Photos are labeled authored placeholders. "
                          "No private messages or photos are retrieved; no real printer, purchase, mailing or scheduler runs.",
                "mock_print_price": {"cents_per_page": 50, "source": "Authored simulation fixture; not a real printing quote."}}

    def context(self):
        return self.view("coordinator")

    def dump(self):
        return deepcopy(self.state)

    @staticmethod
    def _validate_text(value, maximum, allow_empty=False):
        if type(value) is not str or not (0 if allow_empty else 1) <= len(value) <= maximum or (not allow_empty and not value.strip()) or any(ord(ch) < 32 or ord(ch) > 126 for ch in value):
            raise ValueError("Use bounded printable English fixture text for this local edition.")

    @staticmethod
    def _validate_preferences(p):
        if (type(p) is not dict or set(p) != set(_initial()["preferences"]) or p["recipient"] != "resident"
                or p["cadence"] not in ("off", "monthly", "on_request") or p["language"] not in ("English", "Spanish", "Other")
                or type(p["type_size"]) is not int or p["type_size"] not in (18, 20)
                or type(p["allow_print_help"]) is not bool or type(p["allow_delivery_help"]) is not bool
                or type(p["budget_cents"]) is not int or not 0 <= p["budget_cents"] <= 5000
                or type(p["month"]) is not str or re.fullmatch(r"20[0-9]{2}-(0[1-9]|1[0-2])", p["month"]) is None):
            raise ValueError("Use supported paper-edition preferences and a bounded fictional allowance.")

    @classmethod
    def restore(cls, host, data):
        edition = cls(host)
        edition._validate(data)
        edition.state = deepcopy(data)
        return edition

    @classmethod
    def _validate(cls, s):
        def bad():
            raise ValueError("Saved family edition is malformed or inconsistent.")
        if type(s) is not dict or set(s) != set(_initial()):
            bad()
        cls._validate_preferences(s["preferences"])
        if (type(s["schema"]) is not int or s["schema"] != 1 or type(s["edition_revision"]) is not int or not 1 <= s["edition_revision"] <= 100000
                or type(s["cancelled"]) is not bool or type(s["sharing"]) is not dict or set(s["sharing"]) != set(ACTORS)
                or any(type(value) is not bool for value in s["sharing"].values()) or type(s["items"]) is not dict or set(s["items"]) != set(FIXTURES)
                or type(s["selected"]) is not list or len(s["selected"]) > 4 or any(type(key) is not str or key not in FIXTURES for key in s["selected"])
                or len(set(s["selected"])) != len(s["selected"])):
            bad()
        for key, item in s["items"].items():
            if type(item) is not dict or set(item) != set(_initial()["items"][key]):
                bad()
            for field in ("owner", "kind", "plan", "photo_label"):
                if item[field] != FIXTURES[key][field]:
                    bad()
            for field, maximum in (("title", 40), ("text", 180), ("caption", 60)):
                cls._validate_text(item[field], maximum, allow_empty=field == "caption")
            if (type(item["version"]) is not int or not 0 <= item["version"] <= 100000 or type(item["submitted"]) is not bool
                    or item["submitted"] != (item["version"] > 0) or type(item["month"]) is not str
                    or re.fullmatch(r"20[0-9]{2}-(0[1-9]|1[0-2])", item["month"]) is None
                    or item["approval"] not in (None, "explicit", "standing")
                    or (item["approved_version"] is None) != (item["approval"] is None)
                    or item["approved_version"] is not None and (type(item["approved_version"]) is not int or item["approved_version"] != item["version"] or not item["submitted"])
                    or item["approval"] == "standing" and not s["sharing"][item["owner"]]):
                bad()
            if key in s["selected"] and (item["approved_version"] != item["version"] or not item["submitted"] or item["month"] != s["preferences"]["month"]):
                bad()
        a = s["artifact"]
        if a is not None:
            if (type(a) is not dict or set(a) != {"filename", "sha256", "edition_revision", "pages", "selected_versions", "mock_cost_cents"}
                    or type(a["sha256"]) is not str or re.fullmatch(r"[a-f0-9]{64}", a["sha256"]) is None
                    or a["filename"] != f"family-{s['preferences']['month']}-r{s['edition_revision']}-{a['sha256'][:12]}.pdf"
                    or type(a["edition_revision"]) is not int or a["edition_revision"] != s["edition_revision"]
                    or type(a["pages"]) is not int or not 1 <= a["pages"] <= 2
                    or type(a["mock_cost_cents"]) is not int or a["mock_cost_cents"] != a["pages"] * 50
                    or type(a["selected_versions"]) is not dict or any(type(value) is not int for value in a["selected_versions"].values())
                    or a["selected_versions"] != {key: s["items"][key]["version"] for key in s["selected"]}
                    or s["cancelled"] or s["preferences"]["cadence"] == "off" or s["preferences"]["language"] != "English"):
                bad()
            expected, pages = _pdf_document([s["items"][key] for key in s["selected"]], s["preferences"]["month"], s["preferences"]["type_size"], s["edition_revision"])
            if pages != a["pages"] or hashlib.sha256(expected).hexdigest() != a["sha256"]:
                bad()
        if type(s["tasks"]) is not dict or set(s["tasks"]) != {"print", "delivery"}:
            bad()
        for kind, task in s["tasks"].items():
            if (type(task) is not dict or set(task) != set(_task()) or task["helper"] not in (None, "alex", "morgan")
                    or task["status"] not in ("not_requested", "requested", "accepted", "declined", "cancelled", "printed" if kind == "print" else "delivered")
                    or type(task["edition_revision"]) is not int or type(task["attempts"]) is not list
                    or any(type(helper) is not str or helper not in ACTORS for helper in task["attempts"]) or len(task["attempts"]) != len(set(task["attempts"]))):
                bad()
            if task["status"] == "not_requested":
                if task != _task():
                    bad()
            elif (a is None or task["helper"] not in ACTORS or task["edition_revision"] != s["edition_revision"]
                  or task["helper"] not in task["attempts"] or task["request_id"] != f"family-{s['preferences']['month']}-r{s['edition_revision']}-{kind}-{task['helper']}"):
                bad()
            if task["status"] in ("requested", "accepted"):
                permitted = (s["preferences"]["allow_print_help"] and a["mock_cost_cents"] <= s["preferences"]["budget_cents"]) if kind == "print" else s["preferences"]["allow_delivery_help"]
                if not permitted:
                    bad()
        if s["tasks"]["delivery"]["status"] == "delivered" and s["tasks"]["print"]["status"] != "printed":
            bad()
        if type(s["history"]) is not list or len(s["history"]) > 40 or type(s["events"]) is not list or len(s["events"]) > 100:
            bad()
        seen = set()
        for row in s["history"]:
            if (type(row) is not dict or set(row) != {"edition_revision", "month", "filename", "printed", "delivered", "print_helper", "delivery_helper", "reason"}
                    or type(row["edition_revision"]) is not int or not 1 <= row["edition_revision"] < s["edition_revision"] or row["edition_revision"] in seen
                    or type(row["printed"]) is not bool or type(row["delivered"]) is not bool or row["delivered"] and not row["printed"]
                    or row["print_helper"] not in (None, "alex", "morgan") or row["delivery_helper"] not in (None, "alex", "morgan")
                    or row["printed"] and row["print_helper"] is None or row["delivered"] and row["delivery_helper"] is None
                    or type(row["month"]) is not str or type(row["filename"]) is not str or re.fullmatch(r"family-20[0-9]{2}-(0[1-9]|1[0-2])-r[0-9]+-[a-f0-9]{12}\.pdf", row["filename"]) is None
                    or type(row["reason"]) is not str or len(row["reason"]) > 300):
                bad()
            seen.add(row["edition_revision"])
        for event in s["events"]:
            if (type(event) is not dict or set(event) != {"actor", "action", "text", "edition_revision"} or event["actor"] not in ("resident", "alex", "morgan", "coordinator")
                    or type(event["action"]) is not str or len(event["action"]) > 80 or type(event["text"]) is not str or len(event["text"]) > 400
                    or type(event["edition_revision"]) is not int or not 1 <= event["edition_revision"] <= s["edition_revision"]):
                bad()
