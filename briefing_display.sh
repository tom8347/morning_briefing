#!/usr/bin/env bash
# Open the morning briefing HTML in Brave kiosk mode.
# Prevents idle sleep while briefing is showing.
# When Brave is closed, the idle inhibitor is automatically released.
#
# Usage: ./briefing_display.sh /path/to/briefing.html

HTML_FILE="${1:?Usage: briefing_display.sh <html-file>}"

if [ ! -f "$HTML_FILE" ]; then
    echo "File not found: $HTML_FILE" >&2
    exit 1
fi

exec systemd-inhibit --what=idle --mode=block \
    brave --user-data-dir=/tmp/morning-briefing-brave \
    --password-store=basic \
    --disable-features=KWalletIntegration \
    --ozone-platform=wayland \
    --kiosk --noerrdialogs --disable-infobars "file://$HTML_FILE"
