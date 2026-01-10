#!/bin/bash
# SlackPulse Uninstall Script
# Stops and removes the launch agent

PLIST_NAME="com.slackpulse.agent.plist"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"

echo "=== SlackPulse Uninstaller ==="
echo ""

# Unload the launch agent
if [ -f "$LAUNCH_AGENTS_DIR/$PLIST_NAME" ]; then
    echo "Stopping SlackPulse..."
    launchctl unload "$LAUNCH_AGENTS_DIR/$PLIST_NAME" 2>/dev/null || true

    echo "Removing launch agent..."
    rm "$LAUNCH_AGENTS_DIR/$PLIST_NAME"

    echo ""
    echo "SlackPulse has been uninstalled."
    echo "The source code and config remain - delete manually if needed:"
    echo "  rm -rf $(cd "$(dirname "$0")" && pwd)"
    echo "  rm -rf ~/.config/slackpulse"
else
    echo "SlackPulse is not installed as a launch agent."
fi
