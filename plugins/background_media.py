"""
plugins/background_media.py — Ophelia Background Media Plugin
==============================================================
Sets a static image or animated GIF as Ophelia's chat background.
Uses a Label widget placed directly behind the chat area — reliable
across all widget hierarchies.

Commands:
  set background <path>     — set image background
  clear background          — remove background
  background opacity <0-100> — adjust opacity
"""

import threading
import tkinter as tk
from pathlib import Path

NAME        = "background_media"
VERSION     = "1.3"
DESCRIPTION = "Set a static image or animated GIF as Ophelia's background."
MANUAL_ONLY = False
AUTHOR      = "SF12P"
TAGS        = ["appearance", "background", "media"]
REQUIRES    = ["Pillow"]

TRIGGERS = [
    "set background", "clear background", "remove background",
    "background image", "background opacity", "change background",
]

COMMANDS = {
    "set background <path>":      "Set an image as chat background",
    "clear background":           "Remove the background image",
    "background opacity <0-100>": "Adjust background opacity",
}

SETTINGS = {
    "opacity": {
        "label":   "Opacity (%)",
        "type":    "int",
        "default": 40,
        "min":     5,
        "max":     100,
    },
    "blur": {
        "label":   "Blur background",
        "type":    "bool",
        "default": False,
    },
}

# ── State ──────────────────────────────────────────────────────────────────────
_state = {
    "label":      None,   # tk.Label holding the background image
    "image_ref":  None,   # PhotoImage reference (prevent GC)
    "gif_frames": [],     # GIF animation frames
    "gif_job":    None,   # after() job id for GIF animation
    "image_path": "",
    "opacity":    40,
    "root":       None,
    "chat_widget":None,
}


# ── Image helpers ─────────────────────────────────────────────────────────────

def _load_image(path: str, w: int, h: int, opacity: int, blur: bool):
    """Load and process image — returns PhotoImage or list of frames for GIF."""
    from PIL import Image, ImageTk, ImageFilter, ImageEnhance
    img = Image.open(path)

    is_gif = getattr(img, "is_animated", False) or \
             path.lower().endswith(".gif")

    def _process_frame(frame: Image.Image) -> tk.PhotoImage:
        frame = frame.convert("RGBA").resize((w, h), Image.LANCZOS)
        if blur:
            frame = frame.filter(ImageFilter.GaussianBlur(radius=4))
        # Apply opacity by blending with black
        if opacity < 100:
            alpha = int(opacity * 2.55)
            overlay = Image.new("RGBA", frame.size, (0, 0, 0, 255 - alpha))
            frame = Image.alpha_composite(frame, overlay)
        return ImageTk.PhotoImage(frame.convert("RGB"))

    if is_gif:
        frames = []
        try:
            while True:
                frames.append(_process_frame(img.copy()))
                img.seek(img.tell() + 1)
        except EOFError:
            pass
        return frames
    else:
        return [_process_frame(img)]


def _find_chat_container(root: tk.Tk):
    """
    Walk widget tree to find the main chat Text widget and its container.
    Returns (text_widget, container_frame) or (None, None).
    """
    def _walk(widget, depth=0):
        if depth > 8:
            return None, None
        if isinstance(widget, tk.Text):
            w = widget.winfo_width()
            h = widget.winfo_height()
            if w > 300 and h > 200:
                return widget, widget.master
        for child in widget.winfo_children():
            result = _walk(child, depth + 1)
            if result[0] is not None:
                return result
        return None, None
    return _walk(root)


# ── Background management ─────────────────────────────────────────────────────

def _clear_background():
    """Remove existing background label and stop GIF animation."""
    if _state["gif_job"] and _state["root"]:
        try:
            _state["root"].after_cancel(_state["gif_job"])
        except Exception:
            pass
    _state["gif_job"]    = None
    _state["gif_frames"] = []

    if _state["label"]:
        try:
            _state["label"].destroy()
        except Exception:
            pass
    _state["label"]     = None
    _state["image_ref"] = None


def _apply_background(path: str, opacity: int, blur: bool):
    """Create and place the background label behind the chat widget."""
    root = _state["root"]
    if not root:
        return False

    try:
        # Find chat widget
        chat, container = _find_chat_container(root)
        if not chat:
            return False

        _state["chat_widget"] = chat

        # Get dimensions
        root.update_idletasks()
        w = chat.winfo_width()  or 600
        h = chat.winfo_height() or 400

        # Load image
        frames = _load_image(path, w, h, opacity, blur)
        if not frames:
            return False

        _clear_background()

        # Create label in the SAME parent as the chat widget
        # place() it at chat's position so it sits exactly behind it
        parent = chat.master
        lbl = tk.Label(parent, borderwidth=0, highlightthickness=0)
        lbl.image = frames[0]
        lbl.config(image=frames[0])

        # Place at same position as chat widget
        x = chat.winfo_x()
        y = chat.winfo_y()
        lbl.place(x=x, y=y, width=w, height=h)

        # Push label behind chat widget
        lbl.lower(chat)

        _state["label"]      = lbl
        _state["image_ref"]  = frames[0]
        _state["image_path"] = path

        # Reposition if chat resizes
        def _reposition(event=None):
            try:
                if not _state["label"]:
                    return
                nw = chat.winfo_width()
                nh = chat.winfo_height()
                nx = chat.winfo_x()
                ny = chat.winfo_y()
                if nw > 10 and nh > 10:
                    # Reload image at new size
                    new_frames = _load_image(path, nw, nh, opacity, blur)
                    if new_frames:
                        _state["label"].config(image=new_frames[0])
                        _state["label"].image = new_frames[0]
                        _state["image_ref"]   = new_frames[0]
                        if len(new_frames) > 1:
                            _state["gif_frames"] = new_frames
                    _state["label"].place(x=nx, y=ny, width=nw, height=nh)
                    _state["label"].lower(chat)
            except Exception:
                pass

        chat.bind("<Configure>", _reposition)
        root.after(500, _reposition)

        # GIF animation
        if len(frames) > 1:
            _state["gif_frames"] = frames

            def _animate(idx=0):
                try:
                    if not _state["label"] or not _state["gif_frames"]:
                        return
                    frame = _state["gif_frames"][idx % len(_state["gif_frames"])]
                    _state["label"].config(image=frame)
                    _state["label"].image = frame
                    _state["gif_job"] = root.after(
                        80, lambda: _animate(idx + 1))
                except Exception:
                    pass

            _animate()

        return True

    except Exception as e:
        print(f"[background_media] error: {e}")
        return False


def _extract_path(user_input: str) -> str:
    """Extract file path from user input."""
    import re
    text = user_input.strip()
    # Remove trigger phrases
    for prefix in ["set background ", "background image ", "change background "]:
        if text.lower().startswith(prefix):
            text = text[len(prefix):].strip()
            break
    # Strip quotes
    text = text.strip('"\'')
    return text


# ── Lifecycle ─────────────────────────────────────────────────────────────────

def on_startup(context: dict):
    try:
        import tkinter as tk
        _state["root"] = tk._default_root

        # Register skin rebuild hook
        context["shared_state"]["on_gui_rebuild"] = lambda: (
            _reapply() if _state["image_path"] else None)

    except Exception as e:
        print(f"[background_media] startup error: {e}")


def _reapply():
    """Reapply background after skin/GUI rebuild."""
    if _state["image_path"]:
        _state["root"].after(500, lambda: _apply_background(
            _state["image_path"],
            _state["opacity"],
            False))


def on_shutdown(context: dict):
    _clear_background()


# ── Run ───────────────────────────────────────────────────────────────────────

def run(query: str, context: dict) -> str:
    text = context["user_input"].lower().strip()

    # Clear
    if "clear" in text or "remove" in text:
        root = _state["root"] or tk._default_root
        if root:
            root.after(0, _clear_background)
        return "Background removed."

    # Opacity
    if "opacity" in text:
        import re
        m = re.search(r"(\d+)", text)
        if m:
            pct = max(5, min(100, int(m.group(1))))
            _state["opacity"] = pct
            if _state["image_path"]:
                root = _state["root"]
                if root:
                    root.after(0, lambda: _apply_background(
                        _state["image_path"], pct, False))
            return f"Background opacity set to {pct}%."
        return "Please specify opacity 0-100. Example: background opacity 40"

    # Set background
    path_str = _extract_path(context["user_input"])
    if not path_str:
        return ("Please provide an image path.\n"
                "Example: set background C:\\Users\\me\\wallpaper.jpg")

    path = Path(path_str)
    if not path.exists():
        return f"File not found: {path_str}"

    if path.suffix.lower() not in {".png",".jpg",".jpeg",".gif",".webp",".bmp"}:
        return "Unsupported format. Use PNG, JPG, GIF, or WebP."

    opacity = _state.get("opacity", 40)
    root    = _state["root"] or tk._default_root
    if not root:
        return "Could not access GUI."

    _state["root"]    = root
    _state["opacity"] = opacity

    def _do():
        ok = _apply_background(path_str, opacity, False)
        return ok

    root.after(100, _do)
    return f"Background set to: {path.name}"
