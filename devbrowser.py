#!/usr/bin/env python3
"""Run JavaScript inside the dev app, in a real browser, from the terminal.

    ./devbrowser.py 'document.querySelectorAll("#cells .cell").length'
    ./devbrowser.py --file probe.js
    ./devbrowser.py --stop

Why this exists: the API is curl-able, but the frontend was not checkable at
all, so "I read the code and it looks right" was the only verification anyone
could offer for an app/ change. Twice that was wrong — a stale-hours bug got
explained away from the source before a browser showed it in ten seconds. This
drives the real DOM: click things, submit forms, read what a human would see.

Like dev.sh, the safe path is the default one: the port is hard-wired to the
throwaway 4398, so this cannot reach the real app on 4322 and cannot write
to your real labels.md. Chrome runs headless against a scratch profile.

Stdlib only, per the no-dependency rule — hence the ~40 lines of WebSocket
framing below. Chrome's DevTools Protocol speaks WebSocket and nothing else.
"""
import base64
import json
import os
import socket
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

DEV_PORT = 4398  # the real app owns 4322; never point this there
CDP_PORT = 9223  # not 9222 — Sessions' devbrowser owns that one
URL = f"http://127.0.0.1:{DEV_PORT}"
PROFILE = Path(__file__).parent / ".devdata" / "chrome-profile"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


class WS:
    """The smallest WebSocket client that can hold a CDP session."""

    def __init__(self, url: str):
        _, rest = url.split("://", 1)
        hostport, path = rest.split("/", 1)
        host, port = hostport.split(":")
        self.sock = socket.create_connection((host, int(port)))
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall(
            f"GET /{path} HTTP/1.1\r\nHost: {hostport}\r\n"
            f"Upgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
            .encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            buf += self.sock.recv(4096)
        self.buf = buf.split(b"\r\n\r\n", 1)[1]
        self.msg_id = 0

    def _send(self, payload: bytes) -> None:
        head = bytearray([0x81])  # FIN + text frame
        n = len(payload)
        if n < 126:
            head.append(0x80 | n)
        elif n < 65536:
            head.append(0x80 | 126)
            head += struct.pack(">H", n)
        else:
            head.append(0x80 | 127)
            head += struct.pack(">Q", n)
        mask = os.urandom(4)  # clients must mask; servers must not
        head += mask
        self.sock.sendall(bytes(head)
                          + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))

    def _read(self, n: int) -> bytes:
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise EOFError("browser closed the connection")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def recv(self) -> dict:
        """Read frames until a text one arrives, skipping pings/pongs."""
        while True:
            b0, b1 = self._read(2)
            length = b1 & 0x7F
            if length == 126:
                length = struct.unpack(">H", self._read(2))[0]
            elif length == 127:
                length = struct.unpack(">Q", self._read(8))[0]
            data = self._read(length)
            if b0 & 0x0F == 1:  # text
                return json.loads(data)

    def call(self, method: str, **params) -> dict:
        self.msg_id += 1
        self._send(json.dumps(
            {"id": self.msg_id, "method": method, "params": params}).encode())
        while True:  # CDP interleaves events with replies; wait for ours
            msg = self.recv()
            if msg.get("id") == self.msg_id:
                return msg


def chrome_running() -> bool:
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json", timeout=1)
        return True
    except (urllib.error.URLError, OSError):
        return False


def start_chrome() -> None:
    if not Path(CHROME).exists():
        sys.exit(f"Chrome not found at {CHROME}")
    PROFILE.mkdir(parents=True, exist_ok=True)
    subprocess.Popen(
        [CHROME, "--headless=new", "--disable-gpu", "--no-first-run",
         f"--remote-debugging-port={CDP_PORT}",
         f"--user-data-dir={PROFILE}", URL],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        if chrome_running():
            return
        time.sleep(0.2)
    sys.exit("Chrome did not come up")


def stop_chrome() -> None:
    # By CDP port, not by process name: pkill -f "Google Chrome" would take the
    # user's own browser down with it, which is dev.sh's lesson in another form.
    subprocess.run(["pkill", "-f", f"remote-debugging-port={CDP_PORT}"],
                   check=False)
    print("Stopped the dev browser.")


def page() -> WS:
    targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json"))
    for t in targets:
        if t["type"] == "page":
            ws = WS(t["webSocketDebuggerUrl"])
            ws.call("Runtime.enable")
            return ws
    sys.exit("no page target in the dev browser")


def evaluate(ws: WS, expression: str):
    """Run an expression in the page; await it if it returns a promise."""
    reply = ws.call("Runtime.evaluate", expression=expression,
                    awaitPromise=True, returnByValue=True, userGesture=True)
    result = reply.get("result", {})
    if "exceptionDetails" in result:
        detail = result["exceptionDetails"]
        text = (detail.get("exception", {}).get("description")
                or detail.get("text", "unknown error"))
        sys.exit(f"JS threw:\n{text}")
    return result.get("result", {}).get("value")


def main() -> None:
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        sys.exit(__doc__)
    if args[0] == "--stop":
        return stop_chrome()

    expression = (Path(args[1]).read_text(encoding="utf-8")
                  if args[0] == "--file" else args[0])

    try:
        urllib.request.urlopen(URL, timeout=2)
    except (urllib.error.URLError, OSError):
        sys.exit(f"No dev server at {URL} — run ./dev.sh first.")

    if not chrome_running():
        start_chrome()
    ws = page()
    # Reload so each run sees the app.js currently on disk, not the copy this
    # long-lived headless window loaded three edits ago. (That exact staleness,
    # in the user's own window, is what this tool was written to catch.)
    ws.call("Page.enable")
    ws.call("Page.navigate", url=URL)
    time.sleep(1)
    value = evaluate(ws, expression)
    print(value if isinstance(value, str) else json.dumps(value, indent=2))


if __name__ == "__main__":
    main()
