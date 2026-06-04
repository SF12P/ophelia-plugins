"""
plugins/chat_search.py — Ophelia Chat Search Plugin
=====================================================
Search through conversation history across all chats.
Results shown in chat with clickable jump-to links.

Commands:
  search chat <query>     — search all chats for a phrase
  find in chat <query>    — same as search chat
  search history <query>  — same as search chat
"""

import json
import re
from pathlib import Path
from datetime import datetime

NAME        = "chat_search"
VERSION     = "1.0"
DESCRIPTION = "Search through your conversation history across all chats."
MANUAL_ONLY = False
AUTHOR      = "SF12P"
TAGS        = ["utility", "search", "chat"]
REQUIRES    = []

TRIGGERS = [
    "search chat", "search my chat", "search history",
    "find in chat", "find in my chat", "search conversation",
    "did i mention", "when did i", "look in chat",
]

COMMANDS = {
    "search chat <query>":    "Search all chats for a phrase",
    "find in chat <query>":   "Same as search chat",
    "search history <query>": "Search conversation history",
}

MAX_RESULTS = 15


def _extract_query(user_input: str) -> str:
    text = user_input.lower().strip()
    patterns = [
        r"search (?:my )?(?:chat|history|conversation)s?\s+(?:for\s+)?(.+)",
        r"find in (?:my )?(?:chat|history|conversation)s?\s+(.+)",
        r"look in (?:my )?chat\s+(?:for\s+)?(.+)",
        r"did i (?:mention|talk about|say)\s+(.+)",
        r"when did i\s+(?:mention|talk about|say)\s+(.+)",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(1).strip().strip("?").strip()
    return ""


def _search_chats(query: str, memory_dir: str) -> list[dict]:
    """Search all chat JSON files for the query string."""
    chats_dir = Path(memory_dir) / "chats"
    if not chats_dir.exists():
        return []

    results = []
    query_lower = query.lower()

    for chat_file in sorted(chats_dir.glob("*.json"),
                             key=lambda f: f.stat().st_mtime, reverse=True):
        try:
            data = json.loads(chat_file.read_text(encoding="utf-8"))
            chat_name = data.get("name", chat_file.stem)
            messages  = data.get("messages", [])

            for i, msg in enumerate(messages):
                role    = msg.get("role", "")
                content = msg.get("content", msg.get("text", ""))
                if query_lower in content.lower():
                    # Get surrounding context (message before and after)
                    prev_msg = messages[i-1] if i > 0 else None
                    snippet  = content.strip()
                    # Highlight the match
                    idx = snippet.lower().find(query_lower)
                    start = max(0, idx - 60)
                    end   = min(len(snippet), idx + len(query) + 60)
                    excerpt = ("..." if start > 0 else "") + \
                              snippet[start:end] + \
                              ("..." if end < len(snippet) else "")

                    results.append({
                        "chat_id":   chat_file.stem,
                        "chat_name": chat_name,
                        "role":      role,
                        "excerpt":   excerpt,
                        "msg_index": i,
                        "timestamp": msg.get("timestamp", ""),
                    })

                    if len(results) >= MAX_RESULTS:
                        return results
        except Exception:
            continue

    return results


def _show_results(results: list, query: str, context: dict):
    """Display search results in the chat window."""
    try:
        import tkinter as tk
        root = tk._default_root
        if not root:
            return

        def _find_chat_widget(w):
            if isinstance(w, tk.Text) and w.winfo_width() > 200:
                return w
            for c in w.winfo_children():
                found = _find_chat_widget(c)
                if found:
                    return found
            return None

        def _do():
            chat = _find_chat_widget(root)
            if not chat:
                return

            chat.config(state=tk.NORMAL)

            if not results:
                chat.insert(tk.END,
                    f"  No results found for '{query}'.\n", "source")
            else:
                chat.insert(tk.END,
                    f"  Found {len(results)} result(s) for '{query}':\n\n",
                    "source")

                seen_chats = {}
                for r in results:
                    cid  = r["chat_id"]
                    name = r["chat_name"]
                    role = "You" if r["role"] == "user" else "Ophelia"

                    if cid not in seen_chats:
                        seen_chats[cid] = True
                        chat.insert(tk.END, f"  ── {name} ──\n", "ao")

                    chat.insert(tk.END, f"  {role}: ", "source")
                    chat.insert(tk.END, f"{r['excerpt']}\n", "ar")

            chat.config(state=tk.DISABLED)
            chat.see(tk.END)

        root.after(0, _do)
    except Exception:
        pass


def run(query: str, context: dict) -> str:
    search_term = _extract_query(context["user_input"])

    if not search_term or len(search_term) < 2:
        return ("Please specify what to search for.\n"
                "Example: 'search chat python' or 'did I mention my birthday'")

    results = _search_chats(search_term, context["memory_dir"])
    _show_results(results, search_term, context)

    if not results:
        return f"No results found for '{search_term}'."
    return f"Found {len(results)} result(s) for '{search_term}'."
