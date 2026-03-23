# Morning Briefing

## What this is

An Oura Ring-triggered morning briefing that displays a full-screen dashboard on wake-up. Runs as a systemd user service polling Oura every 15 minutes, with a noon fallback.

## Architecture

- **Static HTML template** (`briefing_template.html`) — Python fills in `string.Template` `$variables`. All layout/design changes go here.
- **Python fetches all data** — Oura (sleep, readiness, resilience, activity), OpenMeteo weather, Wikipedia "On This Day", RSS news headlines, Google Calendar via MCP.
- **Claude CLI (`claude -p --model haiku`)** is used for exactly two things:
  1. Picking the best Wikipedia "On This Day" event based on user interests
  2. Writing a ~75-word summary of that event
- **Calendar** is fetched via a third Claude call using MCP tools (`--allowedTools mcp__claude_ai_Google_Calendar__gcal_list_events`)
- **Display** via Brave in kiosk mode with `systemd-inhibit` to prevent screen sleep

## Key files

- `briefing_generator.py` — Main generator: data fetching, Claude calls, template rendering
- `briefing_template.html` — Static HTML/CSS template with `$variable` placeholders
- `oura_poller.py` — systemd service daemon: polls Oura, detects wake-up, triggers briefing
- `oura_auth.py` — Oura OAuth2 flow (tokens stored in `.morning_briefing/tokens.json`)
- `briefing_display.sh` — Launches Brave kiosk with DPMS wake and idle inhibit
- `config.py` — Secrets and settings (NOT committed, see `config.example.py`)
- `oura-poller.service` — systemd user unit file

## Development conventions

- NixOS environment via `flake.nix` + `.envrc` (direnv)
- Test with `python briefing_generator.py` — outputs to `.morning_briefing/briefing_YYYY-MM-DD.html`
- Display with `./briefing_display.sh .morning_briefing/briefing_YYYY-MM-DD.html`
- User's effective viewport is 2048x1152 (2560x1440 at 1.25x Hyprland scale) — everything must fit without scrolling
- Config changes (interests, calendars, location) go in `config.py`
- Design/layout changes go in `briefing_template.html`
- Keep Claude calls minimal and focused — prefer Python data fetching over Claude generation
