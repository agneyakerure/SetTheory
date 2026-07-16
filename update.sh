#!/bin/zsh
# Pull changes made elsewhere and restart the server so new logic takes effect.
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
git pull --ff-only
PID=$(lsof -nP -iTCP:4322 -sTCP:LISTEN -t 2>/dev/null || true)
[ -n "$PID" ] && { kill "$PID"; echo "Stopped server (pid $PID)."; }
echo "Updated. Click SetTheory.app to start it again."
