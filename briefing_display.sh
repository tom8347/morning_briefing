#!/usr/bin/env bash
# Open the morning briefing HTML in Chromium kiosk mode.
# Ensures the screen is on and prevents idle sleep while briefing is showing.
# When Chromium is closed, the idle inhibitor is automatically released.
#
# Usage: ./briefing_display.sh /path/to/briefing.html

HTML_FILE="${1:?Usage: briefing_display.sh <html-file>}"

if [ ! -f "$HTML_FILE" ]; then
    echo "File not found: $HTML_FILE" >&2
    exit 1
fi

# Wake the screen if it's off
hyprctl dispatch dpms on 2>/dev/null || true

# Launch Chromium wrapped in systemd-inhibit so screen stays on.
# When Chromium exits (user dismisses), the inhibitor is released automatically.
exec systemd-inhibit --what=idle --mode=block \
    brave --user-data-dir=/tmp/morning-briefing-brave \
    --password-store=basic \
    --disable-features=KWalletIntegration \
    --ozone-platform=wayland \
    --kiosk --noerrdialogs --disable-infobars "file://$HTML_FILE"
