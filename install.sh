#!/bin/bash
# SlackPulse Install Script
# Installs SlackPulse and registers it to start on login

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST_NAME="com.slackpulse.agent.plist"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"

echo "=== SlackPulse Installer ==="
echo ""

# Check for Python 3
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is required but not found."
    exit 1
fi

# Create virtual environment if needed
if [ ! -d "$SCRIPT_DIR/.venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$SCRIPT_DIR/.venv"
fi

# Install dependencies
echo "Installing dependencies..."
"$SCRIPT_DIR/.venv/bin/pip" install -q -e "$SCRIPT_DIR"

# Create LaunchAgents directory if needed
mkdir -p "$LAUNCH_AGENTS_DIR"

# Generate plist with correct paths
echo "Creating launch agent..."
cat > "$LAUNCH_AGENTS_DIR/$PLIST_NAME" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.slackpulse.agent</string>

    <key>ProgramArguments</key>
    <array>
        <string>$SCRIPT_DIR/.venv/bin/python</string>
        <string>-m</string>
        <string>slackpulse</string>
    </array>

    <key>WorkingDirectory</key>
    <string>$SCRIPT_DIR</string>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <true/>

    <key>StandardOutPath</key>
    <string>/tmp/slackpulse.out.log</string>

    <key>StandardErrorPath</key>
    <string>/tmp/slackpulse.err.log</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PYTHONPATH</key>
        <string>$SCRIPT_DIR</string>
    </dict>
</dict>
</plist>
EOF

# Unload if already loaded
launchctl unload "$LAUNCH_AGENTS_DIR/$PLIST_NAME" 2>/dev/null || true

# Load the launch agent
echo "Loading launch agent..."
launchctl load "$LAUNCH_AGENTS_DIR/$PLIST_NAME"

echo ""
echo "=== Installation Complete ==="
echo ""
echo "SlackPulse will now start automatically on login."
echo ""
echo "Commands:"
echo "  Check status:  launchctl list | grep slackpulse"
echo "  View logs:     tail -f /tmp/slackpulse.out.log"
echo "  Stop:          launchctl unload ~/Library/LaunchAgents/$PLIST_NAME"
echo "  Start:         launchctl load ~/Library/LaunchAgents/$PLIST_NAME"
echo "  Uninstall:     ./uninstall.sh"
echo ""
echo "Don't forget to:"
echo "  1. Grant Full Disk Access to Terminal/Python in System Settings"
echo "  2. Configure ~/.config/slackpulse/config.toml (see README)"
