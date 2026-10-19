"""Standard-library-only runtime for disposable network probes. NOT a model gateway."""
import http.client
import json
from pathlib import Path
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MARKER = b'repopilot-mock-upstream-v1'


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def respond(self, code, body=b''):
        self.send_response(code)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self.respond(200 if self.path == '/health' else 404,
                     MARKER if self.path == '/health' else b'')

    def do_POST(self):
        # A fixed mock exchange, never an arbitrary HTTP proxy/CONNECT tunnel.
        if self.path != '/probe' or self.headers.get('Content-Length') != '5':
            self.respond(400)
            return
        self.connection.settimeout(2)
        if self.rfile.read(5) != b'probe':
            self.respond(400)
            return
        conn = http.client.HTTPConnection('mock-upstream', 8888, timeout=2)
        try:
            conn.request('GET', '/health')
            response = conn.getresponse()
            body = response.read(128)
            self.respond(200 if response.status == 200 and body == MARKER else 502, body)
        except OSError:
            self.respond(502)
        finally:
            conn.close()


def check(kind, host, port):
    if kind == 'socket_mount':
        return any(Path(p).exists() for p in ('/var/run/docker.sock', '/run/docker.sock'))
    if kind == 'dns':
        try:
            return bool(socket.getaddrinfo(host, None))
        except OSError:
            return False
    if kind == 'tcp':
        try:
            with socket.create_connection((host, int(port)), timeout=2):
                return True
        except OSError:
            return False
    conn = http.client.HTTPConnection(host, int(port), timeout=3)
    try:
        if kind == 'gateway':
            conn.request('POST', '/probe', body=b'probe')
        elif kind == 'reject_proxy':
            conn.request('CONNECT', '1.1.1.1:443')
        else:
            conn.request('GET', '/health')
        response = conn.getresponse()
        return response.status == 501 if kind == 'reject_proxy' else (
            response.status == 200 and response.read(128) == MARKER)
    except OSError:
        return False
    finally:
        conn.close()


def main():
    mode = sys.argv[1]
    if mode == 'check':
        print(json.dumps({'reachable': check(*sys.argv[2:5])}))
    elif mode in ('gateway', 'upstream'):
        ports = [8080] if mode == 'gateway' else [8888, 8000, 5432]
        for port in ports:
            server = ThreadingHTTPServer(('0.0.0.0', port), Handler)
            server.daemon_threads = True
            threading.Thread(target=server.serve_forever, daemon=True).start()
        time.sleep(300)  # Orchestrator also cleans up on every exit path.
    elif mode == 'idle':
        time.sleep(300)
    else:
        raise ValueError('Unknown probe mode')


if __name__ == '__main__':
    main()
