"""Quick notes plugin — save and retrieve notes."""
import json, time, re
from pathlib import Path

NAME        = "notes"
TRIGGERS    = ["make a note", "note that", "remember that", "save this",
               "add a note", "show my notes", "list notes", "read my notes"]
DESCRIPTION = "Save and retrieve quick notes"
MANUAL_ONLY = False
AUTHOR    = "SF12P"
TAGS      = ['utility', 'productivity']
REQUIRES  = []


COMMANDS = {
    "make a note <text>":  "Save a quick note",
    "show my notes":       "List your 10 most recent notes",
    "list notes":          "Same as show my notes",
}

def _notes_path(context: dict) -> Path:
    return Path(context["memory_dir"]) / "quick_notes.json"

def _load(context: dict) -> list:
    p = _notes_path(context)
    if p.exists():
        try: return json.loads(p.read_text(encoding="utf-8"))
        except: pass
    return []

def _save(context: dict, notes: list):
    p = _notes_path(context)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(notes, indent=2), encoding="utf-8")

def run(query: str, context: dict) -> str:
    text = context["user_input"].lower()

    # Read notes
    if any(kw in text for kw in ["show", "list", "read", "what are my notes"]):
        notes = _load(context)
        if not notes:
            return "No notes saved yet."
        lines = [f"{i+1}. [{n['time']}] {n['text']}" for i, n in enumerate(notes[-10:])]
        return "Your recent notes:\n" + "\n".join(lines)

    # Save a note
    for trigger in ["make a note", "note that", "remember that", "save this", "add a note"]:
        if trigger in text:
            note_text = re.sub(
                rf'.*{re.escape(trigger)}[:\s]*', '', context["user_input"],
                flags=re.IGNORECASE).strip()
            if note_text:
                notes = _load(context)
                notes.append({
                    "text": note_text,
                    "time": time.strftime("%Y-%m-%d %H:%M")
                })
                _save(context, notes)
                return f"Note saved: '{note_text}'"
    return ""
