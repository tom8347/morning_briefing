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

# Stop hypridle FIRST so it can't disable the monitor while we work
systemctl --user stop hypridle.service 2>/dev/null || true

# Re-enable monitor fully (hypridle uses 'hyprctl keyword monitor ... disable'
# which disconnects the monitor entirely — dpms on alone won't fix that)
hyprctl keyword monitor "HDMI-A-1,2560x1440@59.951,0x0,1.25" 2>/dev/null || true
sleep 1
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
