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
VERSION     = "1.8"
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
    "outer":      None,   # outer container frame
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
    Walk widget tree to find the main chat Text widget.
    Returns (text_widget, outer_frame) where outer_frame is the
    pack-managed Frame that contains the ScrolledText.
    """
    def _walk(widget, depth=0):
        if depth > 8:
            return None, None
        if isinstance(widget, tk.Text):
            w = widget.winfo_width()
            h = widget.winfo_height()
            if w > 300 and h > 200:
                # Walk up to find the outer pack-managed frame
                # ScrolledText: Text -> internal_frame -> outer_frame
                parent = widget.master
                outer  = parent.master if parent else parent
                return widget, outer
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

    # Restore chat widget and outer frame background colors
    if _state.get("chat_widget"):
        try:
            _state["chat_widget"].config(bg="#0a0a0f")
        except Exception:
            pass
        try:
            _state["chat_widget"].master.config(bg="#0a0a0f")
        except Exception:
            pass
    if _state.get("outer"):
        try:
            _state["outer"].config(bg="#0a0a0f")
        except Exception:
            pass
    _state["outer"] = None


def _apply_background(path: str, opacity: int, blur: bool):
    """
    Place background image in the outer chat container frame using place().
    The ScrolledText and its inner Text widget backgrounds are set to match
    the image's dominant edge color so the image shows through seamlessly.
    """
    root = _state["root"]
    if not root:
        return False

    try:
        chat, outer = _find_chat_container(root)
        if not chat or not outer:
            return False

        _state["chat_widget"] = chat
        root.update_idletasks()

        w = outer.winfo_width()  or chat.winfo_width()  or 600
        h = outer.winfo_height() or chat.winfo_height() or 400

        frames = _load_image(path, w, h, opacity, blur)
        if not frames:
            return False

        _clear_background()

        # Place image label inside the outer container frame
        # filling it completely with place(relwidth/relheight)
        lbl = tk.Label(outer, borderwidth=0, highlightthickness=0,
                       image=frames[0])
        lbl.image = frames[0]
        lbl.place(x=0, y=0, relwidth=1.0, relheight=1.0)
        lbl.lower()  # Push to bottom of outer frame stack

        # Lift the ScrolledText (chat.master.master == outer, chat.master is
        # the internal ScrolledText frame) above the label
        try:
            for sib in outer.winfo_children():
                if sib is not lbl:
                    sib.lift()
        except Exception:
            pass

        # Make Text widget and its internal frame backgrounds transparent
        # by setting them to empty string (falls back to parent bg on Windows)
        # Then set outer frame bg to black so label shows through gaps
        try:
            outer.config(bg="black")
        except Exception:
            pass
        try:
            chat.master.config(bg="")  # internal ScrolledText frame
        except Exception:
            pass
        try:
            chat.config(bg="")         # the Text widget itself
        except Exception:
            pass

        _state["label"]      = lbl
        _state["image_ref"]  = frames[0]
        _state["image_path"] = path
        _state["outer"]      = outer

        def _reposition(event=None):
            try:
                if not _state["label"]:
                    return
                nw = outer.winfo_width()
                nh = outer.winfo_height()
                if nw > 10 and nh > 10:
                    new_frames = _load_image(path, nw, nh, opacity, blur)
                    if new_frames:
                        _state["label"].config(image=new_frames[0])
                        _state["label"].image = new_frames[0]
                        _state["image_ref"]   = new_frames[0]
                        if len(new_frames) > 1:
                            _state["gif_frames"] = new_frames
                    # relwidth/relheight handles resize automatically
                    _state["label"].lower()
                    for sib in outer.winfo_children():
                        if sib is not _state["label"]:
                            try: sib.lift()
                            except Exception: pass
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
