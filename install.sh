#!/bin/bash
# Laat de tracker elke dag om 8u en 18u draaien (macOS launchd).
# launchd start de tracker elke 15 minuten met --gepland; die draait alleen als het laatste
# vaste moment (8u/18u) nog niet gelukt is en er internet is. Sliep je Mac, dan wordt het ingehaald.
#
# macOS laat geplande taken niet in ~/Documents, daarom wordt de code gekopieerd
# naar ~/Library/Application Support/porsche-tracker en draait hij daar.
# => Na het aanpassen van config.json of tracker.py: ./install.sh opnieuw draaien.
#
# Verwijderen: ./install.sh --uninstall
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
APP="$HOME/Library/Application Support/porsche-tracker"
LABEL="be.keypoint.porsche-tracker"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
if [ "$1" = "--uninstall" ]; then rm -f "$PLIST"; echo "Verwijderd (gegevens blijven in $APP)."; exit 0; fi

mkdir -p "$APP" "$HOME/Library/LaunchAgents"
cp "$DIR/tracker.py" "$DIR/config.json" "$DIR/dashboard_template.html" "$APP/"
rm -rf "$APP/bronnen" && mkdir -p "$APP/bronnen" && cp "$DIR"/bronnen/*.py "$APP/bronnen/" 2>/dev/null || true
ln -sfn "$APP/dashboard.html" "$DIR/dashboard.html"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array><string>/usr/bin/python3</string><string>$APP/tracker.py</string><string>--gepland</string></array>
  <key>WorkingDirectory</key><string>$APP</string>
  <key>StartInterval</key><integer>900</integer>
  <key>StartCalendarInterval</key>
  <array>
    <dict><key>Hour</key><integer>8</integer><key>Minute</key><integer>0</integer></dict>
    <dict><key>Hour</key><integer>18</integer><key>Minute</key><integer>0</integer></dict>
  </array>
  <key>StandardOutPath</key><string>$APP/tracker.log</string>
  <key>StandardErrorPath</key><string>$APP/tracker.log</string>
</dict>
</plist>
EOF
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "Geïnstalleerd: draait dagelijks om 08:00 en 18:00 (gemist = ingehaald, check elke 15 min). Dashboard: $DIR/dashboard.html"
