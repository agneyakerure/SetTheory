#!/bin/zsh
# Run SetTheory for development — throwaway port, throwaway notes.
#
#   ./dev.sh          start (or restart) the dev server
#   ./dev.sh stop     stop it
#   ./dev.sh fresh    wipe the scratch notes and start clean
#
# Same two rules Sessions learned the hard way, encoded here so the safe path is
# the default one: the port and data dir are hard-wired to throwaway values, and
# stopping goes by recorded PID — never by matching a process name, which would
# also match your real server.
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

DEV_PORT=4398                  # the real app owns 4322; never use it here
DEV_DATA="$DIR/.devdata"
PIDFILE="$DEV_DATA/dev.pid"
URL="http://127.0.0.1:$DEV_PORT"

stop_dev() {
  if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    kill "$(cat "$PIDFILE")" 2>/dev/null || true
    echo "Stopped dev server (pid $(cat "$PIDFILE"))."
  else
    echo "No dev server running."
  fi
  rm -f "$PIDFILE"
  # Wait for the port to actually come free. Killing the process and checking
  # lsof in the next breath is a race: the socket lingers, the check below sees
  # it as taken, and a restart refuses to start for no reason.
  for i in {1..20}; do
    lsof -nP -iTCP:$DEV_PORT -sTCP:LISTEN >/dev/null 2>&1 || break
    sleep 0.1
  done
}

case "${1:-start}" in
  stop)  stop_dev; exit 0 ;;
  fresh) stop_dev; rm -rf "$DEV_DATA"; echo "Wiped $DEV_DATA." ;;
  start) stop_dev >/dev/null 2>&1 || true ;;
  *)     echo "usage: ./dev.sh [start|stop|fresh]"; exit 1 ;;
esac

mkdir -p "$DEV_DATA"

# Refuse rather than no-op: if something else holds the dev port, every request
# below would be answered by whatever that is.
if lsof -nP -iTCP:$DEV_PORT -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Port $DEV_PORT is already in use. Refusing to start."
  exit 1
fi

SETTHEORY_DATA_DIR="$DEV_DATA" SETTHEORY_PORT=$DEV_PORT \
  python3 settheory.py --no-open > "$DEV_DATA/dev.log" 2>&1 &
echo $! > "$PIDFILE"

for i in {1..40}; do curl -s -o /dev/null "$URL/api/ping" && break; sleep 0.25; done

if curl -s -o /dev/null "$URL/api/ping"; then
  echo "Dev server running at $URL  (pid $(cat "$PIDFILE"))"
  echo "  notes : $DEV_DATA    (throwaway — your real labels.md is untouched)"
  echo "  log   : $DEV_DATA/dev.log"
  echo "  stop  : ./dev.sh stop"
else
  echo "Dev server failed to start. Log:"; cat "$DEV_DATA/dev.log"; rm -f "$PIDFILE"; exit 1
fi
