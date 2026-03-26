#!/usr/bin/env python3
"""
Oura wake-up poller — systemd service.

Polls the Oura sleep API every 15 minutes starting at midnight.
When a completed long_sleep session ≥4h is detected, triggers the
morning briefing. Falls back to firing at noon if no Oura data arrives.

Usage:
    python oura_poller.py          # run the polling loop
    python oura_poller.py --once   # single poll cycle (for testing)
    python oura_poller.py --auth   # run OAuth flow only (first-time setup)
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import date, datetime, timedelta

import requests

import config
from oura_auth import get_access_token
from briefing_generator import (fetch_oura_sleep, fetch_oura_readiness,
                                fetch_oura_resilience, fetch_oura_activity,
                                check_activity_nudge, generate_briefing)

STATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".morning_briefing")
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
OURA_BASE = "https://api.ouraring.com"


def flag_path(today):
    return os.path.join(STATE_DIR, f"triggered_{today}")


def already_triggered(today):
    return os.path.exists(flag_path(today))


def mark_triggered(today):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(flag_path(today), "w") as f:
        f.write(datetime.now().isoformat())


def detect_wakeup(access_token, today):
    """Detect wake-up by checking if a long_sleep session has ended today.

    We look at bedtime_end rather than duration — a session that ended
    today means you actually woke up today. Sessions are filed under the
    day sleep started, so we check yesterday and today.
    """
    headers = {"Authorization": f"Bearer {access_token}"}
    yesterday = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    now = datetime.now().astimezone()

    resp = requests.get(f"{OURA_BASE}/v2/usercollection/sleep", headers=headers,
                        params={"start_date": yesterday, "end_date": today})
    if not resp.ok:
        print(f"  Oura API error: {resp.status_code}")
        return False

    sessions = resp.json().get("data", [])
    for s in sessions:
        if s.get("type") != "long_sleep":
            continue
        duration_hours = s.get("total_sleep_duration", 0) / 3600
        if duration_hours < config.MIN_SLEEP_HOURS:
            continue
        bedtime_end_str = s.get("bedtime_end")
        if not bedtime_end_str:
            continue
        # Parse bedtime_end and check it's today
        from datetime import timezone
        bedtime_end = datetime.fromisoformat(bedtime_end_str)
        if bedtime_end.date() != date.today():
            continue
        # Check end time is in the past (session has actually finished)
        if bedtime_end > now:
            continue
        print(f"  Wake-up detected: {duration_hours:.1f}h sleep, woke at {bedtime_end.strftime('%H:%M')}")
        return True

    print(f"  No wake-up yet ({len(sessions)} sessions checked)")
    return False


def wake_screen():
    """Wake the display via hyprctl, auto-detecting Hyprland instance.

    hypridle disables the monitor entirely via 'hyprctl keyword monitor ... disable'
    so we must re-enable it with the full monitor spec, not just dpms on.
    """
    hypr_dir = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/run/user/1000"), "hypr")
    if not os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        try:
            instances = sorted(os.listdir(hypr_dir), key=lambda f: os.path.getmtime(os.path.join(hypr_dir, f)), reverse=True)
            if instances:
                os.environ["HYPRLAND_INSTANCE_SIGNATURE"] = instances[0]
        except OSError:
            pass
    subprocess.run(["hyprctl", "keyword", "monitor", "HDMI-A-1,2560x1440@59.951,0x0,1.25"], capture_output=True)
    subprocess.run(["hyprctl", "dispatch", "dpms", "on"], capture_output=True)


def display_briefing(html_path):
    """Open the briefing in Brave kiosk mode."""
    wake_screen()
    display_script = os.path.join(PROJECT_DIR, "briefing_display.sh")
    subprocess.Popen([display_script, html_path])


def run_briefing(access_token, today):
    """Fetch Oura data and generate the briefing."""
    print("Generating morning briefing...")
    oura_data = {
        "sleep": fetch_oura_sleep(access_token, today),
        "readiness": fetch_oura_readiness(access_token, today),
        "resilience": fetch_oura_resilience(access_token, today),
        "activity_nudge": check_activity_nudge(fetch_oura_activity(access_token)),
    }

    html_path = generate_briefing(oura_data)
    if html_path:
        mark_triggered(today)
        display_briefing(html_path)
        print("Briefing displayed.")
    else:
        print("Briefing generation failed.")


def poll_loop():
    """Main polling loop."""
    print("Morning briefing poller started.")
    print(f"  Poll interval: {config.POLL_INTERVAL_SECONDS}s")
    print(f"  Min sleep: {config.MIN_SLEEP_HOURS}h")
    print(f"  Fallback: {config.FALLBACK_HOUR}:00")

    while True:
        today = date.today().strftime("%Y-%m-%d")
        now = datetime.now()

        if already_triggered(today):
            # Already fired today — sleep until next poll
            time.sleep(config.POLL_INTERVAL_SECONDS)
            continue

        if now.hour < config.EARLIEST_HOUR:
            print(f"[{now.strftime('%H:%M')}] Too early (before {config.EARLIEST_HOUR}:00), sleeping...")
            time.sleep(config.POLL_INTERVAL_SECONDS)
            continue

        print(f"[{now.strftime('%H:%M')}] Polling Oura...")

        try:
            access_token = get_access_token(config.OURA_CLIENT_ID, config.OURA_CLIENT_SECRET)

            if detect_wakeup(access_token, today):
                run_briefing(access_token, today)
            elif now.hour >= config.FALLBACK_HOUR:
                print(f"  Fallback triggered (past {config.FALLBACK_HOUR}:00)")
                run_briefing(access_token, today)
            else:
                print(f"  Waiting... (fallback at {config.FALLBACK_HOUR}:00)")
        except Exception as e:
            print(f"  Error: {e}")

        time.sleep(config.POLL_INTERVAL_SECONDS)


def main():
    parser = argparse.ArgumentParser(description="Morning briefing Oura poller")
    parser.add_argument("--once", action="store_true", help="Run a single poll cycle")
    parser.add_argument("--auth", action="store_true", help="Run OAuth flow only (first-time setup)")
    args = parser.parse_args()

    os.makedirs(STATE_DIR, exist_ok=True)

    if args.auth:
        token = get_access_token(config.OURA_CLIENT_ID, config.OURA_CLIENT_SECRET)
        print(f"Auth OK. Token: {token[:20]}...")
        return

    if args.once:
        today = date.today().strftime("%Y-%m-%d")
        if already_triggered(today):
            print("Already triggered today.")
            return
        try:
            access_token = get_access_token(config.OURA_CLIENT_ID, config.OURA_CLIENT_SECRET)
            if detect_wakeup(access_token, today):
                run_briefing(access_token, today)
            else:
                print("No wake-up detected.")
        except Exception as e:
            print(f"Error: {e}")
        return

    poll_loop()


if __name__ == "__main__":
    main()
