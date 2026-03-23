"""
Morning briefing generator.

Architecture:
- Python fetches all data (Oura, weather, Wikipedia, calendar)
- Claude is called ONCE: pick best wiki event, write summary, generate SVG cartoon
- Python fills a static HTML template with all values
"""

import json
import os
import subprocess
import sys
from datetime import date, datetime, timedelta
from string import Template

import requests

import config
from oura_auth import get_access_token

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_DIR = os.path.join(PROJECT_DIR, ".morning_briefing")
TEMPLATE_PATH = os.path.join(PROJECT_DIR, "briefing_template.html")
OURA_BASE = "https://api.ouraring.com"

# Weather code descriptions (WMO)
WEATHER_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Foggy", 48: "Depositing rime fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
    80: "Slight showers", 81: "Moderate showers", 82: "Violent showers",
    95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Thunderstorm with heavy hail",
}


# ── Data Fetching ──

def _oura_get(access_token, endpoint, params):
    headers = {"Authorization": f"Bearer {access_token}"}
    resp = requests.get(f"{OURA_BASE}/v2/usercollection/{endpoint}",
                        headers=headers, params=params)
    if resp.ok:
        return resp.json().get("data", [])
    print(f"  Oura {endpoint}: {resp.status_code}")
    return []


def fetch_oura_sleep(access_token, today):
    data = _oura_get(access_token, "daily_sleep",
                     {"start_date": today, "end_date": today})
    return data[0] if data else None


def fetch_oura_readiness(access_token, today):
    data = _oura_get(access_token, "daily_readiness",
                     {"start_date": today, "end_date": today})
    return data[0] if data else None


def fetch_oura_resilience(access_token, today):
    start = (date.today() - timedelta(days=3)).strftime("%Y-%m-%d")
    data = _oura_get(access_token, "daily_resilience",
                     {"start_date": start, "end_date": today})
    result = []
    for d in data:
        c = d.get("contributors", {})
        vals = [v for v in [c.get("sleep_recovery"), c.get("daytime_recovery"),
                            c.get("stress")] if v is not None]
        mean = round(sum(vals) / len(vals), 1) if vals else None
        result.append({"day": d["day"], "score": mean})
    return result


def fetch_oura_activity(access_token):
    end = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    start = (date.today() - timedelta(days=2)).strftime("%Y-%m-%d")
    return _oura_get(access_token, "daily_activity",
                     {"start_date": start, "end_date": end})


def check_activity_nudge(activity_data):
    if len(activity_data) < 2:
        return False
    for d in activity_data:
        active = d.get("active_calories", 0)
        target = d.get("target_calories", 0)
        if target <= 0 or active >= target:
            return False
    return True


def fetch_weather():
    params = {
        "latitude": config.LATITUDE,
        "longitude": config.LONGITUDE,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weathercode",
        "current_weather": "true",
        "timezone": "auto",
        "forecast_days": 1,
    }
    resp = requests.get("https://api.open-meteo.com/v1/forecast", params=params)
    return resp.json() if resp.ok else None


def fetch_wikipedia_on_this_day():
    now = date.today()
    url = f"https://en.wikipedia.org/api/rest_v1/feed/onthisday/events/{now.month:02d}/{now.day:02d}"
    resp = requests.get(url, headers={"User-Agent": "MorningBriefing/1.0"})
    if not resp.ok:
        return []
    events = resp.json().get("events", [])
    result = []
    for e in events[:30]:
        # Get the best extract — last page is usually the specific event article
        extract = ""
        pages = e.get("pages", [])
        if pages:
            extract = pages[-1].get("extract", "") or pages[0].get("extract", "")
        result.append({
            "year": e.get("year"),
            "text": e.get("text"),
            "extract": extract,
            "pages": e.get("pages", []),
        })
    return result


def fetch_news_headlines():
    """Scrape top headlines from BBC News, NYT, and Al Jazeera RSS feeds."""
    feeds = {
        "BBC": "https://feeds.bbci.co.uk/news/rss.xml",
        "NYT": "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
        "Al Jazeera": "https://www.aljazeera.com/xml/rss/all.xml",
    }
    import xml.etree.ElementTree as ET
    headlines = {}
    for source, url in feeds.items():
        try:
            resp = requests.get(url, timeout=10, headers={"User-Agent": "MorningBriefing/1.0"})
            if not resp.ok:
                headlines[source] = []
                continue
            root = ET.fromstring(resp.content)
            items = root.findall(".//item")[:3]
            headlines[source] = []
            for item in items:
                title_el = item.find("title")
                link_el = item.find("link")
                if title_el is not None and title_el.text:
                    headlines[source].append({
                        "title": title_el.text,
                        "url": link_el.text if link_el is not None else "",
                    })
        except Exception as e:
            print(f"  News fetch failed for {source}: {e}")
            headlines[source] = []
    return headlines


def format_news_html(headlines):
    if not any(headlines.values()):
        return '<div class="schedule-empty">Headlines unavailable</div>'
    parts = []
    for source, articles in headlines.items():
        if articles:
            items = ""
            for a in articles:
                title = a["title"]
                url = a.get("url", "")
                if url:
                    items += f'<li><a href="{url}" target="_blank">{title}</a></li>'
                else:
                    items += f"<li>{title}</li>"
            parts.append(f'<div class="news-source">{source}</div><ul class="news-list">{items}</ul>')
    return "\n".join(parts)


def fetch_calendar_via_claude(today):
    """Small Claude call to fetch calendar events via MCP."""
    calendar_ids = json.dumps(config.CALENDARS, indent=2)
    prompt = f"""Fetch today's events from these Google Calendars using gcal_list_events:
{calendar_ids}
Use timeMin="{today}T00:00:00", timeMax="{today}T23:59:59", timeZone="Europe/London".
Return ONLY JSON: {{"Main": [events], "Birthdays": [events], "Flom": [events]}}
Each event: {{"summary": "...", "start": "HH:MM" or "all-day", "allDay": bool}}
Empty calendar = empty array. No fences, no explanation."""

    result = subprocess.run(
        ["claude", "-p", "--model", "haiku",
         "--allowedTools", "mcp__claude_ai_Google_Calendar__gcal_list_events"],
        input=prompt, capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        return {name: [] for name in config.CALENDARS}
    text = result.stdout.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[-1].strip() == "```":
            lines = lines[1:-1]
        text = "\n".join(lines)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {name: [] for name in config.CALENDARS}


# ── Claude Calls: Wiki pick → Summary → Cartoon ──

def _claude(prompt, model="haiku", timeout=90, allowed_tools=None):
    """Run a claude -p call. Returns stdout or None on failure."""
    cmd = ["claude", "-p", "--model", model]
    if allowed_tools:
        cmd += ["--allowedTools", allowed_tools]
    try:
        result = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        print(f"  Claude call timed out ({timeout}s)")
        return None
    if result.returncode != 0:
        print(f"  Claude call failed: {result.stderr[:200]}")
        return None
    text = result.stdout.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[-1].strip() == "```":
            lines = lines[1:-1]
        text = "\n".join(lines)
    return text


def wiki_pick_event(wikipedia_events):
    """Call 1: Claude picks the most interesting event."""
    events_brief = [{"year": e["year"], "text": e["text"]} for e in wikipedia_events]
    prompt = f"""From these Wikipedia "On This Day" events, pick the ONE most interesting for someone who loves {config.INTERESTS}.

{json.dumps(events_brief)}

Return ONLY the year as a number, nothing else."""

    text = _claude(prompt)
    if text:
        try:
            year = int(text.strip())
            for e in wikipedia_events:
                if e["year"] == year:
                    return e
        except ValueError:
            pass
    return wikipedia_events[0] if wikipedia_events else None


def wiki_write_summary(event):
    """Call 2: Claude writes a 150-word summary from the full wiki blurb."""
    if not event:
        return {"year": "", "title": "", "summary": ""}

    extract = (event.get("extract") or "")[:800]
    prompt = f"""Write a 75-word engaging summary of this historical event for a morning briefing dashboard.

Event ({event['year']}): {event['text']}

Background: {extract}

Return ONLY valid JSON (no fences): {{"year": {event['year']}, "title": "Short title under 60 chars", "summary": "Your 75-word summary here."}}"""

    text = _claude(prompt)
    if text:
        try:
            data = json.loads(text)
            if "summary" in data:
                return data
        except json.JSONDecodeError:
            pass
    return {"year": event["year"], "title": event["text"][:60], "summary": event["text"]}


def wiki_get_image(event):
    """Get the best image URL from the Wikipedia event's pages."""
    if not event:
        return ""
    pages = event.get("pages", [])
    # Prefer the first page's original image (the specific event article)
    for p in pages:
        orig = p.get("originalimage", {}).get("source", "")
        if orig:
            return orig
    # Fall back to thumbnail
    for p in pages:
        thumb = p.get("thumbnail", {}).get("source", "")
        if thumb:
            return thumb
    return ""


# ── Formatting Helpers ──

def _score_color(score):
    if score is None:
        return "#8a7e74"
    if score >= 85:
        return "#3d8b37"
    if score >= 70:
        return "#c28a1f"
    return "#c44d4d"


SLEEP_CONTRIBUTOR_NAMES = {
    "deep_sleep": "Deep sleep", "efficiency": "Efficiency", "latency": "Latency",
    "rem_sleep": "REM", "restfulness": "Restfulness", "timing": "Timing",
    "total_sleep": "Total sleep",
}

READINESS_CONTRIBUTOR_NAMES = {
    "activity_balance": "Activity bal.", "body_temperature": "Body temp",
    "hrv_balance": "HRV balance", "previous_day_activity": "Prev. activity",
    "previous_night": "Prev. night", "recovery_index": "Recovery",
    "resting_heart_rate": "Resting HR", "sleep_balance": "Sleep bal.",
    "sleep_regularity": "Sleep reg.",
}


def _format_subs(contributors, name_map):
    if not contributors:
        return ""
    parts = []
    for key, label in name_map.items():
        val = contributors.get(key)
        if val is not None and val < 85:
            color = _score_color(val)
            parts.append(f'<span style="color:{color}">{label}: {val}</span>')
    return "<br>".join(parts)


def format_weather_html(weather):
    if not weather:
        return '<div class="weather-info"><em>Weather unavailable</em></div>'
    current = weather.get("current_weather", {})
    daily = weather.get("daily", {})
    temp = current.get("temperature", "?")
    code = current.get("weathercode", 0)
    desc = WEATHER_CODES.get(code, "")
    hi = daily.get("temperature_2m_max", ["?"])[0]
    lo = daily.get("temperature_2m_min", ["?"])[0]
    precip = daily.get("precipitation_sum", [0])[0]
    precip_str = f"<br><span class='weather-detail'>Rain: {precip}mm</span>" if precip and precip > 0 else ""
    return f'''<div class="weather-info">
  <div class="weather-temp">{temp}°C</div>
  <span class="weather-detail">{desc}</span><br>
  <span class="weather-detail">H: {hi}° &nbsp; L: {lo}°</span>
  {precip_str}
</div>'''


def format_schedule_html(calendar_events):
    all_events = []
    for cal_name, events in calendar_events.items():
        for e in events:
            e["_cal"] = cal_name
            all_events.append(e)

    if not all_events:
        return '<div class="schedule-empty">Nothing scheduled today</div>'

    # All-day first, then by start time
    allday = [e for e in all_events if e.get("allDay")]
    timed = [e for e in all_events if not e.get("allDay")]
    timed.sort(key=lambda e: e.get("start", ""))

    items = []
    for e in allday + timed:
        time_str = "All day" if e.get("allDay") else e.get("start", "")
        summary = e.get("summary", "Untitled")
        cal = e.get("_cal", "")
        items.append(f'<li><span class="schedule-time">{time_str}</span>'
                     f'{summary} <span class="schedule-cal">({cal})</span></li>')
    return f'<ul class="schedule-list">{"".join(items)}</ul>'


def generate_resilience_svg(data):
    """Generate an inline SVG sparkline for resilience trend."""
    scores = [(d["day"], d["score"]) for d in data if d.get("score") is not None]
    if len(scores) < 2:
        return '<span style="color:#8a7e74;font-size:0.85rem">Insufficient data</span>'

    # Layout
    w, h = 240, 110
    pad_x, pad_top, pad_bot = 30, 15, 30
    plot_w = w - 2 * pad_x
    plot_h = h - pad_top - pad_bot

    vals = [s for _, s in scores]
    y_min = min(vals) - 5
    y_max = max(vals) + 5
    y_range = y_max - y_min if y_max != y_min else 1

    n = len(scores)
    step = plot_w / (n - 1) if n > 1 else 0

    points = []
    for i, (day_str, score) in enumerate(scores):
        x = pad_x + i * step
        y = pad_top + plot_h - ((score - y_min) / y_range) * plot_h
        points.append((x, y, day_str, score))

    # Build SVG
    polyline_pts = " ".join(f"{x:.0f},{y:.0f}" for x, y, _, _ in points)
    day_names = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri", 5: "Sat", 6: "Sun"}

    svg = f'<svg viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}">'
    svg += f'<polyline points="{polyline_pts}" fill="none" stroke="#8a7e74" stroke-width="2.5" stroke-linejoin="round"/>'

    for x, y, day_str, score in points:
        color = _score_color(score)
        dt = datetime.strptime(day_str, "%Y-%m-%d")
        day_abbr = day_names[dt.weekday()]
        svg += f'<circle cx="{x:.0f}" cy="{y:.0f}" r="5" fill="{color}"/>'
        svg += f'<text x="{x:.0f}" y="{h - 5}" text-anchor="middle" font-size="11" fill="#6b5e54">{day_abbr}</text>'
        svg += f'<text x="{x:.0f}" y="{y - 10:.0f}" text-anchor="middle" font-size="11" font-weight="600" fill="{color}">{score:.0f}</text>'

    svg += '</svg>'
    return svg


# ── Main Generator ──

def generate_briefing(oura_data=None):
    today = date.today().strftime("%Y-%m-%d")
    os.makedirs(STATE_DIR, exist_ok=True)

    print("Fetching weather...")
    weather = fetch_weather()

    print("Fetching Wikipedia 'On This Day'...")
    wikipedia_events = fetch_wikipedia_on_this_day()

    print("Fetching news headlines...")
    news_headlines = fetch_news_headlines()

    print("Fetching calendar events...")
    calendar_events = fetch_calendar_via_claude(today)

    if oura_data is None:
        oura_data = {}
        try:
            token = get_access_token(config.OURA_CLIENT_ID, config.OURA_CLIENT_SECRET)
            print("Fetching Oura data...")
            oura_data["sleep"] = fetch_oura_sleep(token, today)
            oura_data["readiness"] = fetch_oura_readiness(token, today)
            oura_data["resilience"] = fetch_oura_resilience(token, today)
            activity = fetch_oura_activity(token)
            oura_data["activity_nudge"] = check_activity_nudge(activity)
        except Exception as e:
            print(f"Failed to fetch Oura data: {e}")

    sleep = oura_data.get("sleep")
    readiness = oura_data.get("readiness")
    resilience = oura_data.get("resilience", [])
    activity_nudge = oura_data.get("activity_nudge", False)

    print("Claude: picking On This Day event...")
    chosen_event = wiki_pick_event(wikipedia_events)

    print("Claude: writing summary...")
    wiki = wiki_write_summary(chosen_event)

    print("Fetching Wikipedia image...")
    wiki_image_url = wiki_get_image(chosen_event)

    # Build template values
    sleep_score = sleep.get("score", "—") if sleep else "—"
    sleep_contribs = sleep.get("contributors", {}) if sleep else {}
    readiness_score = readiness.get("score", "—") if readiness else "—"
    readiness_contribs = readiness.get("contributors", {}) if readiness else {}

    today_dt = date.today()
    date_formatted = today_dt.strftime("%A %-d %B %Y")

    values = {
        "date_formatted": date_formatted,
        "sleep_score": sleep_score,
        "sleep_color": _score_color(sleep_score if isinstance(sleep_score, (int, float)) else None),
        "sleep_subs": _format_subs(sleep_contribs, SLEEP_CONTRIBUTOR_NAMES),
        "readiness_score": readiness_score,
        "readiness_color": _score_color(readiness_score if isinstance(readiness_score, (int, float)) else None),
        "readiness_subs": _format_subs(readiness_contribs, READINESS_CONTRIBUTOR_NAMES),
        "resilience_svg": generate_resilience_svg(resilience),
        "activity_nudge": '<p class="nudge">You\'ve been a bit sedentary — try to be active today</p>' if activity_nudge else "",
        "weather_html": format_weather_html(weather),
        "schedule_html": format_schedule_html(calendar_events),
        "news_html": format_news_html(news_headlines),
        "wiki_year": wiki.get("year", ""),
        "wiki_title": wiki.get("title", ""),
        "wiki_summary": wiki.get("summary", ""),
        "wiki_svg": f'<img src="{wiki_image_url}" alt="{wiki.get("title", "")}">' if wiki_image_url else "",
    }

    # Render template
    with open(TEMPLATE_PATH) as f:
        template = Template(f.read())
    html = template.safe_substitute(values)

    output_path = os.path.join(STATE_DIR, f"briefing_{today}.html")
    with open(output_path, "w") as f:
        f.write(html)

    print(f"Briefing saved to {output_path}")
    return output_path


if __name__ == "__main__":
    path = generate_briefing()
    if path:
        print(f"Done: {path}")
    else:
        print("Failed to generate briefing.", file=sys.stderr)
        sys.exit(1)
