"""Loopback-only synthetic demo. Role tabs are perspectives, not authentication."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
from urllib.parse import parse_qs, urlsplit

import astra_bridge
from simulation import Household, InvalidAction

ROOT = Path(__file__).resolve().parent
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


class RequestError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port=8765):
        self.household = Household()
        # ponytail: one household lock; split by household if the demo becomes multi-home.
        self.state_lock = threading.RLock()
        super().__init__(('127.0.0.1', port), Handler)


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
                query = parse_qs(target.query, keep_blank_values=True)
                if set(query) != {'role'} or len(query['role']) != 1:
                    raise RequestError(400, 'Supply one role.')
                self.respond(200, self.server.household.view(self.role(query['role'][0])))
            elif not post and target.path == '/api/real-options':
                from real_world import match_options
                query = parse_qs(target.query, keep_blank_values=True, strict_parsing=True, max_num_fields=2)
                if set(query) - {'need', 'budget_cents'} or any(len(values) != 1 for values in query.values()):
                    raise RequestError(400, 'Supply one need and an optional budget in cents.')
                need = query.get('need', ['home_storage'])[0]
                budget = query.get('budget_cents', [None])[0]
                if budget is not None:
                    if not budget.isascii() or not budget.isdigit() or len(budget) > 16 or int(budget) > 2**53 - 1:
                        raise RequestError(400, 'Budget must be a nonnegative integer number of cents.')
                    budget = int(budget)
                self.respond(200, match_options(need=need, budget_cents=budget))
            elif not post and target.path == '/api/comparison' and not target.query:
                self.respond(200, self.server.household.comparison())
            elif not post and target.path == '/api/health' and not target.query:
                self.respond(200, {'status': 'ok', 'engine': astra_bridge.MODEL,
                                  'cli_available': Path(astra_bridge.CODEX).is_file(),
                                  'inference': 'not_checked', 'synthetic': True})
            elif post and target.path in ('/api/event', '/api/chat') and not target.query:
                data = self.body()
                role = self.role(data.get('role'))
                if target.path == '/api/event':
                    if (set(data) not in ({'role', 'action', 'revision'},
                                          {'role', 'action', 'revision', 'payload'}) or
                            ('payload' in data and type(data['payload']) is not dict) or
                            type(data['action']) is not str or type(data['revision']) is not int or
                            not 0 <= data['revision'] <= 2**53):
                        raise RequestError(400, 'Supply role, action, and integer revision.')
                    with self.server.state_lock:
                        self.respond(200, self.server.household.event(
                            data['action'], role, data['revision'], **(
                                {'payload': data['payload']} if 'payload' in data else {})))
                else:
                    if set(data) != {'role', 'message', 'history'}:
                        raise RequestError(400, 'Supply role, message, and history.')
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
                        view = self.server.household.view(role)
                    answer = astra_bridge.reply(view, message, history)
                    with self.server.state_lock:
                        if self.server.household.view(role)['revision'] != view['revision']:
                            raise RequestError(409, 'The plan changed while Astra was replying. Please send again.')
                        self.respond(200, {'reply': answer, 'engine': astra_bridge.MODEL,
                                           'revision': view['revision']})
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


if __name__ == '__main__':
    with Server() as server:
        print('Astra Aging: http://127.0.0.1:8765', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
