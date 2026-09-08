"""Opt-in, one-to-one Apple Messages transport; no runner or agent lives here.

Nothing is read or sent on import. Private configuration and the cursor/outbox
belong under .runtime. See .coordination/imessage-bridge-contract.md.
"""

from contextlib import closing, contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess


_SCRIPT = '''on run argv
    if (count of argv) is not 3 then error "Invalid arguments"
    set accountId to item 1 of argv
    set recipientHandle to item 2 of argv
    set messageText to item 3 of argv
    tell application "Messages"
        set selectedAccount to account id accountId
        if service type of selectedAccount is not iMessage then error "iMessage required"
        if enabled of selectedAccount is false then error "Account disabled"
        if connection status of selectedAccount is not connected then error "Account disconnected"
        set selectedParticipant to participant recipientHandle of selectedAccount
        if handle of selectedParticipant is not recipientHandle then error "Recipient mismatch"
        if id of account of selectedParticipant is not accountId then error "Account mismatch"
        send messageText to selectedParticipant
    end tell
    return "submitted"
end run
'''

# Apple does not publish chat.db as an API. Unknown schemas stop reception.
_SCHEMA = {
    "message": {"guid", "text", "handle_id", "service", "account", "is_from_me",
                "is_system_message", "is_service_message", "associated_message_type",
                "cache_has_attachments"},
    "handle": {"id", "service"},
    "chat": {"style", "service_name", "room_name"},
    "chat_message_join": {"chat_id", "message_id"},
    "chat_handle_join": {"chat_id", "handle_id"},
}
_ID = re.compile(r"[A-Za-z0-9_-]{1,100}\Z")
MAX_INCOMING_TEXT = 2000  # Same intake limit as resident and family coordination.
_SELF_PREFIX = "Astra:"
_MAX_ARCHIVE = 16384
# Exact class/type/reference skeleton of the consented, plain-text demo archive.
# Format reference: https://github.com/discordwell/green2blue/blob/main/src/green2blue/ios/attributed_body.py
_ATTRIBUTED_PREFIX = (
    b"\x04\x0bstreamtyped\x81\xe8\x03\x84\x01@\x84\x84\x84\x12NSAttributedString\x00"
    b"\x84\x84\x08NSObject\x00\x85\x92\x84\x84\x84\x08NSString\x01\x94\x84\x01+"
)
_ATTRIBUTED_MIDDLE = b"\x86\x84\x02iI\x01"  # End NSString; one attribute run.
_ATTRIBUTED_SUFFIX = (
    b"\x92\x84\x84\x84\x0cNSDictionary\x00\x94\x84\x01i\x01\x92\x84\x96\x96\x1d"
    b"__kIMMessagePartAttributeName\x86\x92\x84\x84\x84\x08NSNumber\x00"
    b"\x84\x84\x07NSValue\x00\x94\x84\x01*\x84\x99\x99\x00\x86\x86\x86"
)


def _attributed_text(blob):
    """Read data only; reject every archive outside the proven plain-text shape."""
    # ponytail: one immutable string/run; support rich variants only with validated fixtures.
    if not isinstance(blob, bytes) or len(blob) > _MAX_ARCHIVE or not blob.startswith(_ATTRIBUTED_PREFIX):
        return None
    position = len(_ATTRIBUTED_PREFIX)

    def uint():
        # Typedstream unsigned integers: literal byte outside the tag range, or LE2/LE4.
        # https://github.com/dgelessus/python-typedstream/blob/main/src/typedstream/stream.py
        nonlocal position
        tag = blob[position]
        position += 1
        if not 0x80 <= tag <= 0x91:
            return tag
        width = {0x81: 2, 0x82: 4}.get(tag)
        if width is None or position + width > len(blob):
            raise ValueError
        value = int.from_bytes(blob[position:position + width], "little")
        position += width
        if value > _MAX_ARCHIVE:
            raise ValueError
        return value

    try:
        size = uint()
        end = position + size
        if end > len(blob) or blob[end:end + len(_ATTRIBUTED_MIDDLE)] != _ATTRIBUTED_MIDDLE:
            return None
        text = blob[position:end].decode("utf-8")
        position = end + len(_ATTRIBUTED_MIDDLE)
        if uint() != len(text.encode("utf-16-le")) // 2 or blob[position:] != _ATTRIBUTED_SUFFIX:
            return None
        return text
    except (ValueError, IndexError):
        return None


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


class Bridge:
    def __init__(self, config=None, state_path=None, *, database_path=None, self_test=False):
        if type(self_test) is not bool or (self_test and config is None):
            raise ValueError("Self-chat demo requires an enabled single resident mapping.")
        self.self_test = self_test
        self.config = json.loads(json.dumps(config)) if config is not None else None
        self.state_path = Path(state_path or Path(__file__).parent / ".runtime/imessage-bridge.sqlite3")
        self.database_path = Path(database_path or Path.home() / "Library/Messages/chat.db")
        if config is None:
            self.recipients = {}
            return
        allowed_keys = {"enabled", "recipients"}
        if self_test and isinstance(config, dict) and "self_test_alias" in config:
            allowed_keys.add("self_test_alias")
        if (not isinstance(config, dict) or set(config) != allowed_keys
                or type(config["enabled"]) is not bool
                or not isinstance(config["recipients"], list)
                or not 1 <= len(config["recipients"]) <= 3):
            raise ValueError("Invalid private Messages configuration.")
        self.recipients = {}
        handles = set()
        for item in self.config["recipients"]:
            if (not isinstance(item, dict)
                    or set(item) != {"actor_id", "handle", "account_id", "inbound_account"}
                    or any(not isinstance(v, str) or not v or len(v) > 300
                           or any(ord(c) < 32 for c in v) for v in item.values())
                    or item["actor_id"] not in {"resident", "alex", "morgan"}
                    or item["actor_id"] in self.recipients or item["handle"] in handles):
                raise ValueError("Each approved Messages participant needs one distinct actor mapping.")
            self.recipients[item["actor_id"]] = item
            handles.add(item["handle"])
        if self_test and (not self.config["enabled"] or set(self.recipients) != {"resident"}):
            raise ValueError("Self-chat demo requires an enabled single resident mapping.")
        if "self_test_alias" in self.config:
            alias = self.config["self_test_alias"]
            if (not isinstance(alias, str) or not alias.strip() or len(alias) > 300
                    or any(ord(c) < 32 for c in alias)
                    or alias == self.recipients["resident"]["handle"]):
                raise ValueError("Self-chat alias must be one distinct approved handle.")

    def _enabled(self):
        if not self.config or not self.config["enabled"]:
            raise ValueError("Messages bridge is disabled; an approved participant configuration is required.")

    def _fingerprint(self):
        try:
            stat = self.database_path.stat()
        except FileNotFoundError:
            raise ValueError("Messages database is missing.") from None
        except PermissionError:
            raise ValueError("macOS denied access to Messages database metadata.") from None
        except OSError:
            raise ValueError("Messages database metadata is unavailable.") from None
        scope = [self.config, str(self.database_path.absolute()), stat.st_dev, stat.st_ino]
        if self.self_test:
            scope.append("self-chat-Astra-prefix-v1")
        return _digest(scope)

    def _source(self):
        connection = None
        try:
            connection = sqlite3.connect(self.database_path.absolute().as_uri() + "?mode=ro", uri=True, timeout=2)
            for table, columns in _SCHEMA.items():
                actual = {row[1] for row in connection.execute("PRAGMA table_info(" + table + ")")}
                if self.self_test and table == "message":
                    columns = columns | {"attributedBody"}
                if not columns <= actual:
                    connection.close()
                    raise ValueError("Messages database schema is unsupported; reception is disabled.")
            return connection
        except sqlite3.Error:
            if connection is not None:
                connection.close()
            raise ValueError("Messages database cannot be opened; OS access or database availability needs checking.") from None

    @contextmanager
    def _poll_lock(self):
        # Separate from SQLite's own lock ranges, which share flock semantics on macOS.
        fd = os.open(str(self.state_path) + ".poll-lock", os.O_CREAT | os.O_RDWR, 0o600)
        with os.fdopen(fd, "rb") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError("Messages polling is already active; wait for that intake to finish.") from None
            yield

    def _ledger(self, *, create=False):
        if not self.state_path.exists():
            if not create:
                raise ValueError("An explicit Messages baseline is required before polling or sending.")
            self.state_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            try:
                fd = os.open(self.state_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                pass
            else:
                os.close(fd)
        try:
            db = sqlite3.connect(self.state_path, timeout=2)
            if create:
                db.executescript("""
                    CREATE TABLE IF NOT EXISTS baseline (id INTEGER PRIMARY KEY CHECK(id=1), fingerprint TEXT NOT NULL, cursor INTEGER NOT NULL);
                    CREATE TABLE IF NOT EXISTS outbox (id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, digest TEXT NOT NULL, status TEXT NOT NULL);
                """)
            return db
        except sqlite3.Error:
            raise ValueError("Private Messages state is unavailable; no effects were attempted.") from None

    def _baseline(self, db):
        try:
            row = db.execute("SELECT fingerprint,cursor FROM baseline WHERE id=1").fetchone()
        except sqlite3.Error:
            raise ValueError("Private Messages state is invalid; no effects were attempted.") from None
        if (not row or row[0] != self._fingerprint() or type(row[1]) is not int or row[1] < 0):
            raise ValueError("An explicit fresh baseline is required after configuration or database changes.")
        return row

    def readiness(self):
        """Read sanitized metadata/schema only; never requests Automation access."""
        result = {"enabled": bool(self.config and self.config["enabled"]),
                  "inbound": "not_checked", "outbound": "not_checked", "blocker": ""}
        try:
            self._enabled()
            self._fingerprint()
            with closing(self._source()):
                pass
            with closing(self._ledger()) as db:
                self._baseline(db)
            result["inbound"] = "configured_unverified"
        except ValueError as error:
            result["blocker"] = str(error)
        return result

    def baseline(self):
        """Explicit activation checkpoint: excludes all existing history, reading no text."""
        self._enabled()
        with closing(self._ledger(create=True)) as db, self._poll_lock(), db:
            fingerprint = self._fingerprint()
            with closing(self._source()) as source:
                cursor = source.execute("SELECT COALESCE(MAX(ROWID),0) FROM message").fetchone()[0]
            if fingerprint != self._fingerprint():
                raise ValueError("Messages database changed while baselining; try explicitly again.")
            db.execute("INSERT OR REPLACE INTO baseline VALUES (1,?,?)", (fingerprint, cursor))
        return {"status": "baselined", "history_imported": False}

    def poll_once(self, on_message, *, limit=25):
        """Acknowledge only durable, deduplicated callback intake; false stops the batch.

        The callback receives source_id/actor_id/text and MUST use source_id as
        its existing application's idempotency key. A crash can redeliver it.
        """
        self._enabled()
        if type(limit) is not int or not 1 <= limit <= 25:
            raise ValueError("Messages poll limit must be between 1 and 25.")
        with closing(self._ledger()) as ledger:
            # ponytail: one local poll at a time; a hosted transport needs a proper inbox lease.
            with self._poll_lock():
                fingerprint, cursor = self._baseline(ledger)
                mappings = list(self.recipients.values())
                if self.self_test and "self_test_alias" in self.config:
                    mappings.append({**mappings[0], "handle": self.config["self_test_alias"]})
                predicate = " OR ".join("(h.id=? AND m.account=?)" for _ in mappings)
                values = [v for item in mappings for v in (item["handle"], item["inbound_account"])]
                with closing(self._source()) as source:
                    source.execute("BEGIN")
                    high = source.execute("SELECT COALESCE(MAX(ROWID),0) FROM message").fetchone()[0]
                    if high < cursor:
                        raise ValueError("Messages history changed; a fresh explicit baseline is required.")
                    archive = ("CASE WHEN length(m.attributedBody)<=? THEN m.attributedBody END"
                               if self.self_test else "NULL")
                    rows = source.execute("""
                        SELECT DISTINCT m.ROWID,m.guid,m.text,h.id,m.account,m.cache_has_attachments,
                        """ + archive + """
                        FROM message m JOIN handle h ON h.ROWID=m.handle_id
                        JOIN chat_message_join cm ON cm.message_id=m.ROWID
                        JOIN chat c ON c.ROWID=cm.chat_id
                        WHERE m.ROWID>? AND m.ROWID<=? AND m.is_from_me=?
                          AND m.service='iMessage' AND h.service='iMessage'
                          AND m.is_system_message=0 AND m.is_service_message=0
                          AND m.associated_message_type=0
                          AND c.service_name='iMessage' AND c.style=45
                          AND COALESCE(c.room_name,'')=''
                          AND (SELECT COUNT(*) FROM chat_handle_join ch WHERE ch.chat_id=c.ROWID)=1
                          AND EXISTS (SELECT 1 FROM chat_handle_join ch WHERE ch.chat_id=c.ROWID AND ch.handle_id=h.ROWID)
                          AND (""" + predicate + ") ORDER BY m.ROWID LIMIT ?",
                        ([_MAX_ARCHIVE] if self.self_test else []) +
                        [cursor, high, int(self.self_test), *values, limit]).fetchall()
                result = {"status": "polled", "accepted": 0, "ignored": 0}
                for rowid, guid, body, handle, account, attachments, archive in rows:
                    if self._fingerprint() != fingerprint:
                        raise ValueError("Messages database changed during polling; rebaseline explicitly.")
                    if self.self_test:
                        if body is None and attachments == 0:
                            body = _attributed_text(archive)
                        body = (body[len(_SELF_PREFIX):].strip()
                                if isinstance(body, str) and body.startswith(_SELF_PREFIX) else None)
                    if (not isinstance(guid, str) or not guid or len(guid) > 300
                            or not isinstance(body, str) or not body.strip()
                            or len(body) > MAX_INCOMING_TEXT or "\x00" in body or attachments != 0):
                        result["ignored"] += 1
                    else:
                        actor = next(item["actor_id"] for item in mappings
                                     if item["handle"] == handle and item["inbound_account"] == account)
                        message = {"source_id": "imsg-" + _digest(guid)[:40], "actor_id": actor, "text": body}
                        if on_message(message) is not True:
                            result["status"] = "waiting_for_intake"
                            return result
                        result["accepted"] += 1
                    with ledger:
                        ledger.execute("UPDATE baseline SET cursor=? WHERE id=1 AND fingerprint=?", (rowid, fingerprint))
                if len(rows) < limit:
                    with ledger:
                        ledger.execute("UPDATE baseline SET cursor=? WHERE id=1 AND fingerprint=?", (high, fingerprint))
                return result

    def send_once(self, reply_id, actor_id, text):
        """Send only a caller-authorized, role-filtered reply; no delivery/read claim."""
        self._enabled()
        if (not isinstance(reply_id, str) or not _ID.fullmatch(reply_id)
                or not isinstance(actor_id, str) or actor_id not in self.recipients
                or not isinstance(text, str) or not text.strip() or len(text) > 4000 or "\x00" in text):
            raise ValueError("Invalid Messages reply or participant.")
        if self.self_test and text.startswith(_SELF_PREFIX):
            raise ValueError("Self-chat replies cannot use the reserved request prefix.")
        if not Path("/usr/bin/osascript").is_file():
            raise ValueError("Apple Messages scripting is unavailable on this host.")
        with closing(self._ledger()) as db:
            fingerprint, _ = self._baseline(db)
            digest = _digest([actor_id, text])
            with db:
                db.execute("BEGIN IMMEDIATE")
                existing = db.execute("SELECT fingerprint,digest,status FROM outbox WHERE id=?", (reply_id,)).fetchone()
                if existing:
                    if existing[:2] != (fingerprint, digest):
                        raise ValueError("A Messages reply ID cannot be reused for changed content or configuration.")
                    return {"status": existing[2], "duplicate": True, "delivery": "unknown", "read": "unknown"}
                # Persist before invoking an external side effect, including its uncertain window.
                db.execute("INSERT INTO outbox VALUES (?,?,?,?)", (reply_id, fingerprint, digest, "uncertain"))
            target = self.recipients[actor_id]
            status = "uncertain"
            try:
                result = subprocess.run(["/usr/bin/osascript", "-", target["account_id"], target["handle"], text],
                                        input=_SCRIPT, text=True, capture_output=True, timeout=20, check=False)
                if result.returncode == 0 and result.stdout.strip() == "submitted":
                    status = "submitted"
            except (OSError, subprocess.SubprocessError):
                pass  # Never expose script errors that may contain message content or handles.
            with db:
                db.execute("UPDATE outbox SET status=? WHERE id=?", (status, reply_id))
        return {"status": status, "duplicate": False, "delivery": "unknown", "read": "unknown"}
