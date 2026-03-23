# Oura OAuth2 credentials
# Register at: https://cloud.ouraring.com/oauth/applications
# Set redirect URI to: http://localhost:8080/callback
OURA_CLIENT_ID = "your-client-id"
OURA_CLIENT_SECRET = "your-client-secret"

# Location for OpenMeteo weather
LATITUDE = 51.5933   # Pinner, London
LONGITUDE = -0.3830

# User interests for Wikipedia "On This Day" curation
INTERESTS = "history, philosophy, theatre, music"

# Google Calendar IDs
CALENDARS = {
    "Main": "primary",
    "Birthdays": "your-birthdays-calendar-id@group.calendar.google.com",
    "Flom": "your-flom-calendar-id@group.calendar.google.com",
}

# Polling settings
MIN_SLEEP_HOURS = 4       # Minimum sleep duration to count as wake-up
FALLBACK_HOUR = 12        # Fire briefing at noon if no Oura data
POLL_INTERVAL_SECONDS = 600  # 10 minutes
