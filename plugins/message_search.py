"""
plugins/message_search.py — Per-Chat Message Search
=====================================================
Search within the current active chat using Ctrl+F style search.
Results shown inline with match highlighting.
Can also jump to specific messages.

Commands:
  find <query>         — search current chat
  search for <query>   — same
  ctrl f               — open search bar (shortcut hint)
"""

import json
import re
import tkinter as tk
from pathlib import Path

NAME        = "message_search"
VERSION     = "1.0"
DESCRIPTION = "Search within the current chat for any phrase or keyword."
MANUAL_ONLY = False
AUTHOR      = "SF12P"
TAGS        = ["utility", "search", "chat"]
REQUIRES    = []

TRIGGERS = [
    "find ", "search for ", "search in chat",
    "look for ", "ctrl f", "find in chat",
]

COMMANDS = {
    "find <query>":       "Search current chat for a phrase",
    "search for <query>": "Same as find",
}

# Colors matching Ophelia skin
BG_DARK    = "#0a0a0f"
BG_MID     = "#16161e"
ACCENT     = "#c084fc"
ACCENT_DIM = "#7c3aed"
TEXT_PRIMARY = "#e2e0f0"
TEXT_DIM   = "#6b6880"
SUCCESS    = "#4ade80"
DANGER     = "#f87171"
BORDER     = "#1e1e2e"


def _extract_query(user_input: str) -> str:
    text = user_input.lower().strip()
    for prefix in ["find in chat ", "search in chat ", "find ",
                   "search for ", "look for ", "ctrl f "]:
        if text.startswith(prefix):
            return user_input[len(prefix):].strip()
    return ""


def _get_active_chat_id(context: dict) -> str:
    return context.get("shared_state", {}).get("active_chat_id", "") or \
           context.get("chat_id", "")


def _load_chat(chat_id: str, mem_dir: str) -> dict | None:
    try:
        p = Path(mem_dir) / "chats" / f"{chat_id}.json"
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        pass
    return None


def _search_messages(messages: list, query: str) -> list:
    """Find all messages containing the query string."""
    q = query.lower()
    results = []
    for i, msg in enumerate(messages):
        content = msg.get("content", msg.get("text", ""))
        if q in content.lower():
            role    = msg.get("role", "")
            speaker = "You" if role == "user" else "Ophelia"
            # Build excerpt with match highlighted
            idx     = content.lower().find(q)
            start   = max(0, idx - 60)
            end     = min(len(content), idx + len(query) + 60)
            excerpt = ("..." if start > 0 else "") + \
                      content[start:end] + \
                      ("..." if end < len(content) else "")
            results.append({
                "index":   i,
                "speaker": speaker,
                "excerpt": excerpt,
                "match_start": idx - start if start > 0 else idx,
                "match_len":   len(query),
            })
    return results


def _show_search_bar(context: dict):
    """Open a floating search bar over the chat window."""
    try:
        root = tk._default_root
        if not root:
            return

        # Don't open two search bars
        for w in root.winfo_children():
            if hasattr(w, "_is_search_bar") and w._is_search_bar:
                w.lift()
                return

        win = tk.Toplevel(root)
        win._is_search_bar = True
        win.title("")
        win.configure(bg=BG_DARK)
        win.geometry("420x48")
        win.resizable(False, False)
        win.overrideredirect(True)
        win.wm_attributes("-topmost", True)

        # Position near top of main window
        rx = root.winfo_x() + root.winfo_width() // 2 - 210
        ry = root.winfo_y() + 100
        win.geometry(f"+{rx}+{ry}")

        # Border
        border = tk.Frame(win, bg=BORDER, padx=1, pady=1)
        border.pack(fill=tk.BOTH, expand=True)
        inner  = tk.Frame(border, bg=BG_MID)
        inner.pack(fill=tk.BOTH, expand=True)

        # Search input
        query_var   = tk.StringVar()
        result_lbl  = tk.Label(inner, text="", bg=BG_MID, fg=TEXT_DIM,
            font=("Consolas",8), width=6)
        result_lbl.pack(side=tk.RIGHT, padx=(0,8))

        tk.Button(inner, text="✕", bg=BG_MID, fg=TEXT_DIM,
            font=("Consolas",9), relief=tk.FLAT, padx=6, cursor="hand2",
            command=win.destroy).pack(side=tk.RIGHT)

        entry = tk.Entry(inner, textvariable=query_var,
            bg=BG_MID, fg=TEXT_PRIMARY,
            font=("Consolas",11), insertbackground=ACCENT,
            relief=tk.FLAT, bd=8)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        entry.focus_set()

        tk.Label(inner, text="🔍", bg=BG_MID, fg=ACCENT,
            font=("Consolas",10)).pack(side=tk.LEFT, padx=(8,4))

        current_results = []
        current_idx     = [0]

        def _do_search(*args):
            q = query_var.get().strip()
            if len(q) < 2:
                result_lbl.config(text="")
                return
            chat_id = _get_active_chat_id(context)
            mem_dir = context.get("memory_dir","trm_memory")
            data    = _load_chat(chat_id, mem_dir)
            if not data:
                result_lbl.config(text="no chat")
                return
            msgs    = data.get("messages", [])
            results = _search_messages(msgs, q)
            current_results.clear()
            current_results.extend(results)
            current_idx[0] = 0

            if not results:
                result_lbl.config(text="0 found", fg=DANGER)
            else:
                result_lbl.config(text=f"1/{len(results)}", fg=SUCCESS)
                _highlight(results[0] if results else None, q)

        def _highlight(result, query):
            """Highlight match in chat widget."""
            try:
                # Find chat Text widget
                def _find_chat(w):
                    import tkinter.scrolledtext as st
                    if isinstance(w, tk.Text) and w.winfo_width() > 300:
                        return w
                    for c in w.winfo_children():
                        f = _find_chat(c)
                        if f: return f
                    return None

                chat = _find_chat(root)
                if not chat:
                    return

                # Remove old highlights
                chat.tag_remove("search_highlight", "1.0", tk.END)
                chat.tag_config("search_highlight",
                    background=ACCENT_DIM, foreground=TEXT_PRIMARY)

                # Find and highlight all matches
                content = chat.get("1.0", tk.END)
                q_lower = query.lower()
                start   = 0
                first_pos = None
                while True:
                    idx = content.lower().find(q_lower, start)
                    if idx < 0:
                        break
                    pos_start = f"1.0 + {idx}c"
                    pos_end   = f"1.0 + {idx + len(query)}c"
                    chat.tag_add("search_highlight", pos_start, pos_end)
                    if first_pos is None:
                        first_pos = pos_start
                    start = idx + 1

                # Scroll to first match
                if first_pos:
                    chat.see(first_pos)
            except Exception:
                pass

        def _next(*args):
            if not current_results: return
            current_idx[0] = (current_idx[0] + 1) % len(current_results)
            result_lbl.config(
                text=f"{current_idx[0]+1}/{len(current_results)}", fg=SUCCESS)

        def _prev(*args):
            if not current_results: return
            current_idx[0] = (current_idx[0] - 1) % len(current_results)
            result_lbl.config(
                text=f"{current_idx[0]+1}/{len(current_results)}", fg=SUCCESS)

        query_var.trace_add("write", _do_search)
        entry.bind("<Return>",  _next)
        entry.bind("<Escape>",  lambda e: win.destroy())
        win.bind("<Escape>",    lambda e: win.destroy())

        # Clean up highlight on close
        def _on_close():
            try:
                def _find_chat(w):
                    if isinstance(w, tk.Text) and w.winfo_width() > 300:
                        return w
                    for c in w.winfo_children():
                        f = _find_chat(c)
                        if f: return f
                    return None
                chat = _find_chat(root)
                if chat:
                    chat.tag_remove("search_highlight", "1.0", tk.END)
            except Exception:
                pass
            win.destroy()

        win.protocol("WM_DELETE_WINDOW", _on_close)

    except Exception as e:
        print(f"[message_search] search bar error: {e}")


def run(query: str, context: dict) -> str:
    text = context["user_input"].lower().strip()

    # Open floating search bar
    if "ctrl f" in text or text in ("find", "search"):
        _show_search_bar(context)
        return ""

    # Extract search query
    search_term = _extract_query(context["user_input"])
    if not search_term or len(search_term) < 2:
        _show_search_bar(context)
        return ""

    # Search current chat and show results inline
    chat_id = _get_active_chat_id(context)
    mem_dir = context.get("memory_dir", "trm_memory")
    data    = _load_chat(chat_id, mem_dir)

    if not data:
        return "No active chat to search."

    messages = data.get("messages", [])
    results  = _search_messages(messages, search_term)

    if not results:
        return f"No results for '{search_term}' in this chat."

    lines = [f"Found {len(results)} result(s) for '{search_term}':"]
    for r in results[:8]:
        lines.append(f"\n{r['speaker']}: {r['excerpt']}")

    if len(results) > 8:
        lines.append(f"\n...and {len(results)-8} more.")

    return "\n".join(lines)
