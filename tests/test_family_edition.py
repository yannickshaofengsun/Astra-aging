"""Local paper-edition approval, revision and physical-report acceptance checks."""

from copy import deepcopy
from pathlib import Path
import tempfile
from types import SimpleNamespace
from careanchor import family_edition as module
from careanchor.family_edition import FamilyEdition, FIXTURES


def act(edition, action, actor="resident", **payload):
    return edition.apply("family_edition_" + action, "resident" if actor == "resident" else "family", payload, actor)


def reject(edition, action, actor="resident", **payload):
    before = edition.dump()
    try:
        act(edition, action, actor, **payload)
    except ValueError:
        assert edition.dump() == before, "Rejected edition action changed state"
    else:
        raise AssertionError("Unexpected accepted edition action: " + action)


def fixture():
    edition = FamilyEdition(SimpleNamespace())
    act(edition, "preferences", cadence="monthly", allow_print_help=True, allow_delivery_help=True)
    return edition


def contribute(edition, key, approve=True):
    actor = FIXTURES[key]["owner"]
    act(edition, "contribute", actor, item_id=key)
    if approve:
        act(edition, "approve", actor, item_id=key, item_version=edition.state["items"][key]["version"])


def generate(edition, ids):
    act(edition, "select", "alex", item_ids=ids)
    act(edition, "generate", "alex")
    return edition.current_pdf_path()


def test_subset_own_approval_and_pdf():
    edition = fixture()
    assert edition.view("resident", "resident")["items"] == {}
    assert edition.context()["items"] == {}
    contribute(edition, "alex_tomatoes", approve=False)
    reject(edition, "approve", "morgan", item_id="alex_tomatoes", item_version=1)
    reject(edition, "approve", "alex", item_id="alex_tomatoes", item_version=None)
    reject(edition, "approve", "alex", item_id="alex_tomatoes", item_version=True)
    reject(edition, "select", item_ids=["alex_tomatoes"])
    assert edition.context()["items"] == {}
    act(edition, "approve", "alex", item_id="alex_tomatoes", item_version=1)
    contribute(edition, "morgan_bread", approve=False)  # explicitly supplied, unshared content must stay out
    path = generate(edition, ["alex_tomatoes"])
    data = path.read_bytes()
    assert data.startswith(b"%PDF-1.4") and b"tomatoes" in data and b"recipe" not in data and b"bread" not in data
    assert b"Fictional" in data and b"/Count 1" in data
    assert "morgan_bread" not in edition.view("family", "alex")["items"]
    assert edition.state["tasks"]["print"]["status"] == "not_requested"
    assert edition.state["tasks"]["delivery"]["status"] == "not_requested"
    reject(edition, "generate", "alex")
    reject(edition, "print_report", "alex", edition_revision=edition.state["edition_revision"])
    assert FamilyEdition.restore(edition.host, edition.dump()).dump() == edition.dump()


def test_stale_caption_and_standing_sharing():
    edition = fixture()
    act(edition, "sharing", "alex", enabled=True)
    act(edition, "contribute", "alex", item_id="alex_tomatoes")
    assert edition.state["items"]["alex_tomatoes"]["approval"] == "standing"
    contribute(edition, "morgan_bread")
    old = generate(edition, ["alex_tomatoes", "morgan_bread"])
    version = edition.state["edition_revision"]
    act(edition, "request_print", helper="alex", edition_revision=version)
    act(edition, "print_accept", "alex", edition_revision=version)
    item = deepcopy(edition.state["items"]["alex_tomatoes"])
    act(edition, "edit", "alex", item_id="alex_tomatoes", item_version=item["version"],
        title=item["title"], text=item["text"], caption="Corrected fictional caption: six tomatoes on the balcony.")
    assert edition.state["artifact"] is None and edition.state["selected"] == ["morgan_bread"]
    assert edition.state["items"]["morgan_bread"]["approval"] == "explicit"
    assert edition.state["items"]["alex_tomatoes"]["approval"] == "standing"
    reject(edition, "print_report", "alex", edition_revision=version)
    reject(edition, "approve", "alex", item_id="alex_tomatoes", item_version=item["version"])
    try:
        edition.current_pdf_path(old.name)
    except ValueError:
        pass
    else:
        raise AssertionError("Superseded PDF remained available")
    current = generate(edition, ["alex_tomatoes", "morgan_bread"])
    assert current != old
    act(edition, "sharing", "alex", enabled=False)
    assert edition.state["artifact"] is None and edition.state["selected"] == ["morgan_bread"]
    assert edition.state["items"]["morgan_bread"]["approved_version"] == 1
    assert edition.state["items"]["alex_tomatoes"]["approved_version"] is None
    # Revoking standing sharing does not revoke the other contributor's approval.
    act(edition, "generate", "morgan")
    assert b"Corrected" not in edition.current_pdf_path().read_bytes()


def test_print_refusal_permissions_and_delivery():
    edition = fixture()
    contribute(edition, "morgan_visit")
    generate(edition, ["morgan_visit"])
    revision = edition.state["edition_revision"]
    act(edition, "request_print", "morgan", helper="alex", edition_revision=revision)
    assert edition.state["events"][-1]["actor"] == "morgan"
    before = edition.dump()
    edition.request_print("alex", revision)
    assert edition.dump() == before
    reject(edition, "print_accept", "morgan", edition_revision=revision)
    act(edition, "print_decline", "alex", edition_revision=revision)
    reject(edition, "request_print", helper="alex", edition_revision=revision)
    act(edition, "request_print", helper="morgan", edition_revision=revision)
    act(edition, "print_accept", "morgan", edition_revision=revision)
    act(edition, "request_delivery", helper="alex", edition_revision=revision)
    act(edition, "delivery_accept", "alex", edition_revision=revision)
    reject(edition, "delivery_report", "alex", edition_revision=revision)
    assert edition.state["tasks"]["print"]["status"] == "accepted"
    act(edition, "print_report", "morgan", edition_revision=revision)
    reject(edition, "print_report", "morgan", edition_revision=revision)
    act(edition, "delivery_report", "alex", edition_revision=revision)
    reject(edition, "delivery_report", "alex", edition_revision=revision)
    restored = FamilyEdition.restore(edition.host, edition.dump())
    assert restored.dump() == edition.dump()
    act(edition, "preferences", cadence="off")
    assert edition.state["history"][-1]["printed"] and edition.state["history"][-1]["delivered"]
    assert edition.state["artifact"] is None
    reject(edition, "request_print", helper="alex", edition_revision=revision)
    assert FamilyEdition.restore(edition.host, edition.dump()).dump() == edition.dump()
    edition = fixture()
    contribute(edition, "alex_tomatoes")
    generate(edition, ["alex_tomatoes"])
    revision = edition.state["edition_revision"]
    act(edition, "request_print", helper="alex", edition_revision=revision)
    act(edition, "print_accept", "alex", edition_revision=revision)
    act(edition, "preferences", allow_print_help=False)
    reject(edition, "print_report", "alex", edition_revision=revision)
    assert edition.state["tasks"]["print"]["status"] == "cancelled"
    assert FamilyEdition.restore(edition.host, edition.dump()).dump() == edition.dump()


def test_budget_language_cancel_and_malformed_save():
    edition = fixture()
    contribute(edition, "alex_tomatoes")
    generate(edition, ["alex_tomatoes"])
    act(edition, "preferences", budget_cents=49)
    reject(edition, "request_print", helper="alex", edition_revision=edition.state["edition_revision"])
    act(edition, "preferences", language="Spanish")
    reject(edition, "generate", "alex")
    assert edition.state["artifact"] is None
    act(edition, "preferences", language="English")
    act(edition, "generate", "alex")
    saved = edition.dump()
    corruptions = (lambda s: s.update(extra=1), lambda s: s.update(edition_revision=True),
                   lambda s: s["artifact"].update(filename="../../private.pdf"),
                   lambda s: s["items"]["alex_tomatoes"].update(approved_version=99),
                   lambda s: s["items"]["alex_tomatoes"].update(owner="morgan"),
                   lambda s: s["items"]["alex_tomatoes"].update(text="A replacement that was never in the prepared PDF."),
                   lambda s: s["artifact"]["selected_versions"].update(alex_tomatoes=True),
                   lambda s: s["tasks"]["delivery"].update(status="delivered"))
    for mutate in corruptions:
        bad = deepcopy(saved)
        mutate(bad)
        try:
            FamilyEdition.restore(edition.host, bad)
        except ValueError:
            pass
        else:
            raise AssertionError("Malformed edition snapshot accepted")
    assert edition.dump() == saved
    name = edition.state["artifact"]["filename"]
    act(edition, "cancel")
    reject(edition, "generate", "alex")
    try:
        edition.current_pdf_path(name)
    except ValueError:
        pass
    else:
        raise AssertionError("Cancelled PDF remained available")


def run():
    old_dir = module.EDITION_DIR
    with tempfile.TemporaryDirectory(prefix="family-edition-test-") as directory:
        module.EDITION_DIR = Path(directory)
        try:
            for test in (test_subset_own_approval_and_pdf, test_stale_caption_and_standing_sharing,
                         test_print_refusal_permissions_and_delivery, test_budget_language_cancel_and_malformed_save):
                test()
        finally:
            module.EDITION_DIR = old_dir
    print("Family edition acceptance passed: own approvals, shorter private-safe PDF, sharing/revisions, separate fulfillment, refusal/cancel/permission guards and restore.")


if __name__ == "__main__":
    run()
