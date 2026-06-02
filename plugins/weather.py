"""Weather plugin using wttr.in."""
import requests, re

NAME        = "weather"
TRIGGERS    = ["weather in", "weather for", "weather today", "check the weather",
               "what's the weather", "whats the weather", "temperature in",
               "temperature today", "forecast for", "will it rain", "will it snow",
               "humidity in", "wind speed in"]
# Removed bare "rain","snow","sunny","cloudy" — too broad, fire on non-weather sentences
DESCRIPTION = "Gets current weather for any location using wttr.in (free, no API key)"
MANUAL_ONLY = False

def run(query: str, context: dict) -> str:
    text = context["user_input"]
    # Try to extract a location
    loc_match = re.search(
        r'weather\s+(?:in|for|at)?\s+([a-zA-Z\s,]+?)(?:\?|$|\.)',
        text, re.IGNORECASE)
    location = loc_match.group(1).strip() if loc_match else ""
    if not location:
        # Check for "run weather <location>"
        run_match = re.search(r'run\s+weather\s+(.+)', text, re.IGNORECASE)
        location = run_match.group(1).strip() if run_match else ""
    if not location:
        return "Please specify a location, e.g. 'weather in London'"
    try:
        resp = requests.get(
            f"https://wttr.in/{requests.utils.quote(location)}",
            params={"format": "3"},
            timeout=5,
            headers={"User-Agent": "curl/7.0"}
        )
        if resp.status_code == 200:
            return f"Weather for {location}: {resp.text.strip()}"
        return f"Could not get weather for {location}"
    except Exception as e:
        return f"Weather lookup failed: {e}"
