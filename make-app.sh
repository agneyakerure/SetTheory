#!/bin/zsh
# Builds SetTheory.app — a Dock icon that starts the local server if it isn't
# running, then opens the app in its own window. Bakes in an absolute path, so
# it's rebuilt per machine and never committed.
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
APP="$DIR/SetTheory.app"
URL="http://127.0.0.1:4322"

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS"

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
</dict>
</plist>
PLIST

cat > "$APP/Contents/MacOS/SetTheory" <<LAUNCH
#!/bin/zsh
cd "$DIR"
if ! curl -s -o /dev/null "$URL/api/ping"; then
  python3 settheory.py --no-open > "$DIR/.cache/server.log" 2>&1 &
  for i in {1..40}; do curl -s -o /dev/null "$URL/api/ping" && break; sleep 0.25; done
fi
open -na "Google Chrome" --args --app="$URL" 2>/dev/null || open "$URL"
LAUNCH

chmod +x "$APP/Contents/MacOS/SetTheory"
echo "Built $APP"
echo "Right-click → Open the first time, then keep it in the Dock."
