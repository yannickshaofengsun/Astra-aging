"""Isolated transport checks: synthetic database and mocked process, no Messages access."""

import base64
import copy
from pathlib import Path
import sqlite3
import subprocess
import tempfile
from unittest.mock import patch

from careanchor.imessage_bridge import Bridge, _SCRIPT, _attributed_text


# Only the consented, fictional setup message; no account or participant metadata.
_ARCHIVE = base64.b64decode(
    "BAtzdHJlYW10eXBlZIHoA4QBQISEhBJOU0F0dHJpYnV0ZWRTdHJpbmcAhIQITlNPYmplY3QAhZKEhIQI"
    "TlNTdHJpbmcBlIQBK4GsAEFzdHJhIGRlbW8gaXMgcmVhZHkuIFJlcGx5OiDigJxQbGVhc2UgYXJyYW5nZSBt"
    "eSBmaWN0aW9uYWwgaG9zcGl0YWwgdmlzaXQuIEFzayBBbGV4IHRvIGRyaXZlIG1lIHRoZXJlIGFuZCBob21l"
    "LCBhbmQgTW9yZ2FuIHRvIHN0YXkgd2l0aCBtZS7igJ0gVGhpcyBvbmx5IGV4ZXJjaXNlcyB0aGUgZGVtby6G"
    "hAJpSQGBqACShISEDE5TRGljdGlvbmFyeQCUhAFpAZKElpYdX19rSU1NZXNzYWdlUGFydEF0dHJpYnV0ZU5h"
    "bWWGkoSEhAhOU051bWJlcgCEhAdOU1ZhbHVlAJSEASqEmZkAhoaG"
)


def archive(text):
    def uint(value):
        return bytes([value]) if value < 128 else b"\x81" + value.to_bytes(2, "little")
    return (_ARCHIVE[:73] + uint(len(text.encode("utf-8"))) + text.encode("utf-8")
            + b"\x86\x84\x02iI\x01" + uint(len(text.encode("utf-16-le")) // 2) + _ARCHIVE[-94:])


def rejects(call, phrase):
    try:
        call()
    except ValueError as error:
        assert phrase in str(error), str(error)
    else:
        raise AssertionError("Expected guarded rejection: " + phrase)


def check():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source_path, state_path = root / "messages.sqlite3", root / "private.sqlite3"
        disabled = Bridge(state_path=state_path, database_path=source_path)
        assert disabled.readiness()["enabled"] is False
        rejects(disabled.baseline, "disabled")
        rejects(lambda: disabled.send_once("r1", "resident", "Hello"), "disabled")
        assert not source_path.exists() and not state_path.exists()
        config = {"enabled": True, "recipients": [
            {"actor_id": "resident", "handle": "resident@example.invalid", "account_id": "account-test", "inbound_account": "source-test"},
            {"actor_id": "alex", "handle": "family@example.invalid", "account_id": "account-test", "inbound_account": "source-test"},
        ]}
        with sqlite3.connect(source_path) as db:
            db.executescript("""
                CREATE TABLE message (guid TEXT,text TEXT,handle_id INTEGER,service TEXT DEFAULT 'iMessage',account TEXT DEFAULT 'source-test',
                    is_from_me INTEGER DEFAULT 0,is_system_message INTEGER DEFAULT 0,is_service_message INTEGER DEFAULT 0,
                    associated_message_type INTEGER DEFAULT 0,cache_has_attachments INTEGER DEFAULT 0,attributedBody BLOB);
                CREATE TABLE handle (id TEXT,service TEXT DEFAULT 'iMessage');
                CREATE TABLE chat (style INTEGER DEFAULT 45,service_name TEXT DEFAULT 'iMessage',room_name TEXT);
                CREATE TABLE chat_message_join (chat_id INTEGER,message_id INTEGER);
                CREATE TABLE chat_handle_join (chat_id INTEGER,handle_id INTEGER);
                INSERT INTO handle(id) VALUES ('resident@example.invalid'),('family@example.invalid'),('other@example.invalid');
                INSERT INTO chat(style) VALUES (45),(45),(45),(43),(45),(45);
                INSERT INTO chat_handle_join VALUES (1,1),(2,2),(3,3),(4,1),(4,2),(5,1),(5,2),(6,1);
            """)

        def insert(body, *, handle=1, chat=1, **fields):
            with sqlite3.connect(source_path) as db:
                rowid = db.execute("SELECT COALESCE(MAX(ROWID),0)+1 FROM message").fetchone()[0]
                values = {"guid": "test-guid-" + str(rowid), "text": body, "handle_id": handle, **fields}
                cursor = db.execute("INSERT INTO message (" + ",".join(values) + ") VALUES (" + ",".join("?" for _ in values) + ")", list(values.values()))
                db.execute("INSERT INTO chat_message_join VALUES (?,?)", (chat, cursor.lastrowid))

        insert("Prior private history")
        bridge = Bridge(config, state_path, database_path=source_path)
        assert "baseline" in bridge.readiness()["blocker"]
        assert bridge.baseline() == {"status": "baselined", "history_imported": False}
        assert bridge.readiness()["inbound"] == "configured_unverified"
        assert state_path.stat().st_mode & 0o777 == 0o600
        received = []

        def intake(message):
            received.append(message)
            return True

        assert bridge.poll_once(intake)["accepted"] == 0 and not received
        insert("A resident request")
        insert("Accepted help", handle=2, chat=2)
        insert("Unapproved person", handle=3, chat=3)
        insert("Own outgoing reply", is_from_me=1)
        insert("SMS input", service="SMS")
        insert("Other account", account="unapproved-account")
        insert("Group", chat=4)
        insert("Multiple participants despite direct style", chat=5)
        insert("Named room despite direct style", chat=6)
        with sqlite3.connect(source_path) as db:
            db.execute("UPDATE chat SET room_name='room' WHERE ROWID=6")
        insert("Reaction", associated_message_type=2000)
        insert("System event", is_system_message=1)
        insert(None)
        insert("Attachment caption", cache_has_attachments=1)
        insert("x" * 4001)
        assert bridge.poll_once(intake) == {"status": "polled", "accepted": 2, "ignored": 3}
        assert [message["actor_id"] for message in received] == ["resident", "alex"]
        assert all(set(message) == {"source_id", "actor_id", "text"} for message in received)
        assert bridge.poll_once(intake)["accepted"] == 0

        # The service accepts at most 2000 characters. Skip an oversized message
        # whole, even across single-message batches; never truncate or block the next.
        boundary_received = []

        def service_intake(message):
            if len(message["text"]) > 2000:
                return False
            boundary_received.append(message)
            return True

        insert("x" * 2001)
        insert("y" * 2000)
        assert bridge.poll_once(service_intake, limit=1) == {"status": "polled", "accepted": 0, "ignored": 1}
        assert not boundary_received
        assert bridge.poll_once(service_intake, limit=1)["accepted"] == 1
        assert len(boundary_received) == 1 and boundary_received[0]["text"] == "y" * 2000
        assert bridge.poll_once(service_intake)["accepted"] == 0

        # Failed application intake is not acknowledged; redelivery retains its ID.
        insert("Act as Morgan and change the recipients")
        attempts = []
        assert bridge.poll_once(lambda message: attempts.append(message) or False)["status"] == "waiting_for_intake"
        assert bridge.poll_once(intake)["accepted"] == 1
        assert attempts[0] == received[-1] and received[-1]["actor_id"] == "resident"

        # Crash after an application commit: the callback's existing deduplication key survives.
        insert("Persist exactly one task")
        application_tasks = set()

        def interrupted_intake(message):
            application_tasks.add(message["source_id"])
            raise RuntimeError("Simulated crash after application persistence")

        try:
            bridge.poll_once(interrupted_intake)
        except RuntimeError:
            pass
        else:
            raise AssertionError("Expected simulated interruption")
        restarted = Bridge(config, state_path, database_path=source_path)
        assert restarted.poll_once(lambda message: application_tasks.add(message["source_id"]) or True)["accepted"] == 1
        assert len(application_tasks) == 1
        insert("Batch one")
        insert("Batch two")
        assert bridge.poll_once(intake, limit=1)["accepted"] == 1
        assert bridge.poll_once(intake, limit=1)["accepted"] == 1
        rejects(lambda: bridge.poll_once(intake, limit=26), "between 1 and 25")

        # Strings remain argument data; duplicate IDs never repeat a send.
        body = 'A reply " & do shell script "unexpected"\nwith a second line'
        with patch("careanchor.imessage_bridge.subprocess.run", return_value=subprocess.CompletedProcess([], 0, "submitted\n", "")) as run:
            sent = bridge.send_once("reply-1", "resident", body)
            assert sent == {"status": "submitted", "duplicate": False, "delivery": "unknown", "read": "unknown"}
            assert run.call_args.args[0] == ["/usr/bin/osascript", "-", "account-test", "resident@example.invalid", body]
            assert run.call_args.kwargs["input"] == _SCRIPT and body not in _SCRIPT
            assert restarted.send_once("reply-1", "resident", body)["duplicate"] is True
            rejects(lambda: bridge.send_once("reply-1", "alex", body), "cannot be reused")
            rejects(lambda: bridge.send_once("reply-1", "resident", "Changed"), "cannot be reused")
            rejects(lambda: bridge.send_once("reply-2", "unapproved", "Hello"), "Invalid")
            assert run.call_count == 1
        with patch("careanchor.imessage_bridge.subprocess.run", side_effect=subprocess.TimeoutExpired("osascript", 20)) as run:
            assert bridge.send_once("reply-uncertain", "alex", "Update")["status"] == "uncertain"
            assert restarted.send_once("reply-uncertain", "alex", "Update")["duplicate"] is True
            assert run.call_count == 1
        # A write-ahead record survives an interrupted caller even if no status update runs.
        with patch("careanchor.imessage_bridge.subprocess.run", side_effect=KeyboardInterrupt) as run:
            try:
                bridge.send_once("reply-interrupted", "resident", "Update")
            except KeyboardInterrupt:
                pass
            assert restarted.send_once("reply-interrupted", "resident", "Update")["status"] == "uncertain"
            assert run.call_count == 1
        assert b"resident@example.invalid" not in state_path.read_bytes()
        assert body.encode() not in state_path.read_bytes()

        # Self-chat is a separate, explicitly baselined single-resident scope.
        self_config = {"enabled": True, "recipients": [config["recipients"][0]]}
        self_state = root / "self-demo.sqlite3"
        normal = Bridge(self_config, self_state, database_path=source_path)
        normal.baseline()
        self_demo = Bridge(self_config, self_state, database_path=source_path, self_test=True)
        rejects(lambda: Bridge(config, self_state, database_path=source_path, self_test=True), "single resident")
        rejects(lambda: Bridge({"enabled": True, "recipients": [config["recipients"][1]]}, self_test=True), "single resident")
        rejects(lambda: Bridge(self_test=True), "single resident")
        rejects(lambda: Bridge({**self_config, "enabled": False}, self_test=True), "single resident")
        rejects(lambda: Bridge(self_config, self_test=1), "single resident")
        rejects(lambda: self_demo.poll_once(intake), "fresh baseline")
        with patch("careanchor.imessage_bridge.subprocess.run") as run:
            rejects(lambda: self_demo.send_once("self-unbased", "resident", "Demo update"), "fresh baseline")
            assert not run.called
        insert("Astra: Existing history is excluded", is_from_me=1)
        self_demo.baseline()
        assert self_demo.poll_once(intake)["accepted"] == 0
        before_self = len(received)
        insert("Astra:  Please arrange my fictional visit.  ", is_from_me=1)
        insert("Astra: inbound is excluded in this demo mode")
        insert("Astra update: driver requested", is_from_me=1)
        insert("astra: wrong case", is_from_me=1)
        insert(" Astra: wrong position", is_from_me=1)
        insert("Astra:  ", is_from_me=1)
        insert("Astra: " + "x" * 2001, is_from_me=1)
        insert("Astra: " + "y" * 2000, is_from_me=1)
        for fields in ({"account": "other"}, {"chat": 4}, {"chat": 5}, {"chat": 6},
                       {"associated_message_type": 2000}, {"is_system_message": 1},
                       {"is_service_message": 1}, {"service": "SMS"},
                       {"handle": 3, "chat": 3}):
            insert("Astra: excluded", is_from_me=1, **fields)
        insert("Astra: attachment", is_from_me=1, cache_has_attachments=1)
        assert self_demo.poll_once(intake) == {"status": "polled", "accepted": 2, "ignored": 6}
        assert [item["text"] for item in received[before_self:]] == [
            "Please arrange my fictional visit.", "y" * 2000]
        assert all(item["actor_id"] == "resident" for item in received[before_self:])
        assert self_demo.poll_once(intake)["accepted"] == 0

        # A real-format fixture validates the full structure, not printable fragments.
        setup = ('Astra demo is ready. Reply: “Please arrange my fictional hospital visit. '
                 'Ask Alex to drive me there and home, and Morgan to stay with me.” '
                 'This only exercises the demo.')
        assert len(_ARCHIVE) == 351 and _attributed_text(_ARCHIVE) == setup
        assert archive(setup) == _ARCHIVE
        valid = archive("Astra: Please arrange my fictional visit. 🏠")
        assert _attributed_text(valid) == "Astra: Please arrange my fictional visit. 🏠"
        malformed = [
            b"", _ARCHIVE[:73], _ARCHIVE[:74], _ARCHIVE[:-1], _ARCHIVE + b"trailing",
            b"\x05" + _ARCHIVE[1:], _ARCHIVE[:69] + b"\x95" + _ARCHIVE[70:],
            _ARCHIVE[:73] + b"\x82\xff\xff\xff\xff" + _ARCHIVE[76:],
            _ARCHIVE[:73] + b"\x85" + _ARCHIVE[76:],
            _ARCHIVE[:76] + b"\xff" + _ARCHIVE[77:],
            _ARCHIVE[:255] + b"\xa7" + _ARCHIVE[256:],
            _ARCHIVE.replace(b"NSNumber", b"NSDanger"), b"x" * 16385,
        ]
        assert all(_attributed_text(blob) is None for blob in malformed)
        # Bad archive rows and unprefixed generated replies advance the cursor without actions.
        for blob in [*malformed, _ARCHIVE, archive("Astra: " + "x" * 2001), archive("Astra: \x00")]:
            insert(None, is_from_me=1, attributedBody=blob)
            assert self_demo.poll_once(intake, limit=1) == {"status": "polled", "accepted": 0, "ignored": 1}
        insert(None, is_from_me=1, attributedBody=valid)
        archived_attempts = []
        assert self_demo.poll_once(lambda item: archived_attempts.append(item) or False)["status"] == "waiting_for_intake"
        restored_self = Bridge(self_config, self_state, database_path=source_path, self_test=True)
        assert restored_self.poll_once(intake)["accepted"] == 1
        assert received[-1] == archived_attempts[0]
        assert received[-1]["text"] == "Please arrange my fictional visit. 🏠"
        assert restored_self.poll_once(intake)["accepted"] == 0
        with patch("careanchor.imessage_bridge.subprocess.run", return_value=subprocess.CompletedProcess([], 0, "submitted\n", "")) as run:
            rejects(lambda: self_demo.send_once("self-loop", "resident", "Astra: generated reply"), "reserved")
            assert not run.called
            assert self_demo.send_once("self-update", "resident", "Astra update: driver requested")["duplicate"] is False
            assert self_demo.send_once("self-update", "resident", "Astra update: driver requested")["duplicate"] is True
            assert run.call_count == 1
        rejects(lambda: normal.poll_once(intake), "fresh baseline")
        normal.baseline()
        insert("Normal incoming remains supported")
        insert("Astra: Own requests excluded by default", is_from_me=1)
        assert normal.poll_once(intake)["accepted"] == 1
        assert received[-1]["text"] == "Normal incoming remains supported"

        # One explicit self-chat alias shares resident intake, never the outbound destination.
        alias_config = {**self_config, "self_test_alias": "family@example.invalid"}
        aliases = Bridge(alias_config, self_state, database_path=source_path, self_test=True)
        rejects(lambda: Bridge(alias_config), "Invalid private")
        for invalid_alias in (None, [], "", "  ", "line\nbreak", "x" * 301, "resident@example.invalid"):
            rejects(lambda: Bridge({**self_config, "self_test_alias": invalid_alias}, self_test=True), "distinct approved")
        rejects(lambda: aliases.poll_once(intake), "fresh baseline")
        aliases.baseline()
        before_alias = len(received)
        insert("Astra: Primary request", is_from_me=1)
        insert(None, handle=2, chat=2, is_from_me=1, attributedBody=archive("Astra: Alias request"))
        insert("Astra: Other person", handle=3, chat=3, is_from_me=1)
        insert("Astra: Wrong account", handle=2, chat=2, account="other", is_from_me=1)
        insert("Astra: Group", handle=2, chat=5, is_from_me=1)
        insert("Astra: Incoming excluded", handle=2, chat=2)
        insert("Astra update: task pending", is_from_me=1)
        insert("Astra update: task pending", handle=2, chat=2, is_from_me=1)
        assert aliases.poll_once(intake) == {"status": "polled", "accepted": 2, "ignored": 2}
        assert [(item["actor_id"], item["text"]) for item in received[before_alias:]] == [
            ("resident", "Primary request"), ("resident", "Alias request")]
        assert aliases.poll_once(intake)["accepted"] == 0
        with patch("careanchor.imessage_bridge.subprocess.run", return_value=subprocess.CompletedProcess([], 0, "submitted\n", "")) as run:
            aliases.send_once("alias-update", "resident", "Astra update: request received")
            assert run.call_args.args[0][3] == "resident@example.invalid"
        rejects(lambda: self_demo.poll_once(intake), "fresh baseline")

        changed = copy.deepcopy(config)
        changed["recipients"][0]["account_id"] = "different-account"
        changed_bridge = Bridge(changed, state_path, database_path=source_path)
        rejects(lambda: changed_bridge.poll_once(intake), "fresh baseline")
        with patch("careanchor.imessage_bridge.subprocess.run") as run:
            rejects(lambda: changed_bridge.send_once("new-reply", "resident", "Hello"), "fresh baseline")
            assert not run.called
        changed_bridge.baseline()
        assert changed_bridge.poll_once(intake)["accepted"] == 0
        # A second poll/baseline cannot race the active intake or move its cursor.
        with changed_bridge._poll_lock():
            rejects(lambda: changed_bridge.poll_once(intake), "already active")
            rejects(changed_bridge.baseline, "already active")
        # Failure to durably record an outbound claim prevents any send invocation.
        with sqlite3.connect(state_path) as db:
            db.execute("CREATE TRIGGER block_send BEFORE INSERT ON outbox BEGIN SELECT RAISE(FAIL,'synthetic write failure'); END")
        with patch("careanchor.imessage_bridge.subprocess.run") as run:
            try:
                changed_bridge.send_once("write-fails", "resident", "Hello")
            except sqlite3.Error:
                pass
            else:
                raise AssertionError("Expected private ledger write failure")
            assert not run.called
        malformed = copy.deepcopy(config)
        malformed["recipients"][0]["actor_id"] = []
        rejects(lambda: Bridge(malformed, state_path, database_path=source_path), "distinct actor")
        with sqlite3.connect(source_path) as db:
            db.execute("ALTER TABLE message DROP COLUMN attributedBody")
        assert changed_bridge.readiness()["inbound"] == "configured_unverified"
        assert "schema is unsupported" in self_demo.readiness()["blocker"]
        source_path.rename(root / "old.sqlite3")
        source_path.write_bytes((root / "old.sqlite3").read_bytes())
        rejects(lambda: changed_bridge.poll_once(intake), "fresh baseline")
        # Unsupported/corrupt data does not weaken scope or trigger a broad fallback query.
        other_path = root / "unsupported.sqlite3"
        sqlite3.connect(other_path).close()
        unsupported = Bridge(config, root / "unused.sqlite3", database_path=other_path)
        assert "unsupported" in unsupported.readiness()["blocker"]
        assert not unsupported.state_path.exists()
    print("Apple Messages isolated transport checks passed; no real messages read or sent.")


if __name__ == "__main__":
    check()
