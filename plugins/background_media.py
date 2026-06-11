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
VERSION     = "1.7"
DESCRIPTION = "Set a static image or animated GIF as Ophelia's background."
MANUAL_ONLY = False
AUTHOR      = "SF12P"
TAGS        = ["appearance", "background", "media"]
REQUIRES    = ["Pillow"]

TRIGGERS = [
    "set background", "clear background", "remove background",
    "background image", "background opacity", "change background",
    "add background",
]

COMMANDS = {
    "set background":             "Open file picker to choose a background image",
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

    # Restore chat widget background color
    if _state.get("chat_widget"):
        try:
            _state["chat_widget"].config(bg="#0a0a0f")
        except Exception:
            pass


def _apply_background(path: str, opacity: int, blur: bool):
    """Set image as background of the chat Text widget using bg image trick."""
    root = _state["root"]
    if not root:
        return False

    try:
        chat, container = _find_chat_container(root)
        if not chat:
            return False

        _state["chat_widget"] = chat
        root.update_idletasks()

        w = chat.winfo_width()  or 600
        h = chat.winfo_height() or 400

        frames = _load_image(path, w, h, opacity, blur)
        if not frames:
            return False

        _clear_background()

        # Use a Label placed in the chat widget's PARENT with place(),
        # positioned exactly over the chat widget, then use tag_configure
        # on the Text widget to make its background transparent-ish by
        # matching the label's position perfectly.
        # Most reliable cross-version approach: place label in same parent,
        # set chat bg to "" won't work, so instead we use the Text widget's
        # own -background option with a PhotoImage via a Canvas embedded
        # as the first character in the Text widget.
        parent = chat.master
        lbl = tk.Label(parent, borderwidth=0, highlightthickness=0,
                       image=frames[0])
        lbl.image = frames[0]

        # Get chat position relative to its parent
        x = chat.winfo_x()
        y = chat.winfo_y()
        lbl.place(x=x, y=y, width=w, height=h)

        # Lower label to bottom of stacking order in parent
        lbl.lower()
        # Then lift chat widget above the label
        chat.lift(lbl)
        # Also lift any scrollbars/frames that sit alongside chat
        try:
            for sib in parent.winfo_children():
                if sib is not lbl:
                    try: sib.lift(lbl)
                    except Exception: pass
        except Exception:
            pass

        # Make chat background transparent so label shows through
        try:
            chat.config(bg="")
        except Exception:
            pass
        # If that fails, set to a very dark near-transparent color
        # that blends with the image
        try:
            chat.config(background="#00000001")
        except Exception:
            pass

        _state["label"]      = lbl
        _state["image_ref"]  = frames[0]
        _state["image_path"] = path

        def _reposition(event=None):
            try:
                if not _state["label"]:
                    return
                nw = chat.winfo_width()
                nh = chat.winfo_height()
                nx = chat.winfo_x()
                ny = chat.winfo_y()
                if nw > 10 and nh > 10:
                    new_frames = _load_image(path, nw, nh, opacity, blur)
                    if new_frames:
                        _state["label"].config(image=new_frames[0])
                        _state["label"].image = new_frames[0]
                        _state["image_ref"]   = new_frames[0]
                        if len(new_frames) > 1:
                            _state["gif_frames"] = new_frames
                    _state["label"].place(x=nx, y=ny, width=nw, height=nh)
                    _state["label"].lower()
                    chat.lift(_state["label"])
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
        return "\x00DIRECT\x00Background removed."

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
            return f"\x00DIRECT\x00Background opacity set to {pct}%."
        return "\x00DIRECT\x00Please specify opacity 0-100. Example: background opacity 40"

    # Set background — open file picker directly, no path needed in chat
    root = _state["root"] or tk._default_root
    if not root:
        return "\x00DIRECT\x00Could not access GUI."

    _state["root"] = root
    opacity = _state.get("opacity", 40)
    _state["opacity"] = opacity

    result_holder = {"msg": "No file selected."}

    def _pick_and_apply():
        try:
            from tkinter import filedialog
            path_str = filedialog.askopenfilename(
                title="Choose background image",
                filetypes=[
                    ("Image files", "*.png *.jpg *.jpeg *.gif *.webp *.bmp"),
                    ("All files", "*.*"),
                ])
            if not path_str:
                result_holder["msg"] = "No file selected."
                return
            ok = _apply_background(path_str, opacity, False)
            result_holder["msg"] = (
                f"Background set to: {Path(path_str).name}"
                if ok else "Could not apply background.")
        except Exception as e:
            result_holder["msg"] = f"Error: {e}"

    root.after(0, _pick_and_apply)
    return "\x00DIRECT\x00Opening file picker — choose an image to use as background."
