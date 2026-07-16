#!/bin/zsh
# Builds SetTheory.app — the Dock icon. Its click is the only maintenance there
# is: server down? the click starts it. Server running old code? the click
# restarts it. Window already open? the click focuses it.
#
# Bakes in an absolute path, so it's rebuilt per machine and never committed.
# Run once after cloning: ./make-app.sh
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
APP="$DIR/SetTheory.app"
URL="http://127.0.0.1:4322"

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>SetTheory</string>
  <key>CFBundleDisplayName</key><string>SetTheory</string>
  <key>CFBundleIdentifier</key><string>com.settheory.app</string>
  <key>CFBundleVersion</key><string>1.0</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>SetTheory</string>
  <key>CFBundleIconFile</key><string>app.icns</string>
</dict>
</plist>
PLIST

cat > "$APP/Contents/MacOS/SetTheory" <<EOF
#!/bin/zsh
DIR="$DIR"
URL="$URL"
# If the server fails to start, the reason lands here rather than /dev/null.
LOG="\$HOME/Library/Logs/SetTheory.log"

# Is a server up, AND is it running the code that's on disk? Asking only the
# first question lets a server started before an update stay up forever, quietly
# serving last week's app.
python3 - "\$DIR/settheory.py" "\$URL" <<'PY'
import hashlib, json, sys, urllib.error, urllib.request
src, url = sys.argv[1], sys.argv[2]
try:
    running = json.load(urllib.request.urlopen(url + "/api/version", timeout=2))
except urllib.error.HTTPError:
    sys.exit(3)  # answering but has no /api/version: predates this = stale
except Exception:
    sys.exit(2)  # nothing listening — start one
disk = hashlib.sha256(open(src, "rb").read()).hexdigest()
sys.exit(0 if running.get("source") == disk else 3)
PY
STATUS=\$?

if [ \$STATUS -eq 3 ]; then
  echo "--- \$(date) restarting a stale server ---" >> "\$LOG"
  # By PID from lsof — NEVER by name. \`pkill -f settheory.py\` would also kill a
  # running ./dev.sh, and that class of mistake has taken a real server down.
  for pid in \$(lsof -nP -iTCP:4322 -sTCP:LISTEN -t 2>/dev/null); do kill "\$pid" 2>/dev/null; done
  sleep 0.5
fi
if [ \$STATUS -ne 0 ]; then
  echo "--- \$(date) launching server ---" >> "\$LOG"
  python3 "\$DIR/settheory.py" --no-open >> "\$LOG" 2>&1 &
  for i in {1..30}; do curl -s -o /dev/null "\$URL/api/ping" && break; sleep 0.2; done
  curl -s -o /dev/null "\$URL/api/ping" || echo "server did not answer at \$URL" >> "\$LOG"
fi

# One window, not one per click. \`open -na\` forces a NEW browser instance every
# time, so two clicks means two SetTheory windows onto the same server. Focus the
# one that's already open if there is one.
for B in "Google Chrome" "Microsoft Edge" "Brave Browser"; do
  [ -d "/Applications/\$B.app" ] || continue
  FOUND=\$(osascript 2>/dev/null <<AS
tell application "\$B"
  repeat with w in windows
    repeat with t in tabs of w
      if URL of t starts with "\$URL" then
        set index of w to 1
        activate
        return "ok"
      end if
    end repeat
  end repeat
end tell
return "no"
AS
)
  # "no" = browser running without a SetTheory window; "" = osascript refused
  # (no automation permission yet) — either way, open a fresh app window.
  [ "\$FOUND" = "ok" ] && exit 0
  open -na "/Applications/\$B.app" --args --app="\$URL" && exit 0
done
open "\$URL"
EOF

chmod +x "$APP/Contents/MacOS/SetTheory"

# Build the icon from app/icon.png — three overlapping sets, in the three colours.
ICONSET="$(mktemp -d)/settheory.iconset"
mkdir -p "$ICONSET"
for s in 16 32 64 128 256 512; do
  sips -z $s $s "$DIR/app/icon.png" --out "$ICONSET/icon_${s}x${s}.png" >/dev/null 2>&1
  d=$((s * 2))
  sips -z $d $d "$DIR/app/icon.png" --out "$ICONSET/icon_${s}x${s}@2x.png" >/dev/null 2>&1
done
iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/app.icns" 2>/dev/null || true

echo "Built $APP"
echo "Launch it once (right-click → Open the first time), then right-click its"
echo "Dock icon → Options → Keep in Dock."
