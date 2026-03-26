#!/usr/bin/env bash
# Open the morning briefing HTML in Brave kiosk mode.
# Suspends hypridle so the screen stays on for the duration.
# When Brave is closed, hypridle is restarted automatically.
#
# Usage: ./briefing_display.sh /path/to/briefing.html

HTML_FILE="${1:?Usage: briefing_display.sh <html-file>}"

if [ ! -f "$HTML_FILE" ]; then
    echo "File not found: $HTML_FILE" >&2
    exit 1
fi

# Stop hypridle so it can't turn the monitor off while briefing is showing
systemctl --user stop hypridle.service 2>/dev/null || true

# Ensure monitor is on
hyprctl dispatch dpms on 2>/dev/null || true

# Launch Brave kiosk — this blocks until Brave exits
systemd-inhibit --what=idle --mode=block \
    brave --user-data-dir=/tmp/morning-briefing-brave \
    --password-store=basic \
    --disable-features=KWalletIntegration \
    --ozone-platform=wayland \
    --kiosk --noerrdialogs --disable-infobars "file://$HTML_FILE"

# Brave has exited — restart hypridle
systemctl --user start hypridle.service 2>/dev/null || true
