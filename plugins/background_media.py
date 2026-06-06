"""
plugins/background_media.py — Ophelia Background Media Plugin
==============================================================
Set a static image or animated video as the background
behind the chat area or the entire window.

Commands:
  set background <path>     — set image/video as chat background
  background off            — remove background
  background opacity <0-100>— adjust background transparency
  background mode chat      — show behind chat only (default)
  background mode window    — show behind entire window
  background settings       — show current settings

Supports: jpg, png, gif, mp4, avi, mkv, webm
Requires: Pillow (images), opencv-python (video)
"""

import os
import threading
import time
from pathlib import Path

NAME        = "background_media"
VERSION     = "1.2"
DESCRIPTION = "Set a static image or animated video as Ophelia's background."
MANUAL_ONLY = False
AUTHOR      = "SF12P"
TAGS        = ["appearance", "customization", "media"]
REQUIRES    = ["Pillow", "opencv-python"]

TRIGGERS = [
    "set background", "background image", "background video",
    "live wallpaper", "set wallpaper", "background off",
    "remove background", "background opacity", "background mode",
    "background settings",
]

COMMANDS = {
    "set background <path>":      "Set an image or video as background",
    "background off":             "Remove the background",
    "background opacity <0-100>": "Set background transparency",
    "background mode chat":       "Show background behind chat only (default)",
    "background mode window":     "Show background behind entire window",
    "background settings":        "Show current background settings",
}

SETTINGS = {
    "opacity":      {"type": "int",    "default": 40,    "min": 5,  "max": 95,
                     "label": "Opacity (%)"},
    "mode":         {"type": "choice", "default": "chat",
                     "choices": ["chat", "window"],
                     "label": "Background mode"},
    "fps_limit":    {"type": "int",    "default": 24,    "min": 5,  "max": 60,
                     "label": "Video FPS limit"},
    "blur":         {"type": "bool",   "default": False,
                     "label": "Blur background"},
    "blur_radius":  {"type": "int",    "default": 8,     "min": 2,  "max": 30,
                     "label": "Blur radius"},
}

# Module-level state
_bg_state = {
    "active":    False,
    "path":      "",
    "mode":      "chat",       # "chat" or "window"
    "opacity":   40,           # 0-100
    "fps_limit": 24,
    "blur":      False,
    "blur_radius": 8,
    "_stop":     False,
    "_thread":   None,
    "_canvas":   None,
    "_image_id": None,
    "_root":     None,
    "_target":   None,         # the widget to put canvas behind
}


def _get_root():
    try:
        import tkinter as tk
        return tk._default_root
    except Exception:
        return None


def _get_chat_widget(root):
    """Find the main chat Text widget."""
    import tkinter as tk
    def _find(w):
        if isinstance(w, tk.Text) and w.winfo_width() > 200:
            return w
        for c in w.winfo_children():
            found = _find(c)
            if found:
                return found
        return None
    return _find(root)


def _make_canvas(root, target_widget, mode):
    """
    Create a background canvas behind the target widget.
    ScrolledText nests Text inside Frame inside ScrolledText —
    we need to go to the ScrolledText's own master (the chat container)
    and position the canvas there using absolute coords.
    """
    import tkinter as tk
    if mode == "chat":
        # ScrolledText hierarchy: co(Frame) > ScrolledText > Frame > Text
        # target_widget is the Text — go up to the chat container (co frame)
        try:
            # Walk up until we find a widget with a meaningful size
            parent = target_widget.master  # inner Frame of ScrolledText
            parent = parent.master         # ScrolledText widget
            parent = parent.master         # co frame (chat container)
        except Exception:
            parent = target_widget.master

        canvas = tk.Canvas(parent, highlightthickness=0, bd=0)

        def _position(*args):
            try:
                # Position canvas to cover the ScrolledText (parent.master's child)
                # Find the ScrolledText widget within parent
                sw = target_widget.master.master  # ScrolledText
                x = sw.winfo_x()
                y = sw.winfo_y()
                w = sw.winfo_width()
                h = sw.winfo_height()
                if w > 10 and h > 10:
                    canvas.place(x=x, y=y, width=w, height=h)
                    canvas.lower(sw)
            except Exception:
                pass

        target_widget.master.master.bind("<Configure>", _position)
        root.after(300, _position)
        root.after(800, _position)  # second pass after full render
    else:
        canvas = tk.Canvas(root, highlightthickness=0, bd=0)
        canvas.place(x=0, y=0, relwidth=1, relheight=1)
        canvas.lower()
    return canvas


def _load_image(path: str, width: int, height: int, opacity: int,
                blur: bool, blur_radius: int):
    """Load and process a static image for display."""
    try:
        from PIL import Image, ImageTk, ImageFilter
        img = Image.open(path).convert("RGBA")
        img = img.resize((width, height), Image.LANCZOS)
        if blur:
            img = img.filter(ImageFilter.GaussianBlur(radius=blur_radius))
        # Apply opacity
        r, g, b, a = img.split()
        a = a.point(lambda p: int(p * opacity / 100))
        img.putalpha(a)
        return ImageTk.PhotoImage(img)
    except Exception as e:
        return None


def _show_static(path: str):
    """Show a static image background."""
    import tkinter as tk
    root = _get_root()
    if not root:
        return

    def _do():
        try:
            chat = _get_chat_widget(root)
            if not chat:
                return

            # Remove existing canvas
            _remove_canvas()

            mode   = _bg_state["mode"]
            canvas = _make_canvas(root, chat, mode)
            _bg_state["_canvas"] = canvas
            _bg_state["_root"]   = root
            _bg_state["_target"] = chat
            # Match text widget bg so canvas shows through
            try:
                chat.config(bg="#0a0a0f")
                chat.master.config(bg="#0a0a0f")
            except Exception:
                pass

            def _draw(*args):
                try:
                    w = canvas.winfo_width()  or root.winfo_width()
                    h = canvas.winfo_height() or root.winfo_height()
                    if w < 10 or h < 10:
                        root.after(200, _draw)
                        return
                    photo = _load_image(path, w, h,
                        _bg_state["opacity"],
                        _bg_state["blur"],
                        _bg_state["blur_radius"])
                    if photo:
                        canvas.delete("all")
                        canvas.create_image(0, 0, anchor=tk.NW, image=photo)
                        canvas._photo_ref = photo  # prevent GC
                except Exception:
                    pass

            canvas.bind("<Configure>", _draw)
            root.after(150, _draw)
            _bg_state["active"] = True

        except Exception:
            pass

    root.after(0, _do)


def _show_video(path: str):
    """Show an animated video background."""
    import tkinter as tk
    root = _get_root()
    if not root:
        return

    def _do():
        try:
            import cv2
            from PIL import Image, ImageTk, ImageFilter

            chat = _get_chat_widget(root)
            if not chat:
                return

            _remove_canvas()
            mode   = _bg_state["mode"]
            canvas = _make_canvas(root, chat, mode)
            _bg_state["_canvas"] = canvas
            _bg_state["_root"]   = root
            _bg_state["_stop"]   = False

            cap = cv2.VideoCapture(path)
            fps = min(_bg_state["fps_limit"],
                      cap.get(cv2.CAP_PROP_FPS) or 24)
            delay = int(1000 / fps)

            def _next_frame():
                if _bg_state["_stop"]:
                    cap.release()
                    return
                try:
                    ret, frame = cap.read()
                    if not ret:
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        ret, frame = cap.read()
                    if ret:
                        w = canvas.winfo_width()  or 800
                        h = canvas.winfo_height() or 600
                        frame = cv2.resize(frame, (w, h))
                        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGBA)
                        img = Image.fromarray(frame)
                        if _bg_state["blur"]:
                            img = img.filter(ImageFilter.GaussianBlur(
                                radius=_bg_state["blur_radius"]))
                        # Apply opacity
                        r, g, b, a = img.split()
                        a = a.point(lambda p: int(p * _bg_state["opacity"] / 100))
                        img.putalpha(a)
                        photo = ImageTk.PhotoImage(img)
                        canvas.delete("all")
                        canvas.create_image(0, 0, anchor=tk.NW, image=photo)
                        canvas._photo_ref = photo
                except Exception:
                    pass
                root.after(delay, _next_frame)

            root.after(100, _next_frame)
            _bg_state["active"] = True

        except ImportError:
            root.after(0, lambda: _show_error(
                "opencv-python is required for video backgrounds.\n"
                "Install it with: pip install opencv-python"))
        except Exception as e:
            root.after(0, lambda: _show_error(f"Video error: {e}"))

    root.after(0, _do)


def _remove_canvas():
    """Remove the current background canvas."""
    try:
        _bg_state["_stop"] = True
        if _bg_state["_canvas"]:
            _bg_state["_canvas"].destroy()
            _bg_state["_canvas"] = None
        _bg_state["active"] = False
    except Exception:
        pass


def _show_error(msg: str):
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = _get_root()
        if root:
            messagebox.showerror("Background Error", msg, parent=root)
    except Exception:
        pass


def _browse_file(context: dict) -> str:
    """Open file dialog to pick background."""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = _get_root()
        path = filedialog.askopenfilename(
            title="Select Background",
            filetypes=[
                ("Images & Videos", "*.jpg *.jpeg *.png *.gif *.mp4 *.avi *.mkv *.webm"),
                ("Images", "*.jpg *.jpeg *.png *.gif"),
                ("Videos", "*.mp4 *.avi *.mkv *.webm"),
                ("All files", "*.*"),
            ],
            parent=root)
        return path or ""
    except Exception:
        return ""


def _register_hooks(context: dict):
    """Register plugin hooks via shared_state so gui.py can call us generically."""
    shared = context.get("shared_state")
    if shared is not None:
        shared["on_gui_rebuild"] = _apply_current


def run(query: str, context: dict) -> str:
    # Register hooks on every call so we're always wired up
    _register_hooks(context)

    text = context["user_input"].lower().strip()

    # Remove background
    if any(t in text for t in ["background off", "remove background",
                                "no background", "clear background"]):
        _remove_canvas()
        if context.get("shared_state") is not None:
            context["shared_state"]["background.active"] = False
        return "Background removed."

    # Opacity
    import re
    op_match = re.search(r"opacity\s+(\d+)", text)
    if op_match:
        val = max(5, min(95, int(op_match.group(1))))
        _bg_state["opacity"] = val
        if _bg_state["active"] and _bg_state["path"]:
            _apply_current()
        return f"Background opacity set to {val}%."

    # Mode
    if "background mode chat" in text or "behind chat" in text:
        _bg_state["mode"] = "chat"
        if _bg_state["active"] and _bg_state["path"]:
            _apply_current()
        return "Background mode set to chat area only."

    if "background mode window" in text or "behind window" in text or "entire window" in text:
        _bg_state["mode"] = "window"
        if _bg_state["active"] and _bg_state["path"]:
            _apply_current()
        return "Background mode set to entire window."

    # Settings
    if "background settings" in text or "background info" in text:
        return (
            f"Background settings:\n"
            f"  Active: {'Yes' if _bg_state['active'] else 'No'}\n"
            f"  File: {_bg_state['path'] or 'None'}\n"
            f"  Mode: {_bg_state['mode']}\n"
            f"  Opacity: {_bg_state['opacity']}%\n"
            f"  Blur: {'On' if _bg_state['blur'] else 'Off'}\n"
            f"  FPS limit: {_bg_state['fps_limit']}"
        )

    # Set background — open file picker
    if any(t in text for t in ["set background", "background image",
                                "background video", "live wallpaper",
                                "set wallpaper"]):
        path = _browse_file(context)
        if not path:
            return "No file selected."

        _bg_state["path"] = path
        ext = Path(path).suffix.lower()

        if ext in (".mp4", ".avi", ".mkv", ".webm", ".mov"):
            _show_video(path)
            return (f"Video background set: {Path(path).name}\n"
                    f"Mode: {_bg_state['mode']} | "
                    f"Opacity: {_bg_state['opacity']}%\n"
                    f"Tip: 'background opacity 60' to adjust transparency.")
        else:
            _show_static(path)
            return (f"Background set: {Path(path).name}\n"
                    f"Mode: {_bg_state['mode']} | "
                    f"Opacity: {_bg_state['opacity']}%\n"
                    f"Tip: 'background mode window' to extend to full window.")

    return ""


def _apply_current():
    """Re-apply current background after settings change."""
    if not _bg_state["path"]:
        return
    _remove_canvas()
    ext = Path(_bg_state["path"]).suffix.lower()
    if ext in (".mp4", ".avi", ".mkv", ".webm", ".mov"):
        _show_video(_bg_state["path"])
    else:
        _show_static(_bg_state["path"])
