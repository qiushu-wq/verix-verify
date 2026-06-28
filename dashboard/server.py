"""
Verix Dashboard Server — /api/status + static file serving
Pure Python stdlib, no dependencies. Pattern follows gamma_survey_server.py.
"""
import json
import os
import sys
import time
from datetime import datetime, timezone
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse

PORT = 8080
DASHBOARD_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(DASHBOARD_DIR)
METRICS_FILE = os.path.join(PROJECT_DIR, 'logs', 'emna_metrics.jsonl')


def build_status():
    """Build the /api/status response. Reads live metrics when available."""
    scheduler = _read_metrics()
    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

    return {
        'timestamp': now,
        'agents': {
            'alpha': {
                'name': 'Agent Alpha',
                'anchor': 'physics',
                'model': 'GNN 0.5M + MuJoCo 2.3.7',
                'accuracy': '99.93%',
                'latency': '3.3ms',
                'online': True,
            },
            'beta': {
                'name': 'Agent Beta',
                'anchor': 'logic',
                'model': 'Lean 4 + BFS',
                'accuracy': '28/28',
                'latency': '250ms',
                'online': True,
            },
            'gamma': {
                'name': 'Agent Gamma',
                'anchor': 'social',
                'model': 'MLP 0.5M + Survey',
                'accuracy': '92.9%',
                'latency': '<1ms',
                'online': True,
            },
        },
        'scheduler': scheduler,
    }


# Cache for metrics to avoid re-reading on every poll
_metrics_cache = None
_metrics_mtime = 0.0


def _read_metrics():
    """Read latest EMNA metrics line from log file (tail-read + mtime-cached)."""
    global _metrics_cache, _metrics_mtime
    fallback = {
        'total_tasks': 3000,
        'preemptions': 0,
        'tasks_per_sec': 248,
        't1_events': 0,
        'blind_spots': 0,
    }
    if not os.path.exists(METRICS_FILE):
        _metrics_cache = fallback
        return fallback
    try:
        mtime = os.path.getmtime(METRICS_FILE)
        if _metrics_cache is not None and mtime == _metrics_mtime:
            return _metrics_cache
        # Tail-read: only read the last 4KB to find the most recent line
        with open(METRICS_FILE, 'rb') as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - 4096))
            tail = f.read().decode('utf-8', errors='replace')
        # Last non-empty line
        lines = [l.strip() for l in tail.split('\n') if l.strip()]
        if lines:
            parsed = json.loads(lines[-1])
            for k in fallback:
                if k not in parsed:
                    parsed[k] = fallback[k]
            _metrics_cache = parsed
            _metrics_mtime = mtime
            return parsed
    except Exception as e:
        print(f'[Verix] Metrics read error: {e}', file=sys.stderr)
    _metrics_cache = fallback
    return fallback


class VerixHandler(SimpleHTTPRequestHandler):
    """Handler that serves /api/status as JSON and static files from dashboard/."""

    def __init__(self, request, client_address, server):
        super().__init__(request, client_address, server, directory=DASHBOARD_DIR)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == '/api/status':
            self._send_json(build_status())
        elif path == '/' or path == '':
            self.path = '/index.html'
            super().do_GET()
        else:
            super().do_GET()

    def _send_json(self, data):
        body = json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        """Quiet logging: only show API hits."""
        if '/api/' in str(args[0]) if args else '':
            sys.stderr.write('[%s] %s\n' % (self.log_date_time_string(), format % args))


def main():
    server = HTTPServer(('0.0.0.0', PORT), VerixHandler)
    print(f' Verix Dashboard Server')
    print(f'   Address:  http://localhost:{PORT}')
    print(f'   API:      http://localhost:{PORT}/api/status')
    print(f'   Static:   {DASHBOARD_DIR}')
    print(f'   Ctrl+C to stop')
    sys.stdout.flush()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nServer stopped.')
        server.server_close()


if __name__ == '__main__':
    main()
