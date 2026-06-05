"""
plugins/image_gen.py — Ophelia Image Generation Plugin
=========================================================
Fully self-contained — no changes to gui.py or any other file needed.

Drop into trm_base/plugins/ and enable from the plugin manager.

Triggers (natural language):
  "generate an image of...", "draw me...", "create an image of...", etc.

Chat commands (type in chat):
  image popup on      — show images in a separate window
  image popup off     — show images inline in chat (default)
  image model <id>    — switch to a different HuggingFace model
  image steps <n>     — set inference steps (default 20, more = slower but better)
  image size <n>      — set output size in pixels (512 or 768)
  image settings      — show current settings
  image clear cache   — delete downloaded model to free disk space

First use downloads the model (~1.7GB) and caches it in trm_memory/image_gen_model/.
VRAM is freed after each generation so it doesn't compete with Ollama.
"""

import os
import re
import threading
import time
from pathlib import Path

NAME        = "image_gen"
VERSION     = "1.1"
DESCRIPTION = "Local AI image generation using Stable Diffusion. Fully self-contained."
MANUAL_ONLY = False

TRIGGERS = [
    "generate an image", "generate image", "create an image", "create image",
    "draw me", "draw a ", "draw an ", "make an image", "make a picture",
    "show me an image", "paint a ", "paint an ", "imagine a ", "imagine an ",
    "render a ", "render an ", "picture of", "image of",
    # Settings commands
    "image popup", "image model", "image steps", "image size",
    "image settings", "image clear cache",
]

DEFAULT_MODEL = "stabilityai/sdxl-turbo"

# Settings exposed to the Plugin Manager UI
# Format: {pref_key: {label, type (bool/str/int/choice), default, choices (if choice)}}
# Available models with descriptions
MODEL_OPTIONS = {
    "stabilityai/sdxl-turbo":          "SDXL Turbo (fast, great quality, recommended)",
    "Lykon/dreamshaper-xl-turbo":       "Dreamshaper XL (artistic, vivid, great for characters)",
    "OFA-Sys/small-stable-diffusion-v0":"Small SD (lightweight, weaker quality)",
}

SETTINGS = {
    "image_gen_popup": {
        "label":   "Show images in popup window",
        "type":    "bool",
        "default": False,
    },
    "image_gen_steps": {
        "label":   "Inference steps (higher = better quality)",
        "type":    "int",
        "default": 20,
    },
    "image_gen_size": {
        "label":   "Output size (pixels)",
        "type":    "choice",
        "choices": ["512", "768"],
        "default": "512",
    },
    "image_gen_model": {
        "label":   "Image model",
        "type":    "choice",
        "choices": [
            "stabilityai/sdxl-turbo",
            "Lykon/dreamshaper-xl-turbo",
            "OFA-Sys/small-stable-diffusion-v0",
        ],
        "default": DEFAULT_MODEL,
    },
}

# Commands exposed to the help system
# Format: {command: description}
COMMANDS = {
    "image popup on":       "Show generated images in a separate popup window",
    "image popup off":      "Show generated images inline in chat (default)",
    "image steps <n>":      "Set inference steps — higher = better quality but slower (default 20)",
    "image size <n>":       "Set output size in pixels — 512 or 768 (default 512)",
    "image model <id>":     "Switch to a different HuggingFace model ID",
    "image settings":       "Show current image generation settings",
    "image clear cache":    "Delete the downloaded model to free disk space",
}
DEFAULT_STEPS = 20
DEFAULT_SIZE  = 512


# ── Settings ──────────────────────────────────────────────────────────

def _get_prefs() -> dict:
    try:
        from utils.prefs import Prefs
        p = Prefs()
        return {
            "model":  p.get("image_gen_model")  or DEFAULT_MODEL,
            "popup":  bool(p.get("image_gen_popup")),
            "steps":  int(p.get("image_gen_steps") or DEFAULT_STEPS),
            "size":   int(p.get("image_gen_size")  or DEFAULT_SIZE),
        }
    except Exception:
        return {"model": DEFAULT_MODEL, "popup": False,
                "steps": DEFAULT_STEPS, "size": DEFAULT_SIZE}


def _set_pref(key: str, value):
    try:
        from utils.prefs import Prefs
        Prefs().set(key, value)
    except Exception:
        pass


# ── Prompt extraction ─────────────────────────────────────────────────

def _extract_prompt(user_input: str) -> str:
    text = user_input.strip()
    patterns = [
        r"generate an image of\s+", r"generate image of\s+",
        r"generate an image\s+",    r"create an image of\s+",
        r"create image of\s+",      r"create an image\s+",
        r"draw me an?\s+",          r"draw me\s+",
        r"draw an?\s+",             r"make an image of\s+",
        r"make a picture of\s+",    r"show me an image of\s+",
        r"paint an?\s+",            r"imagine an?\s+",
        r"render an?\s+",           r"picture of\s+",
        r"image of\s+",
    ]
    for pat in patterns:
        cleaned = re.sub(pat, "", text, flags=re.IGNORECASE).strip()
        if cleaned and cleaned != text:
            return cleaned
    return text


# ── Settings commands ─────────────────────────────────────────────────

def _handle_settings_command(text: str) -> str | None:
    """
    Handle image gen chat commands.
    Returns a response string if this was a settings command, else None.
    """
    t = text.lower().strip()

    if t == "image popup on":
        _set_pref("image_gen_popup", True)
        return "Image generation set to popup window mode."

    if t == "image popup off":
        _set_pref("image_gen_popup", False)
        return "Image generation set to inline chat mode."

    if t == "image settings":
        p = _get_prefs()
        return (
            f"Image generation settings:\n"
            f"  Model:  {p['model']}\n"
            f"  Steps:  {p['steps']}\n"
            f"  Size:   {p['size']}x{p['size']}px\n"
            f"  Output: {'popup window' if p['popup'] else 'inline chat'}"
        )

    if t == "image clear cache":
        try:
            from utils.config import Config
            import shutil
            model_dir = Path(Config().memory_dir) / "image_gen_model"
            if model_dir.exists():
                shutil.rmtree(model_dir)
                return "Image model cache cleared. Next generation will re-download the model."
            return "No cached model found."
        except Exception as e:
            return f"Failed to clear cache: {e}"

    m = re.match(r"image steps (\d+)", t)
    if m:
        steps = max(1, min(150, int(m.group(1))))
        _set_pref("image_gen_steps", steps)
        return f"Inference steps set to {steps}. Higher = better quality but slower."

    m = re.match(r"image size (\d+)", t)
    if m:
        size = int(m.group(1))
        if size not in (512, 768):
            return "Size must be 512 or 768."
        _set_pref("image_gen_size", size)
        return f"Output size set to {size}x{size}px."

    m = re.match(r"image model (.+)", t)
    if m:
        model_id = m.group(1).strip()
        _set_pref("image_gen_model", model_id)
        # Clear old cache so new model downloads fresh
        try:
            from utils.config import Config
            import shutil
            model_dir = Path(Config().memory_dir) / "image_gen_model"
            if model_dir.exists():
                shutil.rmtree(model_dir)
        except Exception:
            pass
        return (
            f"Model set to: {model_id}\n"
            f"Old cache cleared. Next generation will download the new model."
        )

    return None


# ── Model management ──────────────────────────────────────────────────

def _get_model_dir() -> Path:
    try:
        from utils.config import Config
        return Path(Config().memory_dir) / "image_gen_model"
    except Exception:
        return Path("./trm_memory/image_gen_model")


def _is_cached() -> bool:
    return (_get_model_dir() / "model_index.json").exists()


def _download_model(model_id: str, on_status) -> bool:
    try:
        from diffusers import StableDiffusionPipeline
        import torch
        model_dir = _get_model_dir()
        model_dir.mkdir(parents=True, exist_ok=True)
        on_status(
            f"Downloading image model: {model_id}\n"
            f"This only happens once (~1.7GB). Please wait..."
        )
        model_id = prefs.get("model", DEFAULT_MODEL)
        PipeClass = _get_pipeline_class(model_id)
        pipe = PipeClass.from_pretrained(
            model_id,
            torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
            safety_checker=None,
            requires_safety_checker=False,
        )
        pipe.save_pretrained(str(model_dir))
        on_status("Model downloaded and cached.")
        return True
    except Exception as e:
        on_status(f"Download failed: {e}")
        return False


def _get_pipeline_class(model_id: str):
    """Return appropriate pipeline class for the model."""
    try:
        from diffusers import AutoPipelineForText2Image, StableDiffusionPipeline
        if "xl" in model_id.lower() or "sdxl" in model_id.lower():
            return AutoPipelineForText2Image
        return StableDiffusionPipeline
    except Exception:
        from diffusers import StableDiffusionPipeline
        return StableDiffusionPipeline


def _load_pipeline(prefs: dict):
    from diffusers import StableDiffusionPipeline
    import torch
    model_dir = _get_model_dir()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype  = torch.float16 if torch.cuda.is_available() else torch.float32
    pipe = StableDiffusionPipeline.from_pretrained(
        str(model_dir), torch_dtype=dtype,
        safety_checker=None, requires_safety_checker=False)
    pipe = pipe.to(device)
    try:
        pipe.enable_attention_slicing()
        pipe.enable_vae_slicing()
    except Exception:
        pass
    return pipe


# ── Generation ────────────────────────────────────────────────────────

def _generate(pipe, prompt: str, prefs: dict):
    size = prefs["size"]
    model_id = prefs.get("model", DEFAULT_MODEL)
    is_turbo = "turbo" in model_id.lower() or "sdxl-turbo" in model_id.lower()
    return pipe(
        prompt,
        num_inference_steps=prefs["steps"] if not is_turbo else min(prefs["steps"], 4),
        height=size, width=size,
        guidance_scale=0.0 if is_turbo else 7.5,
    ).images[0]


def _save_image(image) -> Path:
    try:
        from utils.config import Config
        out_dir = Path(Config().memory_dir) / "generated_images"
    except Exception:
        out_dir = Path("./trm_memory/generated_images")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"ophelia_{int(time.time())}.png"
    image.save(str(path))
    return path


# ── Display ───────────────────────────────────────────────────────────

def _find_chat_widget(root):
    import tkinter as tk
    def _search(w):
        if isinstance(w, tk.Text): return w
        for c in w.winfo_children():
            found = _search(c)
            if found: return found
        return None
    return _search(root)


def _show_inline(image_path: Path, prompt: str):
    try:
        import tkinter as tk
        from PIL import Image as PILImage, ImageTk
        root = tk._default_root
        if not root: return

        def _do():
            chat = _find_chat_widget(root)
            if not chat: return
            img = PILImage.open(str(image_path))
            img.thumbnail((400, 400))
            photo = ImageTk.PhotoImage(img)
            if not hasattr(root, "_img_refs"): root._img_refs = []
            root._img_refs.append(photo)
            chat.config(state=tk.NORMAL)
            chat.insert(tk.END, f"\n[Image: {prompt[:50]}]\n", "source")
            lbl = tk.Label(chat, image=photo, bg="#0e0e12", cursor="hand2")
            lbl.bind("<Button-1>", lambda e: _open_viewer(image_path))
            chat.window_create(tk.END, window=lbl)
            chat.insert(tk.END, "\n", "source")
            chat.config(state=tk.DISABLED)
            chat.see(tk.END)
        root.after(0, _do)
    except Exception:
        pass


def _show_popup(image_path: Path, prompt: str):
    try:
        import tkinter as tk
        from PIL import Image as PILImage, ImageTk
        root = tk._default_root
        if not root: return

        def _do():
            win = tk.Toplevel(root)
            win.title(f"Generated: {prompt[:40]}")
            win.configure(bg="#0e0e12")
            win.resizable(True, True)
            img = PILImage.open(str(image_path))
            photo = ImageTk.PhotoImage(img)
            win._photo = photo
            tk.Label(win, image=photo, bg="#0e0e12").pack(padx=10, pady=10)
            tk.Label(win, text=prompt, bg="#0e0e12", fg="#9ca3af",
                font=("Consolas", 9), wraplength=500,
                justify=tk.CENTER).pack(padx=10, pady=(0,6))
            def save_as():
                from tkinter import filedialog
                import shutil
                dest = filedialog.asksaveasfilename(
                    defaultextension=".png",
                    filetypes=[("PNG","*.png"),("All files","*.*")],
                    initialfile=image_path.name, parent=win)
                if dest: shutil.copy2(str(image_path), dest)
            tk.Button(win, text="Save As", bg="#1c1c26", fg="#c084fc",
                font=("Consolas",9), relief=tk.FLAT, padx=12, pady=5,
                cursor="hand2", command=save_as).pack(pady=(0,10))
        root.after(0, _do)
    except Exception:
        pass


def _open_viewer(image_path: Path):
    try:
        os.startfile(str(image_path))
    except Exception:
        try:
            import subprocess
            subprocess.run(["start", "", str(image_path)], shell=True)
        except Exception:
            pass


def _chat_status(msg: str):
    """Insert a status line into the chat window."""
    try:
        import tkinter as tk
        root = tk._default_root
        if not root: return
        def _do():
            chat = _find_chat_widget(root)
            if not chat: return
            chat.config(state=tk.NORMAL)
            chat.insert(tk.END, f"  {msg}\n", "source")
            chat.config(state=tk.DISABLED)
            chat.see(tk.END)
        root.after(0, _do)
    except Exception:
        pass


# ── Plugin entry point ────────────────────────────────────────────────

def run(query: str, context: dict) -> str:
    user_input = context["user_input"]

    # Check for settings commands first
    cmd_result = _handle_settings_command(user_input)
    if cmd_result is not None:
        return cmd_result

    # Check dependencies
    try:
        import diffusers
        from PIL import Image
    except ImportError:
        return (
            "Image generation needs additional packages. Run:\n"
            "  pip install diffusers transformers accelerate Pillow torch\n"
            "Then restart Ophelia."
        )

    prompt = _extract_prompt(user_input)
    if not prompt or len(prompt) < 3:
        return "Please describe what you'd like me to generate."

    prefs = _get_prefs()

    def _run_async():
        try:
            if not _is_cached():
                ok = _download_model(prefs["model"], _chat_status)
                if not ok:
                    return

            _chat_status(f"Generating: {prompt[:60]}...")
            # Show waiting message in chat
            try:
                import tkinter as tk
                root = tk._default_root
                if root:
                    def _show_wait():
                        pass  # handled by _asy in run()
                    root.after(0, _show_wait)
            except Exception:
                pass
            pipe  = _load_pipeline(prefs)
            image = _generate(pipe, prompt, prefs)
            path  = _save_image(image)

            # Free VRAM so Ollama isn't starved
            del pipe
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass

            if prefs["popup"]:
                _show_popup(path, prompt)
            else:
                _show_inline(path, prompt)

            _chat_status(f"Saved: {path.name}")

        except Exception as e:
            _chat_status(f"Image generation failed: {e}")

    threading.Thread(target=_run_async, daemon=True).start()
    return f"Generating: {prompt[:80]}. One moment..."
