#!/usr/bin/env python3
"""SetTheory — local server.

   python3 server.py, then open http://localhost:8420

   Serves the app, transcodes AIFF->MP3 on demand via ffmpeg (cached, range-capable),
   and persists your label notes to state.json. Nothing here talks to the network;
   build.py does that.
"""
import json, os, re, subprocess, threading, hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HERE  = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, '.cache', 'audio')
STATE = os.path.join(HERE, 'state.json')
PORT  = 8420
os.makedirs(CACHE, exist_ok=True)
_lock = threading.Lock()

def data():   return json.load(open(os.path.join(HERE, 'data.json')))
def state():  return json.load(open(STATE)) if os.path.exists(STATE) else {'labels': {}}
def save(s):
    with _lock:
        tmp = STATE + '.tmp'
        json.dump(s, open(tmp, 'w'), indent=1)
        os.replace(tmp, STATE)

def audio_file(path):
    """Transcode to mp3 once, cache, return path. MP3s pass through."""
    if path.lower().endswith('.mp3'):
        return path
    h = hashlib.md5(path.encode()).hexdigest()
    out = os.path.join(CACHE, h + '.mp3')
    if not os.path.exists(out):
        r = subprocess.run(['ffmpeg', '-nostdin', '-i', path, '-b:a', '192k', '-y', out],
                           capture_output=True)
        if r.returncode != 0 or not os.path.exists(out):
            return None
    return out

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, code, body, ctype='application/json'):
        if isinstance(body, str): body = body.encode()
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ('/', '/index.html'):
            return self._send(200, open(os.path.join(HERE, 'app.html'), 'rb').read(), 'text/html; charset=utf-8')
        if u.path == '/api/data':
            return self._send(200, json.dumps(data()))
        if u.path == '/api/state':
            return self._send(200, json.dumps(state()))
        if u.path == '/audio':
            tid = int(parse_qs(u.query).get('id', ['-1'])[0])
            tracks = data()['tracks']
            if not (0 <= tid < len(tracks)): return self._send(404, b'no track', 'text/plain')
            src = tracks[tid]['path']
            if not os.path.exists(src): return self._send(404, b'file missing on disk', 'text/plain')
            f = audio_file(src)
            if not f: return self._send(500, b'transcode failed', 'text/plain')
            return self._range(f)
        self._send(404, b'nope', 'text/plain')

    def _range(self, f):
        size = os.path.getsize(f)
        rng = self.headers.get('Range')
        start, end = 0, size - 1
        if rng and (m := re.match(r'bytes=(\d+)-(\d*)', rng)):
            start = int(m.group(1))
            if m.group(2): end = min(int(m.group(2)), size - 1)
        length = end - start + 1
        self.send_response(206 if rng else 200)
        self.send_header('Content-Type', 'audio/mpeg')
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Content-Length', str(length))
        if rng: self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        self.end_headers()
        with open(f, 'rb') as fh:
            fh.seek(start)
            remaining = length
            while remaining > 0:
                chunk = fh.read(min(65536, remaining))
                if not chunk: break
                try: self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError): return
                remaining -= len(chunk)

    def do_POST(self):
        if urlparse(self.path).path != '/api/state': return self._send(404, b'nope', 'text/plain')
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])) or '{}')
        s = state()
        name = body.get('name')
        if not name: return self._send(400, json.dumps({'error': 'name required'}))
        rec = s['labels'].get(name, {'status': 'none', 'colors': [], 'notes': '', 'url': None, 'added': False})
        for k in ('status', 'colors', 'notes', 'url', 'added'):
            if k in body: rec[k] = body[k]
        s['labels'][name] = rec
        save(s)
        self._send(200, json.dumps(rec))

def prewarm():
    """Transcode AIFFs ahead of time so the first click on a track is instant."""
    todo = [t['path'] for t in data()['tracks']
            if t['exists'] and not t['path'].lower().endswith('.mp3')]
    todo = [p for p in todo if not os.path.exists(os.path.join(CACHE, hashlib.md5(p.encode()).hexdigest() + '.mp3'))]
    if not todo: return
    print(f'  warming {len(todo)} tracks in background...')
    for n, p in enumerate(todo, 1):
        audio_file(p)
        if n % 25 == 0: print(f'  warmed {n}/{len(todo)}')
    print('  audio cache warm')

if __name__ == '__main__':
    if not os.path.exists(os.path.join(HERE, 'data.json')):
        raise SystemExit('no data.json — run: python3 build.py')
    threading.Thread(target=prewarm, daemon=True).start()
    print(f'SetTheory -> http://localhost:{PORT}   (ctrl-c to stop)')
    ThreadingHTTPServer(('127.0.0.1', PORT), H).serve_forever()
