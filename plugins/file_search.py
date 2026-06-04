"""
plugins/file_search.py — Ophelia File Search Plugin
=====================================================
Searches the entire PC for files or folders matching a query.
Displays results in chat with full paths, and opens File Explorer
with the found item highlighted.

Triggers: "find file", "search for file", "where is", "locate file", etc.

Commands:
  find file <name>    — search for a file by name
  find folder <name>  — search for a folder by name
  where is <name>     — same as find file
"""

import os
import re
import threading
import subprocess
from pathlib import Path

NAME        = "file_search"
VERSION     = "1.0"
DESCRIPTION = "Search your entire PC for files and folders. Opens File Explorer with result highlighted."
MANUAL_ONLY = False
AUTHOR      = "SF12P"
TAGS        = ["utility", "files", "search"]
REQUIRES    = []

TRIGGERS = [
    "find file", "find folder", "search for file", "search for folder",
    "where is", "locate file", "locate folder", "look for file",
    "find my", "where did i put", "search my pc for",
]

COMMANDS = {
    "find file <name>":   "Search entire PC for a file by name",
    "find folder <name>": "Search entire PC for a folder by name",
    "where is <name>":    "Find where a file or folder is located",
}

# Folders to skip — system/hidden dirs that slow search and have no user files
SKIP_DIRS = {
    "Windows", "Program Files", "Program Files (x86)",
    "$Recycle.Bin", "System Volume Information",
    "AppData\\Local\\Temp", "AppData\\Local\\Microsoft",
    "AppData\\Roaming\\Microsoft", "__pycache__",
    ".git", "node_modules",
}

MAX_RESULTS = 10


def _extract_query(user_input: str) -> tuple[str, str]:
    """
    Extract search term and type (file/folder) from user input.
    Returns (query, type) where type is 'file', 'folder', or 'any'
    """
    text = user_input.lower().strip()

    search_type = "any"
    if "folder" in text or "directory" in text:
        search_type = "folder"
    elif "file" in text:
        search_type = "file"

    # Remove trigger phrases to get the actual search term
    patterns = [
        r"find (?:file|folder|my)\s+",
        r"search (?:for )?(?:file|folder|my)?\s*(?:called|named)?\s*",
        r"where (?:is|did i put)\s+",
        r"locate (?:file|folder)?\s*",
        r"look for (?:file|folder)?\s*",
        r"search my pc for\s*",
    ]
    query = text
    for pat in patterns:
        cleaned = re.sub(pat, "", query, flags=re.IGNORECASE).strip()
        if cleaned and cleaned != query:
            query = cleaned
            break

    # Remove common filler words
    query = re.sub(r'^(the|my|a|an)\s+', '', query).strip()
    # Remove file/folder keywords if they're at the start
    query = re.sub(r'^(file|folder|document)\s+(called|named)?\s*', '', query).strip()

    return query, search_type


def _search_pc(query: str, search_type: str, on_status=None) -> list[Path]:
    """
    Search the entire PC for files/folders matching query.
    Returns list of matching paths, up to MAX_RESULTS.
    """
    results = []
    query_lower = query.lower()

    # Search all drive letters
    drives = []
    for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":
        drive = Path(f"{letter}:\\")
        if drive.exists():
            drives.append(drive)

    for drive in drives:
        if on_status:
            on_status(f"Searching {drive}...")
        try:
            for root, dirs, files in os.walk(drive):
                # Skip system directories
                root_path = Path(root)
                dirs[:] = [d for d in dirs
                           if d not in SKIP_DIRS
                           and not d.startswith('.')]

                # Check folders
                if search_type in ("folder", "any"):
                    for d in dirs:
                        if query_lower in d.lower():
                            results.append(root_path / d)
                            if len(results) >= MAX_RESULTS:
                                return results

                # Check files
                if search_type in ("file", "any"):
                    for f in files:
                        if query_lower in f.lower():
                            results.append(root_path / f)
                            if len(results) >= MAX_RESULTS:
                                return results
        except PermissionError:
            continue
        except Exception:
            continue

    return results


def _open_in_explorer(path: Path):
    """Open File Explorer with the item highlighted."""
    try:
        if path.is_file():
            subprocess.run(["explorer", "/select,", str(path)])
        else:
            subprocess.run(["explorer", str(path)])
    except Exception:
        pass


def _chat_status(msg: str, context: dict):
    """Insert a status line into the chat window."""
    try:
        import tkinter as tk
        root = tk._default_root
        if not root: return
        def _do():
            # Find chat widget
            def _find(w):
                if isinstance(w, tk.Text): return w
                for c in w.winfo_children():
                    found = _find(c)
                    if found: return found
                return None
            chat = _find(root)
            if not chat: return
            chat.config(state=tk.NORMAL)
            chat.insert(tk.END, f"  {msg}\n", "source")
            chat.config(state=tk.DISABLED)
            chat.see(tk.END)
        root.after(0, _do)
    except Exception:
        pass


def _show_results(results: list[Path], query: str, context: dict):
    """Display results in chat with clickable open buttons."""
    try:
        import tkinter as tk
        root = tk._default_root
        if not root: return

        def _do():
            def _find(w):
                if isinstance(w, tk.Text): return w
                for c in w.winfo_children():
                    found = _find(c)
                    if found: return found
                return None
            chat = _find(root)
            if not chat: return

            chat.config(state=tk.NORMAL)
            if not results:
                chat.insert(tk.END, f"  No results found for '{query}'.\n", "source")
            else:
                chat.insert(tk.END,
                    f"  Found {len(results)} result(s) for '{query}':\n", "source")
                for i, path in enumerate(results, 1):
                    # Path label
                    chat.insert(tk.END, f"  {i}. ", "source")
                    chat.insert(tk.END, f"{path}\n", "user")
                    # Open button
                    btn = tk.Button(chat,
                        text="📂 Open",
                        bg="#1c1c26", fg="#c084fc",
                        font=("Consolas", 8),
                        relief=tk.FLAT, padx=6, pady=1,
                        cursor="hand2",
                        command=lambda p=path: _open_in_explorer(p))
                    chat.window_create(tk.END, window=btn)
                    chat.insert(tk.END, "\n", "source")
            chat.config(state=tk.DISABLED)
            chat.see(tk.END)
        root.after(0, _do)
    except Exception:
        pass


def run(query: str, context: dict) -> str:
    user_input = context["user_input"]
    search_term, search_type = _extract_query(user_input)

    if not search_term or len(search_term) < 2:
        return "Please specify what to search for. Example: 'find file report.pdf'"

    def _search_async():
        _chat_status(f"Searching for '{search_term}'...", context)
        results = _search_pc(search_term, search_type,
            on_status=lambda m: _chat_status(m, context))
        _show_results(results, search_term, context)

    threading.Thread(target=_search_async, daemon=True).start()
    return f"Searching your PC for '{search_term}'. Results will appear shortly..."
