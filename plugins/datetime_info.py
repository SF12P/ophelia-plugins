"""
plugins/datetime_info.py — Date, Time and Alarm Plugin
========================================================
Returns current date/time and supports setting alarms.
Exposes get_now() for other plugins to use as a consistent time source.

Interoperability:
  - Writes datetime.now to shared_state["datetime.now"] on every call
  - Other plugins can read shared_state["datetime.now"] for accurate time
  - Exposes get_now() which plugin_manager.call("get_now") can access

Alarms:
  - "set an alarm for 3pm" — uses reminder system to fire at that time
  - "set an alarm in 30 minutes" — relative alarm
  - Works with reminder plugin if loaded, falls back to reminder manager
    passed in context["reminder_manager"]
"""

import datetime

NAME        = "datetime_info"
DESCRIPTION = "Returns current date/time and sets alarms. Shared time source for other plugins."
MANUAL_ONLY = False
AUTHOR    = "SF12P"
TAGS      = ['utility', 'time']
REQUIRES  = []


TRIGGERS = [
    "what time is it", "what's the time", "current time", "what is the time",
    "what day is it", "today's date", "what is today", "what year is it",
    "what month is it", "current date",
    # Alarm triggers
    "set an alarm", "set alarm", "wake me", "alarm for", "alarm in",
]

COMMANDS = {
    "set an alarm for <time>": "Set an alarm using natural language time (e.g. 3pm, in 30 minutes)",
    "set an alarm in <duration>": "Set an alarm relative to now (e.g. in 2 hours)",
}


def get_now() -> datetime.datetime:
    """
    Consistent time source for all plugins.
    Call via: plugin_manager.call("get_now") or import directly.
    """
    return datetime.datetime.now()


def run(query: str, context: dict) -> str:
    now = get_now()

    # Write to shared_state so other plugins have accurate time
    shared = context.get("shared_state")
    if shared is not None:
        shared["datetime.now"]    = now
        shared["datetime.date"]   = now.date()
        shared["datetime.time"]   = now.time()
        shared["datetime.weekday"]= now.strftime("%A")

    text = context["user_input"].lower().strip()

    # ── Alarm handling ────────────────────────────────────────────────
    alarm_triggers = ["set an alarm", "set alarm", "wake me", "alarm for", "alarm in"]
    if any(t in text for t in alarm_triggers):
        return _handle_alarm(context["user_input"], context, now)

    # ── Date/time response ────────────────────────────────────────────
    return (
        f"Current date and time: {now.strftime('%A, %B %d %Y')} "
        f"at {now.strftime('%I:%M %p')}"
    )


def _handle_alarm(user_input: str, context: dict, now: datetime.datetime) -> str:
    """
    Parse an alarm request and set it via the reminder system.
    Uses context["reminder_manager"] if available, otherwise falls back
    to ReminderManager.parse_natural() style parsing.
    """
    import re

    text = user_input.lower().strip()

    # Extract time from alarm request
    # Convert "alarm" phrasing to "remind me" for the shared parser
    converted = text
    converted = re.sub(r"set (?:an? )?alarm for",  "remind me at",  converted)
    converted = re.sub(r"set (?:an? )?alarm in",   "remind me in",  converted)
    converted = re.sub(r"wake me (?:up )?at",       "remind me at",  converted)
    converted = re.sub(r"wake me (?:up )?in",       "remind me in",  converted)
    converted = re.sub(r"alarm for",                "remind me at",  converted)
    converted = re.sub(r"alarm in",                 "remind me in",  converted)

    # Add a message if none present
    if "remind me" in converted and not any(
        w in converted for w in ["to ", "about ", "that "]):
        converted = converted.replace("remind me", "remind me alarm")

    # Try to parse via ReminderManager
    try:
        from core.reminders import ReminderManager
        parsed = ReminderManager.parse_natural(converted)
        if parsed:
            message, fire_at = parsed

            # Set via reminder_manager in context if available
            rm = context.get("reminder_manager")
            if rm:
                r = rm.add(message or "Alarm", fire_at)
                return (
                    f"Alarm set for {r.fire_at_str}. "
                    f"I'll notify you when it fires."
                )

            # Fallback — report what we parsed but can't set it
            return (
                f"Alarm parsed for {fire_at.strftime('%I:%M %p')} "
                f"but the reminder system isn't active. "
                f"Try: remind me at {fire_at.strftime('%I:%M %p')} to wake up."
            )
    except Exception:
        pass

    return (
        "I couldn't parse that alarm time. "
        "Try: 'set an alarm for 3pm' or 'set an alarm in 30 minutes'."
    )
