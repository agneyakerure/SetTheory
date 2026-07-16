#!/bin/zsh
# One-time setup. Needs Python 3 and ffmpeg (only if your library is AIFF).
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

command -v ffmpeg >/dev/null || echo "Note: ffmpeg not found — AIFF tracks won't play. brew install ffmpeg"

if [ ! -f .cache/data.json ]; then
  echo "No map yet. Build one first:"
  echo "  python3 build.py https://bandcamp.com/YOURNAME"
  exit 1
fi

./make-app.sh
echo
echo "Done. Launch SetTheory.app (right-click → Open the first time)."
