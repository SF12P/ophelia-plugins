"""
plugins/export_chat.py — Ophelia Chat Export Plugin
=====================================================
Export the current chat or any chat to a .txt or .pdf file.
Saves to the user's Documents folder by default.

Commands:
  export chat           — export current chat as .txt
  export chat as pdf    — export current chat as .pdf
  export chat <name>    — export a specific chat by name
  export all chats      — export all chats to separate files
"""

import json
import time
from pathlib import Path
from datetime import datetime

NAME        = "export_chat"
VERSION     = "1.0"
DESCRIPTION = "Export your chats as .txt or .pdf files."
MANUAL_ONLY = False
AUTHOR      = "SF12P"
TAGS        = ["utility", "export", "chat"]
REQUIRES    = []

TRIGGERS = [
    "export chat", "save chat", "export conversation",
    "save conversation", "export all chats", "download chat",
]

COMMANDS = {
    "export chat":         "Export current chat as .txt",
    "export chat as pdf":  "Export current chat as .pdf",
    "export all chats":    "Export all chats to separate .txt files",
}


def _get_documents() -> Path:
    """Get the user's Documents folder."""
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders")
        docs = Path(winreg.QueryValueEx(key, "Personal")[0])
        winreg.CloseKey(key)
        return docs
    except Exception:
        return Path.home() / "Documents"


def _load_chat(chat_id: str, memory_dir: str) -> dict | None:
    try:
        p = Path(memory_dir) / "chats" / f"{chat_id}.json"
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        pass
    return None


def _format_chat_txt(data: dict, ai_name: str = "Ophelia") -> str:
    """Format a chat as plain text."""
    name     = data.get("name", "Chat")
    messages = data.get("messages", [])
    lines    = [
        f"{'='*60}",
        f"  {name}",
        f"  Exported: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"  Project Ophelia by SF12P",
        f"{'='*60}",
        "",
    ]
    for msg in messages:
        role    = msg.get("role", "")
        content = msg.get("content", msg.get("text", "")).strip()
        ts      = msg.get("timestamp", "")
        speaker = "You" if role == "user" else ai_name
        if ts:
            lines.append(f"[{ts}] {speaker}:")
        else:
            lines.append(f"{speaker}:")
        lines.append(content)
        lines.append("")
    return "\n".join(lines)


def _export_txt(data: dict, output_path: Path, ai_name: str = "Ophelia") -> bool:
    try:
        text = _format_chat_txt(data, ai_name)
        output_path.write_text(text, encoding="utf-8")
        return True
    except Exception:
        return False


def _export_pdf(data: dict, output_path: Path, ai_name: str = "Ophelia") -> bool:
    """Export as PDF using reportlab if available, fallback to txt."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib import colors

        name     = data.get("name", "Chat")
        messages = data.get("messages", [])

        doc    = SimpleDocTemplate(str(output_path), pagesize=A4,
                                   leftMargin=2*cm, rightMargin=2*cm,
                                   topMargin=2*cm, bottomMargin=2*cm)
        styles = getSampleStyleSheet()
        story  = []

        # Title
        title_style = ParagraphStyle("title", parent=styles["Heading1"],
                                     textColor=colors.HexColor("#c084fc"))
        story.append(Paragraph(name, title_style))
        story.append(Paragraph(
            f"Exported {datetime.now().strftime('%Y-%m-%d %H:%M')} — Project Ophelia",
            styles["Normal"]))
        story.append(Spacer(1, 0.5*cm))

        user_style = ParagraphStyle("user", parent=styles["Normal"],
                                    textColor=colors.HexColor("#e2e0f0"),
                                    leftIndent=0.5*cm)
        ai_style   = ParagraphStyle("ai", parent=styles["Normal"],
                                    textColor=colors.HexColor("#c084fc"),
                                    leftIndent=0.5*cm)

        for msg in messages:
            role    = msg.get("role", "")
            content = msg.get("content", msg.get("text", "")).strip()
            speaker = "You" if role == "user" else ai_name
            label   = ParagraphStyle("label", parent=styles["Normal"],
                                     textColor=colors.grey, fontSize=8)
            story.append(Paragraph(speaker, label))
            style = user_style if role == "user" else ai_style
            # Escape special chars for reportlab
            safe = content.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
            story.append(Paragraph(safe, style))
            story.append(Spacer(1, 0.3*cm))

        doc.build(story)
        return True

    except ImportError:
        # reportlab not installed — fall back to txt with .pdf extension renamed
        txt_path = output_path.with_suffix(".txt")
        ok = _export_txt(data, txt_path, ai_name)
        if ok:
            # Rename output_path to txt
            output_path.write_bytes(txt_path.read_bytes())
            txt_path.unlink()
        return ok
    except Exception:
        return False


def _open_folder(path: Path):
    """Open the folder containing the exported file."""
    try:
        import subprocess
        subprocess.run(["explorer", "/select,", str(path)])
    except Exception:
        pass


def run(query: str, context: dict) -> str:
    text     = context["user_input"].lower().strip()
    mem_dir  = context["memory_dir"]
    docs     = _get_documents() / "Ophelia Exports"
    docs.mkdir(parents=True, exist_ok=True)

    as_pdf   = "pdf" in text
    all_chats = "all chats" in text or "all chat" in text

    # Get active chat ID from shared state or prefs
    shared   = context.get("shared_state", {})
    chat_id  = shared.get("active_chat_id", "")
    ai_name  = shared.get("ai_name", "Ophelia")

    if all_chats:
        # Export all chats
        chats_dir = Path(mem_dir) / "chats"
        if not chats_dir.exists():
            return "No chats found to export."
        exported = 0
        for f in chats_dir.glob("*.json"):
            try:
                data     = json.loads(f.read_text(encoding="utf-8"))
                name     = data.get("name", f.stem)
                safe     = "".join(c for c in name if c.isalnum() or c in " _-")[:40]
                out_path = docs / f"{safe}.txt"
                if _export_txt(data, out_path, ai_name):
                    exported += 1
            except Exception:
                continue
        _open_folder(docs)
        return f"Exported {exported} chat(s) to:\n{docs}"

    # Export current chat
    if not chat_id:
        return ("No active chat found. Switch to a chat first, then try again.")

    data = _load_chat(chat_id, mem_dir)
    if not data:
        return "Could not load current chat."

    name     = data.get("name", "Chat")
    safe     = "".join(c for c in name if c.isalnum() or c in " _-")[:40]
    ts       = datetime.now().strftime("%Y%m%d_%H%M")
    ext      = ".pdf" if as_pdf else ".txt"
    out_path = docs / f"{safe}_{ts}{ext}"

    if as_pdf:
        ok = _export_pdf(data, out_path, ai_name)
    else:
        ok = _export_txt(data, out_path, ai_name)

    if ok:
        _open_folder(out_path)
        return f"Chat exported to:\n{out_path}"
    return "Export failed. Please try again."
