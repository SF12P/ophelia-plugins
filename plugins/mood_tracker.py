"""
plugins/mood_tracker.py — Ophelia Mood Tracker Plugin
======================================================
Log your mood and let Ophelia track patterns over time.
Stores mood entries locally in trm_memory/mood_log.json

Commands:
  log mood <mood>         — log current mood
  how have i been feeling — show recent mood summary
  mood history            — show last 10 mood entries
  mood stats              — show mood breakdown
"""

import json
import time
import re
from pathlib import Path
from datetime import datetime

NAME        = "mood_tracker"
VERSION     = "1.0"
DESCRIPTION = "Track your mood over time. Ophelia notices patterns and checks in on you."
MANUAL_ONLY = False
AUTHOR      = "SF12P"
TAGS        = ["wellness", "mood", "tracking"]
REQUIRES    = []

TRIGGERS = [
    "log mood", "i'm feeling", "im feeling", "i feel",
    "mood is", "feeling really", "how have i been feeling",
    "mood history", "mood stats", "mood log",
    "i've been feeling", "ive been feeling",
]

COMMANDS = {
    "log mood <mood>":           "Log how you're feeling right now",
    "i'm feeling <mood>":        "Same as log mood",
    "how have i been feeling":   "Get a summary of your recent moods",
    "mood history":              "Show your last 10 mood entries",
    "mood stats":                "Show mood breakdown and patterns",
}

# Mood categories for pattern detection
MOOD_POSITIVE = {"happy", "great", "good", "excited", "joyful", "amazing",
                  "fantastic", "wonderful", "cheerful", "content", "motivated",
                  "energetic", "confident", "peaceful", "grateful", "proud"}
MOOD_NEGATIVE = {"sad", "bad", "terrible", "awful", "depressed", "anxious",
                  "stressed", "angry", "frustrated", "tired", "exhausted",
                  "lonely", "scared", "worried", "upset", "down", "low"}
MOOD_NEUTRAL  = {"okay", "fine", "alright", "meh", "neutral", "normal", "average"}


def _log_path(context: dict) -> Path:
    return Path(context["memory_dir"]) / "mood_log.json"


def _load_log(context: dict) -> list:
    p = _log_path(context)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def _save_log(context: dict, entries: list):
    p = _log_path(context)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(entries, indent=2), encoding="utf-8")


def _categorize(mood: str) -> str:
    m = mood.lower()
    if any(w in m for w in MOOD_POSITIVE): return "positive"
    if any(w in m for w in MOOD_NEGATIVE): return "negative"
    return "neutral"


def _extract_mood(text: str) -> str:
    """Extract the mood word/phrase from user input."""
    text = text.lower().strip()
    patterns = [
        r"log mood\s+(.+)",
        r"i(?:'m|m) feeling\s+(.+)",
        r"i feel\s+(.+)",
        r"(?:my )?mood is\s+(.+)",
        r"feeling really\s+(.+)",
        r"i(?:'ve|ve) been feeling\s+(.+)",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            mood = m.group(1).strip()
            mood = re.sub(r'\.$', '', mood)
            return mood
    return ""


def _log_mood(mood: str, context: dict) -> str:
    entries = _load_log(context)
    entry = {
        "mood":      mood,
        "category":  _categorize(mood),
        "timestamp": time.time(),
        "date":      datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    entries.append(entry)
    # Keep last 500 entries
    if len(entries) > 500:
        entries = entries[-500:]
    _save_log(context, entries)

    category = entry["category"]
    if category == "positive":
        response = f"Glad to hear you're feeling {mood}! I've logged that. 😊"
    elif category == "negative":
        response = (f"I'm sorry you're feeling {mood}. I've logged that. "
                    f"I'm here if you want to talk about it.")
    else:
        response = f"Got it — feeling {mood}. I've logged that."

    # Check for concerning patterns
    recent = [e for e in entries[-7:] if e["category"] == "negative"]
    if len(recent) >= 5:
        response += ("\n\nI've noticed you've been feeling down quite a bit lately. "
                     "Remember it's okay to reach out to someone you trust if things feel heavy.")

    return response


def _mood_history(context: dict) -> str:
    entries = _load_log(context)
    if not entries:
        return "No mood entries yet. Try: 'log mood happy' or 'I'm feeling anxious'."

    last = entries[-10:]
    lines = ["Your recent mood entries:\n"]
    for e in reversed(last):
        lines.append(f"  {e['date']} — {e['mood']}")
    return "\n".join(lines)


def _mood_stats(context: dict) -> str:
    entries = _load_log(context)
    if not entries:
        return "No mood data yet."

    total = len(entries)
    cats  = {"positive": 0, "negative": 0, "neutral": 0}
    moods = {}
    for e in entries:
        cats[e.get("category", "neutral")] += 1
        m = e["mood"]
        moods[m] = moods.get(m, 0) + 1

    top = sorted(moods.items(), key=lambda x: x[1], reverse=True)[:5]
    pct_pos = int(cats["positive"] / total * 100)
    pct_neg = int(cats["negative"] / total * 100)
    pct_neu = int(cats["neutral"]  / total * 100)

    lines = [
        f"Mood stats from {total} entries:\n",
        f"  Positive: {cats['positive']} ({pct_pos}%)",
        f"  Negative: {cats['negative']} ({pct_neg}%)",
        f"  Neutral:  {cats['neutral']} ({pct_neu}%)\n",
        "Most logged moods:",
    ]
    for mood, count in top:
        lines.append(f"  {mood}: {count}x")
    return "\n".join(lines)


def _how_have_i_been(context: dict) -> str:
    entries = _load_log(context)
    if not entries:
        return "No mood data yet — start logging with 'I'm feeling happy' or 'log mood anxious'."

    recent = entries[-14:]  # last 2 weeks roughly
    if not recent:
        return "Not enough data yet."

    cats = {"positive": 0, "negative": 0, "neutral": 0}
    for e in recent:
        cats[e.get("category", "neutral")] += 1

    dominant = max(cats, key=cats.get)
    total = len(recent)

    if dominant == "positive":
        summary = f"You've been doing pretty well lately — {cats['positive']} out of your last {total} logged moods were positive."
    elif dominant == "negative":
        summary = (f"It looks like you've been having a rough time — "
                   f"{cats['negative']} out of your last {total} logged moods were on the lower side. "
                   f"I hope things start looking up soon.")
    else:
        summary = f"You've been feeling fairly neutral lately — a mix of ups and downs across your last {total} entries."

    return summary


def run(query: str, context: dict) -> str:
    text = context["user_input"].lower().strip()

    if any(t in text for t in ["how have i been feeling", "how have i been"]):
        return _how_have_i_been(context)

    if "mood history" in text or "mood log" in text:
        return _mood_history(context)

    if "mood stats" in text or "mood breakdown" in text:
        return _mood_stats(context)

    # Log mood
    mood = _extract_mood(context["user_input"])
    if mood:
        return _log_mood(mood, context)

    return ("I can track your mood! Try:\n"
            "  'I'm feeling happy'\n"
            "  'log mood anxious'\n"
            "  'how have I been feeling'\n"
            "  'mood stats'")
