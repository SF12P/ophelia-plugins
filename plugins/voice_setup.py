"""
plugins/voice_setup.py — Ophelia Voice Setup Plugin
=====================================================
Installs and configures Chatterbox-Turbo voice for Ophelia.
Shows a setup wizard on first run, then auto-starts voice server.

Triggers: "set up voice", "install voice", "voice setup", "enable voice"
Manual:   "run voice_setup"
"""

import os
import sys
import subprocess
import threading
import shutil
import tempfile
from pathlib import Path

NAME        = "voice_setup"
VERSION     = "1.0"
TRIGGERS    = ["set up voice", "install voice", "voice setup", "enable voice",
               "setup voice", "configure voice"]
DESCRIPTION = "Sets up Chatterbox-Turbo voice for Ophelia"
MANUAL_ONLY = False

# Where the chatterbox env lives relative to trm_base's parent
CHATTERBOX_ENV = "chatterbox_env"

# Chatterbox dependencies
CHATTERBOX_PACKAGES = [
    "chatterbox-tts",
    "torch",
    "torchaudio",
    "soundfile",
    "flask",
]


def _get_base_dir(context: dict) -> Path:
    """Get the Project Ophelia root directory."""
    cfg = context.get("cfg")
    if cfg:
        return Path(cfg.memory_dir).parent.parent
    return Path(__file__).parent.parent.parent


def _get_env_path(context: dict) -> Path:
    return _get_base_dir(context) / CHATTERBOX_ENV


def _env_exists(context: dict) -> bool:
    env = _get_env_path(context)
    py  = env / "Scripts" / "python.exe"
    return py.exists()


def _voice_server_exists(context: dict) -> bool:
    base = _get_base_dir(context) / "trm_base"
    return (base / "voice_server.py").exists()


def run(query: str, context: dict) -> str:
    """Plugin entry point — show setup wizard or status."""
    if _env_exists(context):
        return "Voice is already set up. Enable it from the Voice (Turbo) toggle in the sidebar."

    # Launch wizard in main thread via after() if possible
    try:
        import tkinter as tk
        root = tk._default_root
        if root:
            root.after(0, lambda: _show_wizard(context))
            return "Opening voice setup wizard..."
    except Exception:
        pass

    return ("Voice setup requires the GUI. "
            "Click 'Voice (Turbo)' in the sidebar to begin setup.")


def _show_wizard(context: dict):
    """Show the voice setup wizard window."""
    import tkinter as tk
    from tkinter import filedialog, messagebox

    BG     = "#0e0e12"; PANEL  = "#1c1c26"; MID    = "#16161e"
    ACCENT = "#c084fc"; DIM    = "#7c3aed"; TEXT   = "#e2e0f0"
    SUB    = "#6b6880"; GREEN  = "#4ade80"; RED    = "#f87171"
    AMBER  = "#fbbf24"
    FM = ("Consolas", 10); FB = ("Consolas", 10, "bold")
    FS = ("Consolas", 9);  FT = ("Consolas", 14, "bold")

    root = tk._default_root
    win  = tk.Toplevel(root)
    win.title("Voice Setup")
    win.configure(bg=BG)
    win.geometry("500x480")
    win.resizable(False, False)
    win.transient(root)
    win.grab_set()

    state = {"step": 0, "wav_path": "", "cancelled": False}

    def clear():
        for w in win.winfo_children():
            w.destroy()

    # ── Step 0: Welcome ──────────────────────────────────────────────
    def page_welcome():
        clear()
        tk.Label(win, text="◈  Voice Setup", bg=BG, fg=ACCENT,
                 font=FT).pack(pady=(32, 6))
        tk.Label(win,
                 text="This wizard will set up Ophelia's voice system.\n\n"
                      "Ophelia can speak her responses out loud using\n"
                      "a cloned voice — you provide a short audio sample\n"
                      "and she learns to sound like it.\n\n"
                      "Requirements:\n"
                      "  • About 500MB of free disk space\n"
                      "  • A short .wav recording (5-30 seconds)\n"
                      "  • Internet connection for initial download",
                 bg=BG, fg=TEXT, font=FM, justify=tk.CENTER).pack(padx=30)

        row = tk.Frame(win, bg=BG)
        row.pack(pady=24)
        tk.Button(row, text="Cancel", bg=MID, fg=SUB, font=FS,
                  relief=tk.FLAT, padx=14, pady=8, cursor="hand2",
                  command=win.destroy).pack(side=tk.LEFT, padx=8)
        tk.Button(row, text="Set Up Voice  →", bg=DIM, fg=TEXT, font=FB,
                  relief=tk.FLAT, padx=20, pady=8,
                  activebackground=ACCENT, cursor="hand2",
                  command=page_voice_sample).pack(side=tk.LEFT, padx=8)

    # ── Step 1: Voice sample ─────────────────────────────────────────
    def page_voice_sample():
        clear()
        tk.Label(win, text="Voice Sample", bg=BG, fg=ACCENT,
                 font=FB).pack(pady=(28, 6))
        tk.Label(win,
                 text="Choose a .wav audio file for Ophelia's voice.\n\n"
                      "Tips for best results:\n"
                      "  • 10-30 seconds of clear speech\n"
                      "  • Minimal background noise\n"
                      "  • Single speaker only\n\n"
                      "You can record one using Voice Recorder\n"
                      "on Windows, then export as .wav",
                 bg=BG, fg=TEXT, font=FM, justify=tk.CENTER).pack(padx=30)

        wav_lbl = tk.Label(win, text="No file selected",
                           bg=BG, fg=SUB, font=FS, wraplength=420)
        wav_lbl.pack(pady=8)

        def browse():
            path = filedialog.askopenfilename(
                title="Select voice sample",
                filetypes=[("WAV files","*.wav"),("All files","*.*")],
                parent=win)
            if path:
                state["wav_path"] = path
                wav_lbl.config(text=Path(path).name, fg=ACCENT)
                next_btn.config(state=tk.NORMAL)

        tk.Button(win, text="Browse for .wav file", bg=DIM, fg=TEXT,
                  font=FM, relief=tk.FLAT, padx=16, pady=8,
                  activebackground=ACCENT, cursor="hand2",
                  command=browse).pack(pady=4)

        row = tk.Frame(win, bg=BG)
        row.pack(pady=16)
        tk.Button(row, text="← Back", bg=MID, fg=SUB, font=FS,
                  relief=tk.FLAT, padx=14, pady=8, cursor="hand2",
                  command=page_welcome).pack(side=tk.LEFT, padx=8)
        next_btn = tk.Button(row, text="Install  →", bg=DIM, fg=TEXT,
                  font=FB, relief=tk.FLAT, padx=20, pady=8,
                  activebackground=ACCENT, cursor="hand2",
                  state=tk.DISABLED, command=page_install)
        next_btn.pack(side=tk.LEFT, padx=8)

    # ── Step 2: Installing ───────────────────────────────────────────
    def page_install():
        clear()
        tk.Label(win, text="Installing Voice...", bg=BG, fg=ACCENT,
                 font=FB).pack(pady=(28, 6))

        step_lbl = tk.Label(win, text="Starting...", bg=BG, fg=TEXT,
                             font=FM, wraplength=440, justify=tk.CENTER)
        step_lbl.pack(pady=(0, 10))

        bar_bg = tk.Frame(win, bg=MID, width=440, height=18)
        bar_bg.pack(padx=30, pady=6)
        bar_bg.pack_propagate(False)
        bar = tk.Frame(bar_bg, bg=ACCENT, height=18)
        bar.place(x=0, y=0, width=0, height=18)

        log = tk.Text(win, bg=MID, fg=SUB, font=FS, height=9,
                      relief=tk.FLAT, state=tk.DISABLED, wrap=tk.WORD)
        log.pack(padx=30, fill=tk.X, pady=8)

        def addlog(msg):
            def _do():
                log.config(state=tk.NORMAL)
                log.insert(tk.END, msg+"\n")
                log.see(tk.END)
                log.config(state=tk.DISABLED)
            win.after(0, _do)

        def setprog(pct):
            win.after(0, lambda: bar.place(
                x=0, y=0, width=int(440*pct/100), height=18))

        def setstep(msg):
            win.after(0, lambda: step_lbl.config(text=msg))

        def install():
            try:
                env_path = _get_env_path(context)
                py311    = "py"

                # 1 — Create venv
                setstep("Creating voice environment...")
                setprog(10)
                addlog("Creating Python environment...")
                subprocess.run(
                    [py311, "-3.11", "-m", "venv", str(env_path)],
                    check=True, capture_output=True)
                addlog("Environment created.")

                # 2 — Install packages
                setstep("Installing voice packages\n(this may take several minutes)...")
                setprog(30)
                env_py = str(env_path / "Scripts" / "python.exe")
                addlog("Installing Chatterbox-Turbo and dependencies...")
                addlog("(This downloads ~500MB, please wait...)")
                subprocess.run(
                    [env_py, "-m", "pip", "install", "--quiet"] + CHATTERBOX_PACKAGES,
                    check=True, capture_output=True)
                addlog("Voice packages installed.")
                setprog(70)

                # 3 — Copy voice sample
                setstep("Saving voice sample...")
                setprog(80)
                base     = _get_base_dir(context) / "trm_base"
                wav_dest = base / "Ophelia's Voice.wav"
                if state["wav_path"]:
                    shutil.copy2(state["wav_path"], str(wav_dest))
                    addlog(f"Voice sample saved: {wav_dest.name}")

                setprog(100)
                win.after(0, page_done_success)

            except Exception as e:
                addlog(f"Error: {e}")
                win.after(0, lambda: page_done_fail(str(e)))

        threading.Thread(target=install, daemon=True).start()

    # ── Step 3a: Success ─────────────────────────────────────────────
    def page_done_success():
        clear()
        tk.Label(win, text="✓  Voice Ready!", bg=BG, fg=GREEN,
                 font=FT).pack(pady=(44, 12))
        tk.Label(win,
                 text="Voice has been set up successfully.\n\n"
                      "To use it:\n"
                      "  1. Restart Ophelia\n"
                      "  2. Enable 'Voice (Turbo)' in the sidebar\n"
                      "  3. Enable 'Auto-start server'\n\n"
                      "Ophelia will speak her responses out loud.",
                 bg=BG, fg=TEXT, font=FM, justify=tk.CENTER).pack(padx=30)
        tk.Button(win, text="Close", bg=MID, fg=SUB, font=FS,
                  relief=tk.FLAT, padx=16, pady=8, cursor="hand2",
                  command=win.destroy).pack(pady=24)

    # ── Step 3b: Fail ────────────────────────────────────────────────
    def page_done_fail(error: str):
        clear()
        tk.Label(win, text="Setup Failed", bg=BG, fg=RED,
                 font=FT).pack(pady=(44, 12))
        tk.Label(win,
                 text="Voice setup didn't complete.\n\n"
                      "Try running Ophelia as Administrator\n"
                      "and making sure you have internet access.",
                 bg=BG, fg=TEXT, font=FM, justify=tk.CENTER).pack(padx=30)
        tk.Label(win, text=f"\n{error[:120]}", bg=BG, fg=SUB,
                 font=FS, wraplength=440, justify=tk.CENTER).pack(padx=30)
        tk.Button(win, text="Close", bg=MID, fg=SUB, font=FS,
                  relief=tk.FLAT, padx=16, pady=8, cursor="hand2",
                  command=win.destroy).pack(pady=20)

    page_welcome()
