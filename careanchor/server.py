"""Loopback-only synthetic demo. Role tabs are perspectives, not authentication."""
import json
import hashlib
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
from urllib.parse import parse_qs, urlsplit

from . import astra_bridge
from .imessage_bridge import Bridge as MessagesBridge
from .proactive import VisitWatcher
from .simulation import Household, InvalidAction

ROOT = Path(__file__).resolve().parents[1]
MAX_BODY = 32768
MAX_JSON_RESPONSE = 262144
STATIC = {'/': ('web/index.html', 'text/html; charset=utf-8'),
          '/index.html': ('web/index.html', 'text/html; charset=utf-8'),
          '/assets/home.png': ('assets/home.png', 'image/png'),
          '/assets/home.blend': ('assets/home.blend', 'application/octet-stream'),
          '/assets/home.glb': ('assets/home.glb', 'model/gltf-binary'),
          '/assets/sketch-home.png': ('assets/sketch-home.png', 'image/png'),
          '/assets/sketch-home.blend': ('assets/sketch-home.blend', 'application/octet-stream'),
          '/assets/sketch-home.glb': ('assets/sketch-home.glb', 'model/gltf-binary'),
          '/assets/sketch-adapted.png': ('assets/sketch-adapted.png', 'image/png'),
          '/assets/sketch-adapted.blend': ('assets/sketch-adapted.blend', 'application/octet-stream')}


# Fixed authored asset names only; never expose arbitrary manifest paths or assets.
for name in ('meal-room', 'meal-foreground', 'meal-dish-full', 'meal-dish-used', 'sketch-cart'):
    STATIC[f'/assets/{name}.png'] = (f'assets/{name}.png', 'image/png')
for name in ('meal-room', 'sketch-cart'):
    STATIC[f'/assets/{name}.blend'] = (f'assets/{name}.blend', 'application/octet-stream')
for name in ('meal-scene', 'sketch-cart'):
    STATIC[f'/assets/{name}.json'] = (f'assets/{name}.json', 'application/json')
STATIC['/assets/sketch-cart.glb'] = ('assets/sketch-cart.glb', 'model/gltf-binary')
for actor in ('resident', 'helper'):
    for pose in ('idle', 'walk_a', 'walk_b', 'carry', 'carry_walk_a', 'carry_walk_b'):
        for direction in ('south', 'east', 'north', 'west'):
            name = f'assets/meal-sprites/{actor}-{pose}-{direction}.png'
            STATIC['/' + name] = (name, 'image/png')
for pose in ('seated', 'eating'):
    name = f'assets/meal-sprites/resident-{pose}-south.png'
    STATIC['/' + name] = (name, 'image/png')


class RequestError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port=8765, save_path=None, messages_config=None, messages_self_test=False):
        self.household = Household(save_path=save_path)
        # ponytail: one household lock; split by household if the demo becomes multi-home.
        self.state_lock = threading.RLock()
        self.coordination_gate = threading.Lock()
        self.messages = MessagesBridge(messages_config, self_test=messages_self_test)
        self.messages_poll_status = {'status': 'disabled', 'blocker': ''}
        self.proactive = VisitWatcher(self)
        super().__init__(('127.0.0.1', port), Handler)

    def poll_messages(self, stop):
        """Explicit CLI opt-in only; the adapter owns baseline, scope, and serialization."""
        delay = 3
        self.messages_poll_status = {'status': 'waiting', 'blocker': ''}
        while not stop.wait(delay):
            self.messages_poll_status = {'status': 'polling', 'blocker': ''}
            try:
                result = self.messages.poll_once(self.accept_message, limit=1)
                waiting = result['status'] == 'waiting_for_intake'
                self.messages_poll_status = {'status': result['status'],
                    'blocker': 'Waiting for household intake; retrying shortly.' if waiting else ''}
                delay = 10 if waiting else 3
            except Exception:
                # Never log message text, private mappings, or raw transport errors.
                self.messages_poll_status = {'status': 'unavailable',
                    'blocker': 'Messages intake failed; check readiness and the explicit baseline. Retrying in 10 seconds.'}
                delay = 10
        self.messages_poll_status = {**self.messages_poll_status, 'status': 'stopped'}


    def coordination_response(self, request_id, status=200, **details):
        with self.state_lock:
            state = self.household.view('resident')
            request = next((r for r in state['coordination']['requests'] if r['id'] == request_id), None)
            return status, {'state': state, 'request': request, 'engine': astra_bridge.MODEL, **details}

    def coordinate(self, data, intake=True, *, proactive=None):
        required = {'role', 'revision', 'request_id'} | ({'message'} if intake else set())
        allowed = required | ({'replace_request_id'} if intake else set())
        if (not required <= set(data) <= allowed or data['role'] != 'resident' or
                type(data['revision']) is not int or not 0 <= data['revision'] <= 2**53 - 1):
            raise RequestError(400, 'Supply a resident request and current integer revision.')
        for key in ('request_id', 'replace_request_id'):
            if key in data and (type(data[key]) is not str or not 1 <= len(data[key]) <= 48 or
                               not all(c.isascii() and (c.isalnum() or c in '_-') for c in data[key])):
                raise RequestError(400, 'Use a bounded request identifier.')
        if intake and (type(data['message']) is not str or not data['message'].strip() or len(data['message']) > 2000):
            raise RequestError(400, 'Message must contain 1–2000 characters.')
        household, request_id = self.household, data['request_id']
        if proactive is None and request_id.startswith('proactive-') and intake:
            raise RequestError(400, 'That request identifier is reserved for automatic visit checks.')
        with self.state_lock:
            state = household.view('resident')
            if intake and any(r['id'] == request_id for r in state['coordination']['requests']):
                household.begin_coordination(request_id, data['message'], data['revision'], data.get('replace_request_id'))
                return self.coordination_response(request_id)
            if state['revision'] != data['revision']:
                raise RequestError(409, 'The household changed. Refresh before continuing.')
            if not self.coordination_gate.acquire(blocking=False):
                raise RequestError(409, 'Another request is running. You can still cancel it.')
        started = False
        try:
            if intake:
                with self.state_lock:
                    household.begin_coordination(request_id, data['message'], data['revision'], data.get('replace_request_id'),
                                                 initiated_by='coordinator' if proactive is not None else 'resident')
                    started = True
                    if (proactive is not None and household.save_path is not None
                            and household.mission_persistence['status'] != 'saved'):
                        raise InvalidAction('The automatic request could not be saved; no model call or actions were started.')
                    context = household.coordination_context(request_id)
                    if proactive is not None:
                        context['proactive_notice'] = {key: proactive[key] for key in
                            ('notice', 'availability_on_visit_date', 'previous_helpers')}
                proposal = astra_bridge.interpret_request(context, data['message'])
                with self.state_lock:
                    try:
                        current = household.coordination_context(request_id)
                        if current['version'] != context['version']:
                            raise InvalidAction('Request context changed.')
                    except InvalidAction:
                        household.fail_coordination(request_id, 'The request context changed. Review it before retrying.')
                        return self.coordination_response(request_id, 409)
                    try:
                        if proactive is not None:
                            self.proactive.validate(proposal, proactive)
                        household.accept_coordination(request_id, proposal, context['version'])
                    except (InvalidAction, ValueError) as exc:
                        household.fail_coordination(request_id, str(exc))
                        encoded = json.dumps(proposal, ensure_ascii=False).encode()
                        interpretation = (proposal if len(encoded) <= 8192 else
                            {'truncated': True, 'json_prefix': encoded[:8192].decode('utf-8', errors='ignore')})
                        return self.coordination_response(request_id, 400, interpretation=interpretation)
                    if proactive is not None:
                        # Validation and bounded local effects are atomic with respect to new notices and revocation.
                        for _ in range(12):
                            if (household.save_path is not None
                                    and household.mission_persistence['status'] != 'saved'):
                                return self.coordination_response(request_id, 503, error='Automatic work stopped because the household could not be saved.')
                            if not household.advance_coordination(request_id):
                                break
                        return self.coordination_response(request_id)
            else:
                with self.state_lock:
                    household.coordination_context(request_id)
                    started = True
            for _ in range(12):
                with self.state_lock:
                    if not household.advance_coordination(request_id):
                        break
            return self.coordination_response(request_id)
        except (astra_bridge.BridgeError, InvalidAction) as exc:
            if not started:
                raise
            with self.state_lock:
                household.fail_coordination(request_id, str(exc))
            return self.coordination_response(request_id, 429 if isinstance(exc, astra_bridge.Busy)
                                       else 503 if isinstance(exc, astra_bridge.BridgeError) else 400)
        finally:
            self.coordination_gate.release()

    def recipient_reply(self, data):
        if (set(data) != {'role', 'actor_id', 'revision', 'reply_id', 'message'} or
                data['role'] != 'family' or data['actor_id'] not in ('alex', 'morgan') or
                type(data['revision']) is not int or not 0 <= data['revision'] <= 2**53 - 1 or
                type(data['reply_id']) is not str or not 1 <= len(data['reply_id']) <= 48 or
                not all(c.isascii() and (c.isalnum() or c in '_-') for c in data['reply_id']) or
                type(data['message']) is not str or not data['message'].strip() or len(data['message']) > 2000):
            raise RequestError(400, 'Supply a named family actor, current revision, reply ID, and response text.')
        household, actor = self.household, data['actor_id']
        def respond(status, reply=None, error=None):
            with self.state_lock:
                result = {'state': household.view('family', actor_id=actor),
                          'reply': reply, 'engine': astra_bridge.MODEL}
                if error:
                    result['error'] = error
                return status, result
        with self.state_lock:
            state = household.view('family', actor_id=actor)
            if any(r['id'] == data['reply_id'] for r in state['coordination']['replies']):
                reply = household.accept_recipient_reply(data['reply_id'], actor, data['message'],
                    {'decisions': [], 'question': ''}, state['coordination']['version'])
                return respond(200, reply)
            if state['revision'] != data['revision']:
                raise RequestError(409, 'The household changed. Refresh before replying.')
            if not self.coordination_gate.acquire(blocking=False):
                raise RequestError(409, 'Another request is running. Try your reply shortly.')
        try:
            with self.state_lock:
                context = household.recipient_context(actor, data['revision'])
            proposal = astra_bridge.interpret_helper_reply(context, data['message'])
            with self.state_lock:
                state = household.view('family', actor_id=actor)
                if state['coordination']['version'] != context['version']:
                    return respond(409, error='Responsibilities changed while Astra interpreted your reply.')
                reply = household.accept_recipient_reply(data['reply_id'], actor, data['message'], proposal, context['version'])
                return respond(200, reply)
        except (astra_bridge.BridgeError, InvalidAction) as exc:
            return respond(429 if isinstance(exc, astra_bridge.Busy) else
                    503 if isinstance(exc, astra_bridge.BridgeError) else 400, error=str(exc))
        finally:
            self.coordination_gate.release()

    def message_snapshot(self):
        """Meaningful, recipient-filtered notices only; no revision/tick fields."""
        if not self.messages.config or not self.messages.config['enabled']:
            return {}
        with self.state_lock:
            notices = {}
            for actor in self.messages.recipients:
                state = self.household.view('resident' if actor == 'resident' else 'family', actor_id=actor)
                if actor == 'resident':
                    for request in state['coordination']['requests']:
                        if request['status'] == 'interpreting':
                            continue
                        text = request['question'] or request['error'] or request['summary']
                        notices[(actor, 'request', request['id'])] = ('Household simulation: ' + text +
                            '\nRequest status: ' + request['status'].replace('_', ' ') + '.')
                else:
                    for item in state['coordination']['inbox']:
                        notices[(actor, 'inbox', item['id'])] = ('Household simulation: ' + item['body'] +
                            '\nYour update status: ' + item['status'].replace('_', ' ') + '.')
            return notices

    def send_changed_updates(self, before):
        """Send after addressed task processing or an authorized visit check, never a GET."""
        changed = [(key, text) for key, text in self.message_snapshot().items() if before.get(key) != text]
        results = []
        # ponytail: at most 25 addressed updates per processing pass for this single household.
        for key, text in changed[:25]:
            with self.state_lock:
                if (not self.messages.config or not self.messages.config['enabled'] or
                        self.household.save_path is None or self.household.mission_persistence['status'] not in ('saved', 'restored') or
                        not self.household.coordination.state['permissions']['notify']):
                    break
                if self.message_snapshot().get(key) != text:
                    continue
            digest = hashlib.sha256(json.dumps([key, text], ensure_ascii=False).encode()).hexdigest()
            try:
                result = self.messages.send_once('update-' + digest, key[0], text)
            except (ValueError, OSError):
                result = {'status': 'unavailable', 'delivery': 'unknown', 'read': 'unknown'}
            results.append({'actor_id': key[0], **result})
        return results

    def send_message_outcome(self, source_id, actor):
        """Internal supervised send, never an HTTP destination or arbitrary text."""
        with self.state_lock:
            if (actor not in self.messages.recipients or not self.messages.config['enabled'] or
                    self.household.save_path is None or self.household.mission_persistence['status'] not in ('saved', 'restored')):
                raise RequestError(503, 'A configured participant and saved household are required.')
            if not self.household.coordination.state['permissions']['notify']:
                raise RequestError(403, 'Household permission for addressed updates is missing.')
            state = self.household.view('resident' if actor == 'resident' else 'family', actor_id=actor)
            records = state['coordination']['requests' if actor == 'resident' else 'replies']
            record = next((r for r in records if r['id'] == source_id), None)
            if record is None or record.get('status') == 'interpreting':
                raise RequestError(409, 'There is no completed interpretation to report.')
            if actor == 'resident':
                text = record['question'] or record['error'] or record['summary']
            else:
                accepted = sum(d['status'] == 'accepted' for d in record['decisions'])
                declined = sum(d['status'] == 'declined' for d in record['decisions'])
                text = record['question'] or f'Recorded your reply: {accepted} accepted and {declined} declined responsibilities. Physical completion is not implied.'
        return self.messages.send_once(source_id + '-outcome', actor, 'Household simulation: ' + text)

    def accept_message(self, incoming):
        """Adapter callback only: configured identity, same pipeline, durable acknowledgment."""
        if (not self.messages.config or not self.messages.config['enabled'] or
                self.household.save_path is None or type(incoming) is not dict or
                set(incoming) != {'source_id', 'actor_id', 'text'} or
                type(incoming['actor_id']) is not str or incoming['actor_id'] not in self.messages.recipients):
            return False
        actor, source_id = incoming['actor_id'], incoming['source_id']
        before = self.message_snapshot()
        if actor == 'resident' and isinstance(source_id, str):
            # Retry the current notice after restart; send_once deduplicates its stable ID.
            before.pop((actor, 'request', source_id), None)
        with self.state_lock:
            revision = self.household.revision
        try:
            if actor == 'resident':
                self.coordinate({'role': 'resident', 'revision': revision,
                    'request_id': source_id, 'message': incoming['text']})
            else:
                self.recipient_reply({'role': 'family', 'actor_id': actor, 'revision': revision,
                    'reply_id': source_id, 'message': incoming['text']})
        except (RequestError, InvalidAction, astra_bridge.BridgeError):
            return False
        with self.state_lock:
            state = self.household.view('resident' if actor == 'resident' else 'family', actor_id=actor)
            records = state['coordination']['requests' if actor == 'resident' else 'replies']
            record = next((r for r in records if r['id'] == source_id), None)
            durable = bool(record and (actor != 'resident' or record['status'] != 'interpreting')
                           and self.household.mission_persistence['status'] in ('saved', 'restored'))
        if durable:
            self.send_changed_updates(before)
        return durable


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, *_):
        pass  # Never log messages, prompts, CLI output, or query strings.

    def send_error(self, code, message=None, explain=None):
        self.respond(code, {'error': 'Request could not be handled.'})

    def respond(self, status, data):
        body = bytearray()
        for chunk in json.JSONEncoder(ensure_ascii=False).iterencode(data):
            body.extend(chunk.encode())
            if len(body) > MAX_JSON_RESPONSE:
                status = 500
                body = b'{"error":"Response exceeds the local demo limit."}'
                break
        self.headers_for(status, 'application/json; charset=utf-8', len(body))
        self.wfile.write(body)

    def headers_for(self, status, kind, length):
        self.send_response(status)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(length))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
        self.send_header('Connection', 'close')
        self.end_headers()
        self.close_connection = True

    def boundary(self):
        hosts = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
        if len(self.headers.get_all('Host', [])) != 1 or self.headers['Host'] not in hosts:
            raise RequestError(403, 'Use the local demo address.')
        origins = self.headers.get_all('Origin', [])
        if len(origins) > 1 or (origins and origins[0] != 'http://' + self.headers['Host']):
            raise RequestError(403, 'This origin is not allowed.')
        if self.headers.get('Sec-Fetch-Site') == 'cross-site':
            raise RequestError(403, 'Cross-site requests are not allowed.')
        target = urlsplit(self.path)
        if target.scheme or target.netloc or target.fragment:
            raise RequestError(400, 'Invalid request path.')
        return target

    @staticmethod
    def role(value):
        if value not in ('resident', 'family'):
            raise RequestError(400, 'Choose resident or family.')
        return value

    @staticmethod
    def actor(role, actor_id):
        if actor_id is not None and actor_id not in (('alex', 'morgan') if role == 'family' else ('resident',)):
            raise RequestError(400, 'Choose a named actor for this perspective.')
        return actor_id

    def body(self):
        if self.headers.get('Transfer-Encoding'):
            raise RequestError(400, 'Transfer encoding is not supported.')
        lengths = self.headers.get_all('Content-Length', [])
        if len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit():
            raise RequestError(400, 'A valid content length is required.')
        length = int(lengths[0])
        if not 0 < length <= MAX_BODY:
            raise RequestError(413, 'Request is too large or empty.')
        if self.headers.get_content_type() != 'application/json':
            raise RequestError(415, 'Send application/json.')
        raw = self.rfile.read(length)
        if len(raw) != length:
            raise RequestError(400, 'Incomplete request.')
        def pairs(items):
            result = {}
            for key, value in items:
                if key in result:
                    raise ValueError('Duplicate key')
                result[key] = value
            return result
        try:
            data = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs,
                              parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        except (UnicodeError, ValueError, RecursionError):
            raise RequestError(400, 'Send a valid JSON object.') from None
        if type(data) is not dict:
            raise RequestError(400, 'Send a JSON object.')
        return data

    def do_GET(self):
        self.handle_route(False)

    def do_POST(self):
        self.handle_route(True)

    def handle_route(self, post):
        try:
            target = self.boundary()
            if not post and target.path == '/api/state':
                query = parse_qs(target.query, keep_blank_values=True, strict_parsing=True, max_num_fields=2)
                if 'role' not in query or set(query) - {'role', 'actor_id'} or any(len(v) != 1 for v in query.values()):
                    raise RequestError(400, 'Supply one role and optional named actor.')
                role = self.role(query['role'][0])
                actor_id = self.actor(role, query.get('actor_id', [None])[0])
                self.respond(200, self.server.household.view(role, actor_id=actor_id))
            elif not post and target.path == '/api/real-options':
                from .real_world import match_options
                query = parse_qs(target.query, keep_blank_values=True, strict_parsing=True, max_num_fields=3)
                if set(query) - {'need', 'budget_cents', 'channel'} or any(len(values) != 1 for values in query.values()):
                    raise RequestError(400, 'Supply one need, optional budget in cents, and channel.')
                need = query.get('need', ['home_storage'])[0]
                budget = query.get('budget_cents', [None])[0]
                if budget is not None:
                    if not budget.isascii() or not budget.isdigit() or len(budget) > 16 or int(budget) > 2**53 - 1:
                        raise RequestError(400, 'Budget must be a nonnegative integer number of cents.')
                    budget = int(budget)
                self.respond(200, match_options(need=need, budget_cents=budget,
                                               channel=query.get('channel', ['all'])[0]))
            elif not post and target.path == '/api/comparison' and not target.query:
                self.respond(200, self.server.household.comparison())
            elif not post and target.path.startswith('/api/family-edition/pdf/') and not target.query:
                filename = target.path.removeprefix('/api/family-edition/pdf/')
                with self.server.state_lock:
                    edition = self.server.household.family_edition
                    try:
                        body = edition.current_pdf_path(filename).read_bytes()
                        edition.current_pdf_path(filename)
                        if hashlib.sha256(body).hexdigest() != edition.state['artifact']['sha256']:
                            raise ValueError('Edition changed during download.')
                    except (ValueError, OSError):
                        raise RequestError(404, 'The current approved edition is not available.') from None
                    self.headers_for(200, 'application/pdf', len(body))
                self.wfile.write(body)
            elif not post and target.path == '/api/messages/readiness' and not target.query:
                self.respond(200, {**self.server.messages.readiness(),
                                   'automatic_poll': self.server.messages_poll_status})
            elif not post and target.path == '/api/proactive' and not target.query:
                self.respond(200, self.server.proactive.view())
            elif post and target.path == '/api/proactive' and not target.query:
                data = self.body()
                if (set(data) != {'role', 'revision', 'enabled'} or data['role'] != 'resident'
                        or type(data['revision']) is not int or type(data['enabled']) is not bool):
                    raise RequestError(400, 'Supply the resident role, current revision and watch preference.')
                with self.server.state_lock:
                    if data['revision'] != self.server.household.revision:
                        raise RequestError(409, 'The household changed. Refresh before changing visit monitoring.')
                    self.respond(200, self.server.proactive.set_enabled(data['enabled']))
            elif not post and target.path == '/api/health' and not target.query:
                self.respond(200, {'status': 'ok', 'engine': astra_bridge.MODEL,
                                  'cli_available': Path(astra_bridge.CODEX).is_file(),
                                  'inference': 'not_checked', 'synthetic': True})
            elif post and target.path in ('/api/messages/baseline', '/api/messages/poll') and not target.query:
                data = self.body()
                allowed = {'role', 'revision'} | ({'limit'} if target.path.endswith('/poll') else set())
                if (not {'role', 'revision'} <= set(data) <= allowed or data['role'] != 'resident' or
                        type(data['revision']) is not int or not 0 <= data['revision'] <= 2**53 - 1 or
                        ('limit' in data and (type(data['limit']) is not int or not 1 <= data['limit'] <= 25))):
                    raise RequestError(400, 'Supply the resident role, current revision, and optional bounded poll limit.')
                with self.server.state_lock:
                    if self.server.household.revision != data['revision']:
                        raise RequestError(409, 'The household changed. Refresh before Messages setup.')
                    if not self.server.messages.config or not self.server.messages.config['enabled']:
                        raise RequestError(503, 'Messages is disabled; an approved private participant configuration is required.')
                    if self.server.household.save_path is None:
                        raise RequestError(503, 'Saved household state is required before receiving Messages.')
                result = (self.server.messages.baseline() if target.path.endswith('/baseline') else
                          self.server.messages.poll_once(self.server.accept_message, limit=data.get('limit', 1)))
                self.respond(200, result)
            elif post and target.path == '/api/coordination/reply' and not target.query:
                before = self.server.message_snapshot()
                status, result = self.server.recipient_reply(self.body())
                self.server.send_changed_updates(before)
                self.respond(status, result)
            elif post and target.path in ('/api/coordination/request', '/api/coordination/run') and not target.query:
                before = self.server.message_snapshot()
                status, result = self.server.coordinate(self.body(), target.path.endswith('/request'))
                self.server.send_changed_updates(before)
                self.respond(status, result)
            elif post and target.path == '/api/mission/astra' and not target.query:
                data = self.body()
                if (set(data) != {'role', 'revision'} or data['role'] != 'resident' or
                        type(data['revision']) is not int or not 0 <= data['revision'] <= 2**53 - 1):
                    raise RequestError(400, 'Supply the resident role and current integer revision.')
                with self.server.state_lock:
                    snapshot = self.server.household.coordinator_view()
                    if snapshot['revision'] != data['revision']:
                        raise RequestError(409, 'The mission changed. Refresh before asking Astra.')
                proposal = astra_bridge.propose_mission(snapshot)
                with self.server.state_lock:
                    audit = self.server.household.apply_mission_proposal(proposal, data['revision'])
                    status = 200 if audit['accepted'] else 409 if audit['rejection'] == 'stale' else 400
                    self.respond(status, {'state': self.server.household.view('resident'),
                                          'proposal': audit, 'engine': astra_bridge.MODEL})
            elif post and target.path in ('/api/event', '/api/chat') and not target.query:
                data = self.body()
                role = self.role(data.get('role'))
                actor_id = self.actor(role, data.get('actor_id'))
                if 'actor_id' in data and actor_id is None:
                    raise RequestError(400, 'Choose a named actor.')
                if target.path == '/api/event':
                    if (set(data) - {'actor_id'} not in ({'role', 'action', 'revision'},
                                          {'role', 'action', 'revision', 'payload'}) or
                            ('payload' in data and type(data['payload']) is not dict) or
                            type(data['action']) is not str or type(data['revision']) is not int or
                            not 0 <= data['revision'] <= 2**53):
                        raise RequestError(400, 'Supply role, action, and integer revision.')
                    with self.server.state_lock:
                        before = self.server.message_snapshot() if role == 'family' else None
                        state = self.server.household.event(
                            data['action'], role, data['revision'], **(
                                {'payload': data['payload']} if 'payload' in data else {}), **(
                                {'actor_id': actor_id} if actor_id is not None else {}))
                    if before is not None:
                        self.server.send_changed_updates(before)
                    self.respond(200, state)
                else:
                    if (set(data) - {'actor_id', 'context_revision'} != {'role', 'message', 'history'} or
                            ('context_revision' in data and (type(data['context_revision']) is not int or
                                                            not 0 <= data['context_revision'] <= 2**53 - 1))):
                        raise RequestError(400, 'Supply role, message, history, and optional current context revision.')
                    message, history = data['message'], data['history']
                    if type(message) is not str or not message.strip() or len(message) > 2000:
                        raise RequestError(400, 'Message must contain 1–2000 characters.')
                    if type(history) is not list or len(history) > 12:
                        raise RequestError(400, 'History must contain at most 12 messages.')
                    for item in history:
                        if (type(item) is not dict or set(item) != {'role', 'content'} or
                                item['role'] not in ('user', 'assistant') or
                                type(item['content']) is not str or len(item['content']) > 4000):
                            raise RequestError(400, 'Invalid channel history.')
                    with self.server.state_lock:
                        view = self.server.household.view(role, actor_id=actor_id)
                        view['coordination'] = self.server.household.coordination.model_view(role, actor_id)
                        memory_active = view['coordination'].get('memory_revision', 0) > 0
                        if (memory_active or 'context_revision' in data) and data.get('context_revision') != view['context_revision']:
                            raise RequestError(409, 'Conversation context changed. Refresh before sending again.')
                        if memory_active:
                            if role == 'family' and actor_id is None:
                                raise RequestError(400, 'Choose a named family actor for the current conversation.')
                            history = []
                    answer = astra_bridge.reply(view, message, history)
                    with self.server.state_lock:
                        if self.server.household.view(role, actor_id=actor_id)['revision'] != view['revision']:
                            raise RequestError(409, 'The plan changed while Astra was replying. Please send again.')
                        self.respond(200, {'reply': answer, 'engine': astra_bridge.MODEL,
                                           'revision': view['revision'], 'context_revision': view['context_revision'],
                                           'actor_id': view['actor_id']})
            elif not post and target.path in STATIC and not target.query:
                filename, kind = STATIC[target.path]
                path = ROOT / filename
                if not path.is_file() or path.resolve() != path:
                    raise RequestError(404, 'File is not available.')
                with path.open('rb') as stream:
                    self.headers_for(200, kind, path.stat().st_size)
                    while chunk := stream.read(65536):
                        self.wfile.write(chunk)
            else:
                raise RequestError(404, 'Not found.')
        except RequestError as exc:
            self.respond(exc.status, {'error': exc.message})
        except InvalidAction as exc:
            self.respond(400, {'error': str(exc)})
        except astra_bridge.Busy as exc:
            self.respond(429, {'error': str(exc)})
        except astra_bridge.BridgeError as exc:
            self.respond(503, {'error': str(exc)})
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass
        except (ValueError, OSError):
            self.respond(400, {'error': 'Request could not be handled.'})


def main():
    parser = argparse.ArgumentParser(description='Run the local household demo.')
    parser.add_argument('--messages-config', type=Path, help='Explicit private Messages configuration JSON.')
    parser.add_argument('--messages-poll', action='store_true', help='Receive new Messages while running; requires an existing explicit baseline.')
    parser.add_argument('--messages-self-test', action='store_true', help='Explicit selected-resident self-chat test; requires config, polling, and a fresh manual baseline.')
    args = parser.parse_args()
    config = None
    if args.messages_poll and not args.messages_config:
        parser.error('--messages-poll requires --messages-config.')
    if args.messages_self_test and not (args.messages_config and args.messages_poll):
        parser.error('--messages-self-test requires --messages-config and --messages-poll.')
    if args.messages_config:
        try:
            with args.messages_config.open('rb') as stream:
                raw = stream.read(MAX_BODY + 1)
            if len(raw) > MAX_BODY:
                raise ValueError()
            config = json.loads(raw)
            MessagesBridge(config, self_test=args.messages_self_test)  # Validate without Messages access or baselining.
            if args.messages_poll and not config['enabled']:
                raise ValueError()
        except (OSError, ValueError, TypeError, KeyError):
            parser.error('Private Messages configuration is unreadable, invalid, or disabled for polling.')
    with Server(save_path=ROOT / '.runtime' / 'mission-state.json', messages_config=config,
                messages_self_test=args.messages_self_test) as server:
        stop = threading.Event()
        receiver = threading.Thread(target=server.poll_messages, args=(stop,)) if args.messages_poll else None
        watcher = threading.Thread(target=server.proactive.run, args=(stop,))
        watcher.start()
        if receiver:
            receiver.start()
        print('CareAnchor: http://127.0.0.1:8765', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            stop.set()
            watcher.join()
            if receiver:
                receiver.join()  # Finish the current bounded intake before closing; schedule no further polls.


if __name__ == '__main__':
    main()
