#!/usr/bin/env python3
"""
SetTheory — the map a dig starts from.

Pick the colour you're feeling, hear what you already own in it, and see the
labels that colour lives on. Local only; the server never touches the network
(build.py does that, separately and deliberately).

Storage is plain Markdown in ~/Documents/SetTheory/ — same contract as Sessions.
The map itself (data.json) is a derived cache, rebuilt by build.py; your notes
are the only thing here that can't be regenerated.
"""
import json
import os
import re
import subprocess
import sys
import threading
import hashlib
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote

HERE = Path(__file__).resolve().parent
APP = HERE / "app"
CACHE = HERE / ".cache"
AUDIO = CACHE / "audio"
DATA_DIR = Path(os.environ.get("SETTHEORY_DATA_DIR", Path.home() / "Documents" / "SetTheory"))
PORT = int(os.environ.get("SETTHEORY_PORT", "4322"))

LABELS_MD = "labels.md"
STATUSES = ("never", "dipped", "walked")

# A note line that would parse back as file structure. Without this, writing
# "## Fake Label" into a notes box invents a label and silently truncates the
# note you were actually writing. Same guard, same reason, as Sessions' STRUCT_RE.
STRUCT_RE = re.compile(r"^\s*(##\s+\S|\*\*\w+:\*\*)", re.M)

_lock = threading.Lock()


def ensure_data_dir() -> None:
    """Create the data dir on first run and seed it from defaults/."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    seed = HERE / "defaults" / LABELS_MD
    target = DATA_DIR / LABELS_MD
    if not target.exists() and seed.exists():
        target.write_text(seed.read_text(encoding="utf-8"), encoding="utf-8")


# ---------------------------------------------------------------- data layer

def labels_file() -> Path:
    return DATA_DIR / LABELS_MD


def field(text: str, name: str) -> str:
    """Last-wins, like Sessions. Returns '' when absent."""
    hits = re.findall(rf"^\*\*{re.escape(name)}:\*\*[ \t]*(.*)$", text, re.M)
    return hits[-1].strip() if hits else ""


def parse_labels() -> dict:
    """
    labels.md is `## Name` sections, each with **Field:** lines and free prose.
    Anything the app doesn't understand is left alone on rewrite.
    """
    path = labels_file()
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    out = {}
    # split on ## headings; [0] is the file preamble
    parts = re.split(r"^## +(.+?)[ \t]*$", text, flags=re.M)
    for i in range(1, len(parts), 2):
        name = parts[i].strip()
        body = parts[i + 1]
        notes = re.sub(r"^\*\*\w+:\*\*.*$", "", body, flags=re.M).strip()
        colors = [c.strip() for c in field(body, "Colors").split(",") if c.strip()]
        status = field(body, "Status").lower()
        out[name] = {
            "status": status if status in STATUSES else "never",
            "colors": colors,
            "url": field(body, "URL") or None,
            "notes": notes,
            "added": field(body, "Added").lower() == "yes",
        }
    return out


def render_labels(labels: dict) -> str:
    lines = [
        "# Labels",
        "",
        "Where each vibe lives, and what you found there. Plain Markdown — edit it",
        "by hand any time; the app reads it back. `Status` is one of never / dipped /",
        "walked. Anything below the fields is yours to write.",
        "",
    ]
    for name in sorted(labels):
        rec = labels[name]
        lines.append(f"## {name}")
        lines.append(f"**Status:** {rec.get('status') or 'never'}")
        if rec.get("colors"):
            lines.append(f"**Colors:** {', '.join(rec['colors'])}")
        if rec.get("url"):
            lines.append(f"**URL:** {rec['url']}")
        if rec.get("added"):
            lines.append("**Added:** yes")
        notes = (rec.get("notes") or "").strip()
        if notes:
            lines.append("")
            lines.append(notes)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_labels(labels: dict) -> None:
    """Caller must hold _lock — see set_label. Atomic replace so a crash
       mid-write can't truncate the file."""
    ensure_data_dir()
    tmp = labels_file().with_suffix(".tmp")
    tmp.write_text(render_labels(labels), encoding="utf-8")
    os.replace(tmp, labels_file())


def set_label(name: str, patch: dict) -> dict:
    """Raises ValueError on input that would corrupt labels.md."""
    if "\n" in name or STRUCT_RE.search(name) or name.startswith("#"):
        raise ValueError("a label name can't contain newlines or Markdown structure")
    if STRUCT_RE.search(patch.get("notes") or ""):
        raise ValueError(
            "notes can't contain a '## heading' or '**Field:**' line — "
            "that would parse back as a new label and eat the rest of your note"
        )
    # The whole read-modify-write must be atomic, not just the write. The server
    # is threaded, and clicking a status while a notes box blurs fires two POSTs
    # at once: both would read the old file and the second would silently clobber
    # the first. Caught by driving real clicks — the UI said "walked", the file
    # said "never".
    with _lock:
        labels = parse_labels()
        rec = labels.get(name, {"status": "never", "colors": [], "url": None,
                                "notes": "", "added": False})
        for k in ("status", "colors", "url", "notes", "added"):
            if k in patch:
                rec[k] = patch[k]
        if rec.get("status") not in STATUSES:
            rec["status"] = "never"
        labels[name] = rec
        write_labels(labels)
        return rec


def map_data() -> dict:
    path = CACHE / "data.json"
    if not path.exists():
        return {"colors": [], "energy": [], "tracks": [], "labels": [], "built": None}
    return json.loads(path.read_text(encoding="utf-8"))


def state() -> dict:
    d = map_data()
    d["saved"] = parse_labels()
    d["dataDir"] = str(DATA_DIR)
    return d


# ------------------------------------------------------------------- audio

def audio_file(path: str) -> str | None:
    """Transcode to mp3 once and cache. MP3s pass through untouched."""
    if path.lower().endswith(".mp3"):
        return path
    AUDIO.mkdir(parents=True, exist_ok=True)
    out = AUDIO / (hashlib.md5(path.encode()).hexdigest() + ".mp3")
    if not out.exists():
        r = subprocess.run(["ffmpeg", "-nostdin", "-i", path, "-b:a", "192k", "-y", str(out)],
                           capture_output=True)
        if r.returncode != 0 or not out.exists():
            return None
    return str(out)


def prewarm() -> None:
    """Transcode ahead of time so the first click on a track is instant."""
    todo = [t["path"] for t in map_data().get("tracks", [])
            if t.get("exists") and not t["path"].lower().endswith(".mp3")]
    todo = [p for p in todo
            if not (AUDIO / (hashlib.md5(p.encode()).hexdigest() + ".mp3")).exists()]
    if not todo:
        return
    print(f"  warming {len(todo)} tracks in the background...")
    for n, p in enumerate(todo, 1):
        audio_file(p)
        if n % 25 == 0:
            print(f"  warmed {n}/{len(todo)}")
    print("  audio cache warm")


# ------------------------------------------------------------------- server

MIME = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8", ".png": "image/png", ".svg": "image/svg+xml"}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send_json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        route = u.path
        if route == "/api/state":
            return self.send_json(state())
        if route == "/api/ping":
            return self.send_json({"ok": True, "port": PORT})
        if route == "/audio":
            return self.serve_audio(parse_qs(u.query))
        return self.serve_static(route)

    def serve_static(self, route):
        rel = "index.html" if route == "/" else unquote(route.lstrip("/"))
        path = (APP / rel).resolve()
        if not str(path).startswith(str(APP.resolve())) or not path.is_file():
            return self.send_error(404)
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", MIME.get(path.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def serve_audio(self, q):
        try:
            tid = int(q.get("id", ["-1"])[0])
        except ValueError:
            return self.send_error(400)
        tracks = map_data().get("tracks", [])
        if not (0 <= tid < len(tracks)):
            return self.send_error(404)
        src = tracks[tid]["path"]
        if not os.path.exists(src):
            return self.send_error(404, "file missing on disk")
        f = audio_file(src)
        if not f:
            return self.send_error(500, "transcode failed")
        self.serve_range(f)

    def serve_range(self, f):
        size = os.path.getsize(f)
        rng = self.headers.get("Range")
        start, end = 0, size - 1
        if rng:
            m = re.match(r"bytes=(\d+)-(\d*)", rng)
            if m:
                start = int(m.group(1))
                if m.group(2):
                    end = min(int(m.group(2)), size - 1)
        length = end - start + 1
        self.send_response(206 if rng else 200)
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if rng:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        with open(f, "rb") as fh:
            fh.seek(start)
            left = length
            while left > 0:
                chunk = fh.read(min(65536, left))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    return
                left -= len(chunk)

    def do_POST(self):
        route = urlparse(self.path).path
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or "{}")
        except (ValueError, json.JSONDecodeError):
            return self.send_json({"error": "bad json"}, 400)
        if route != "/api/label":
            return self.send_error(404)
        name = (body.get("name") or "").strip()
        if not name:
            return self.send_json({"error": "name required"}, 400)
        try:
            return self.send_json(set_label(name, body))
        except ValueError as e:
            return self.send_json({"error": str(e)}, 400)


def main():
    ensure_data_dir()
    if not (CACHE / "data.json").exists():
        print("No map yet. Build one first:\n"
              "  python3 build.py https://bandcamp.com/YOURNAME")
        sys.exit(1)
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError:
        print(f"Something already holds port {PORT} — SetTheory may already be running.")
        sys.exit(1)
    threading.Thread(target=prewarm, daemon=True).start()
    url = f"http://127.0.0.1:{PORT}"
    print(f"SetTheory -> {url}")
    print(f"  notes : {DATA_DIR / LABELS_MD}")
    if "--no-open" not in sys.argv:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
