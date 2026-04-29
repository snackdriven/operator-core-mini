#!/usr/bin/env bash

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PLIST_PATH="$HOME/Library/LaunchAgents/com.snackdriven.weaver.plist"
SCRIPT_PATH="$DIR/start-weaver.sh"

echo "=========================================="
echo "Registering Weaver to start on macOS boot"
echo "=========================================="
echo ""

# Ensure the launch agents directory exists
mkdir -p "$HOME/Library/LaunchAgents"

# Create the launchd plist file
cat > "$PLIST_PATH" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.snackdriven.weaver</string>
    <key>ProgramArguments</key>
    <array>
        <string>$SCRIPT_PATH</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>StandardOutPath</key>
    <string>$DIR/../logs/weaver-launchd.log</string>
    <key>StandardErrorPath</key>
    <string>$DIR/../logs/weaver-launchd.err</string>
</dict>
</plist>
EOF

# Ensure the script is executable
chmod +x "$SCRIPT_PATH"

echo "Loading launchd agent..."
# Unload it first just in case it already exists to refresh it
launchctl unload "$PLIST_PATH" 2>/dev/null
launchctl load "$PLIST_PATH"

echo "[SUCCESS] Weaver will now start automatically in the background when you log into macOS."
echo "Plist created at: $PLIST_PATH"
