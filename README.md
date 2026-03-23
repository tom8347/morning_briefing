# Morning Briefing

A daily morning dashboard triggered by Oura Ring wake-up detection. Displays sleep/readiness/resilience scores, weather, calendar, news headlines, and a curated "On This Day" historical event — all in a full-screen kiosk window.

![NixOS](https://img.shields.io/badge/NixOS-Flake-blue)

## Features

- **Oura Ring integration** — sleep score, readiness score, resilience trend (4-day sparkline), activity nudge
- **Weather** — current conditions and forecast via OpenMeteo (no API key needed)
- **Google Calendar** — today's events from multiple calendars via MCP
- **On This Day** — Claude picks the most interesting Wikipedia event based on configured interests and writes a summary, with a photo from the article
- **News headlines** — top 3 stories each from BBC News, NYT, and Al Jazeera (clickable)
- **Auto-trigger** — polls Oura every 15 min, fires on wake-up detection (≥4h sleep), noon fallback
- **Kiosk display** — full-screen Brave window with DPMS wake and idle inhibit

## Setup

### Prerequisites

- NixOS with direnv
- [Claude CLI](https://docs.anthropic.com/en/docs/claude-cli) with Pro subscription (for `claude -p`)
- Google Calendar MCP server configured in Claude
- Oura Ring with OAuth2 app registered at https://cloud.ouraring.com/oauth/applications

### Install

```bash
cd ~/Documents/morning_briefing
direnv allow

# Configure
cp config.example.py config.py
# Edit config.py with your Oura credentials, calendar IDs, etc.

# Authenticate with Oura (opens browser)
python oura_poller.py --auth

# Test generation
python briefing_generator.py
./briefing_display.sh .morning_briefing/briefing_$(date +%Y-%m-%d).html
```

### Enable systemd service

```bash
mkdir -p ~/.config/systemd/user
cp oura-poller.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now oura-poller.service

# Check status
systemctl --user status oura-poller.service
journalctl --user -u oura-poller.service -f
```

## Configuration

See `config.example.py` for all options:

- **Oura OAuth2 credentials** — client ID and secret
- **Location** — latitude/longitude for weather
- **Interests** — topics for Wikipedia event curation
- **Calendars** — Google Calendar IDs to display
- **Polling** — minimum sleep hours, fallback time, poll interval
