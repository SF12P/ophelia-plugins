"""
plugins/system_monitor.py — Ophelia System Monitor Overlay
============================================================
A compact always-on-top widget showing live CPU, RAM, and GPU stats.
Follows Ophelia's active skin by default.
Can be independently styled via the skin editor.

Commands:
  show monitor       — show the overlay
  hide monitor       — hide the overlay
  system stats       — show current stats in chat
  how is my pc       — same as system stats
"""

import threading
import time
import tkinter as tk
from pathlib import Path

NAME        = "system_monitor"
VERSION     = "1.0"
DESCRIPTION = "Always-on-top live system stats overlay — CPU, RAM, GPU."
MANUAL_ONLY = False
AUTHOR      = "SF12P"
TAGS        = ["utility", "system", "overlay"]
REQUIRES    = ["psutil"]

TRIGGERS = [
    "show monitor", "hide monitor", "system stats",
    "how is my pc", "pc stats", "cpu usage", "ram usage",
    "show overlay", "hide overlay",
]

COMMANDS = {
    "show monitor": "Show the system stats overlay",
    "hide monitor": "Hide the system stats overlay",
    "system stats": "Show current CPU/RAM/GPU in chat",
}

SETTINGS = {
    "position": {
        "label":   "Screen position",
        "type":    "choice",
        "choices": ["top-right", "top-left", "bottom-right", "bottom-left"],
        "default": "top-right",
    },
    "opacity": {
        "label":   "Opacity (0-100)",
        "type":    "int",
        "default": 85,
        "min":     20,
        "max":     100,
    },
    "show_gpu": {
        "label":   "Show GPU stats",
        "type":    "bool",
        "default": True,
    },
    "update_interval": {
        "label":   "Update interval (seconds)",
        "type":    "int",
        "default": 2,
        "min":     1,
        "max":     10,
    },
}

# Module-level overlay instance
_overlay = None
_context  = None


# ── Stats collection ──────────────────────────────────────────────────────────

def _get_stats(show_gpu: bool = True) -> dict:
    try:
        import psutil
        cpu  = psutil.cpu_percent(interval=0.1)
        ram  = psutil.virtual_memory()
        ram_used  = ram.used  / (1024**3)
        ram_total = ram.total / (1024**3)
        ram_pct   = ram.percent

        stats = {
            "cpu":       cpu,
            "ram_used":  round(ram_used, 1),
            "ram_total": round(ram_total, 1),
            "ram_pct":   ram_pct,
            "gpu_name":  "",
            "gpu_load":  None,
            "gpu_mem":   None,
            "gpu_temp":  None,
        }

        if show_gpu:
            try:
                import GPUtil
                gpus = GPUtil.getGPUs()
                if gpus:
                    g = gpus[0]
                    stats["gpu_name"] = g.name.replace("NVIDIA GeForce","").strip()
                    stats["gpu_load"] = round(g.load * 100, 1)
                    stats["gpu_mem"]  = round(g.memoryUsed, 0)
                    stats["gpu_temp"] = round(g.temperature, 0)
            except ImportError:
                # Try pynvml as fallback
                try:
                    import pynvml
                    pynvml.nvmlInit()
                    h = pynvml.nvmlDeviceGetHandleByIndex(0)
                    name = pynvml.nvmlDeviceGetName(h)
                    if isinstance(name, bytes): name = name.decode()
                    util = pynvml.nvmlDeviceGetUtilizationRates(h)
                    mem  = pynvml.nvmlDeviceGetMemoryInfo(h)
                    temp = pynvml.nvmlDeviceGetTemperature(h, pynvml.NVML_TEMPERATURE_GPU)
                    stats["gpu_name"] = name.replace("NVIDIA GeForce","").strip()
                    stats["gpu_load"] = util.gpu
                    stats["gpu_mem"]  = round(mem.used / (1024**2), 0)
                    stats["gpu_temp"] = temp
                except Exception:
                    pass
            except Exception:
                pass

        return stats
    except Exception as e:
        return {"error": str(e)}


def _format_stats_chat(stats: dict) -> str:
    if "error" in stats:
        return f"Could not read system stats: {stats['error']}"

    lines = [
        f"CPU:  {stats['cpu']}%",
        f"RAM:  {stats['ram_used']}GB / {stats['ram_total']}GB  ({stats['ram_pct']}%)",
    ]
    if stats.get("gpu_load") is not None:
        name = stats.get("gpu_name","GPU")
        lines.append(
            f"GPU:  {name}  {stats['gpu_load']}%  "
            f"{stats['gpu_mem']}MB  {stats['gpu_temp']}°C"
        )
    return "\n".join(lines)


# ── Overlay widget ────────────────────────────────────────────────────────────

class SystemOverlay:

    def __init__(self, root: tk.Tk, prefs: dict, cfg=None):
        self.root      = root
        self.prefs     = prefs
        self.cfg       = cfg
        self._running  = False
        self._thread   = None
        self._win      = None
        self._labels   = {}
        self._custom_colors = {}  # set by skin editor
        self._build()

    def _get_skin_colors(self) -> dict:
        """Read current skin colors from prefs — fallback to defaults."""
        try:
            from utils.prefs import Prefs
            p = Prefs()
            skin = p.get("skin") or {}
            return {
                "bg":      skin.get("BG_DARK",  "#0a0a0f"),
                "fg":      skin.get("TEXT_PRIMARY", "#e2e0f0"),
                "accent":  skin.get("ACCENT",   "#c084fc"),
                "dim":     skin.get("TEXT_DIM",  "#6b6880"),
                "border":  skin.get("BORDER",    "#1e1e2e"),
            }
        except Exception:
            return {
                "bg":     "#0a0a0f",
                "fg":     "#e2e0f0",
                "accent": "#c084fc",
                "dim":    "#6b6880",
                "border": "#1e1e2e",
            }

    def _colors(self) -> dict:
        # Custom colors override skin
        skin = self._get_skin_colors()
        skin.update(self._custom_colors)
        return skin

    def _build(self):
        c = self._colors()

        self._win = tk.Toplevel(self.root)
        self._win.overrideredirect(True)       # no title bar
        self._win.wm_attributes("-topmost", True)
        self._win.wm_attributes("-alpha", self.prefs.get("opacity", 85) / 100)
        self._win.configure(bg=c["bg"])
        self._win.resizable(False, False)

        # Thin border frame
        border = tk.Frame(self._win, bg=c["border"], padx=1, pady=1)
        border.pack(fill=tk.BOTH, expand=True)

        inner = tk.Frame(border, bg=c["bg"], padx=10, pady=6)
        inner.pack(fill=tk.BOTH, expand=True)

        font_label = ("Consolas", 8)
        font_value = ("Consolas", 9, "bold")

        # CPU row
        cpu_row = tk.Frame(inner, bg=c["bg"])
        cpu_row.pack(fill=tk.X, pady=1)
        tk.Label(cpu_row, text="CPU", bg=c["bg"], fg=c["dim"],
            font=font_label, width=4, anchor=tk.W).pack(side=tk.LEFT)
        self._labels["cpu"] = tk.Label(cpu_row, text="—",
            bg=c["bg"], fg=c["accent"], font=font_value, anchor=tk.W)
        self._labels["cpu"].pack(side=tk.LEFT)
        self._labels["cpu_bar"] = tk.Label(cpu_row, text="",
            bg=c["bg"], fg=c["dim"], font=("Consolas",7), anchor=tk.W)
        self._labels["cpu_bar"].pack(side=tk.LEFT, padx=(4,0))

        # RAM row
        ram_row = tk.Frame(inner, bg=c["bg"])
        ram_row.pack(fill=tk.X, pady=1)
        tk.Label(ram_row, text="RAM", bg=c["bg"], fg=c["dim"],
            font=font_label, width=4, anchor=tk.W).pack(side=tk.LEFT)
        self._labels["ram"] = tk.Label(ram_row, text="—",
            bg=c["bg"], fg=c["accent"], font=font_value, anchor=tk.W)
        self._labels["ram"].pack(side=tk.LEFT)
        self._labels["ram_bar"] = tk.Label(ram_row, text="",
            bg=c["bg"], fg=c["dim"], font=("Consolas",7), anchor=tk.W)
        self._labels["ram_bar"].pack(side=tk.LEFT, padx=(4,0))

        # GPU row (hidden if no GPU detected)
        self._gpu_row = tk.Frame(inner, bg=c["bg"])
        self._gpu_row.pack(fill=tk.X, pady=1)
        tk.Label(self._gpu_row, text="GPU", bg=c["bg"], fg=c["dim"],
            font=font_label, width=4, anchor=tk.W).pack(side=tk.LEFT)
        self._labels["gpu"] = tk.Label(self._gpu_row, text="—",
            bg=c["bg"], fg=c["accent"], font=font_value, anchor=tk.W)
        self._labels["gpu"].pack(side=tk.LEFT)
        self._labels["gpu_bar"] = tk.Label(self._gpu_row, text="",
            bg=c["bg"], fg=c["dim"], font=("Consolas",7), anchor=tk.W)
        self._labels["gpu_bar"].pack(side=tk.LEFT, padx=(4,0))

        # Drag support
        self._drag_x = 0
        self._drag_y = 0
        self._win.bind("<ButtonPress-1>",   self._drag_start)
        self._win.bind("<B1-Motion>",        self._drag_move)
        for w in self._win.winfo_children():
            w.bind("<ButtonPress-1>",  self._drag_start)
            w.bind("<B1-Motion>",       self._drag_move)

        self._position_window()
        self._win.withdraw()  # hidden until show() called

    def _make_bar(self, pct: float, width: int = 8) -> str:
        """Simple ASCII progress bar."""
        filled = int((pct / 100) * width)
        return f"[{'█'*filled}{'░'*(width-filled)}]"

    def _color_for_pct(self, pct: float, c: dict) -> str:
        if pct >= 90: return "#f87171"   # red
        if pct >= 70: return "#fbbf24"   # amber
        return c["accent"]

    def _position_window(self):
        pos = self.prefs.get("position", "top-right")
        self._win.update_idletasks()
        w = self._win.winfo_reqwidth()
        h = self._win.winfo_reqheight()
        sw = self._win.winfo_screenwidth()
        sh = self._win.winfo_screenheight()
        pad = 16
        positions = {
            "top-right":    (sw - w - pad,      pad),
            "top-left":     (pad,                pad),
            "bottom-right": (sw - w - pad,      sh - h - pad - 48),
            "bottom-left":  (pad,               sh - h - pad - 48),
        }
        x, y = positions.get(pos, positions["top-right"])
        self._win.geometry(f"+{x}+{y}")

    def _drag_start(self, event):
        self._drag_x = event.x_root - self._win.winfo_x()
        self._drag_y = event.y_root - self._win.winfo_y()

    def _drag_move(self, event):
        x = event.x_root - self._drag_x
        y = event.y_root - self._drag_y
        self._win.geometry(f"+{x}+{y}")

    def show(self):
        self._win.deiconify()
        self._win.lift()
        self._running = True
        if not self._thread or not self._thread.is_alive():
            self._thread = threading.Thread(
                target=self._update_loop, daemon=True)
            self._thread.start()

    def hide(self):
        self._running = False
        self._win.withdraw()

    def destroy(self):
        self._running = False
        try: self._win.destroy()
        except Exception: pass

    def refresh_skin(self):
        """Called when skin changes — rebuild colors."""
        try:
            c = self._colors()
            self._win.configure(bg=c["bg"])
            self._win.wm_attributes("-alpha", self.prefs.get("opacity", 85) / 100)
            for widget in self._win.winfo_children():
                try: widget.configure(bg=c["bg"])
                except Exception: pass
                for child in widget.winfo_children():
                    try: child.configure(bg=c["bg"])
                    except Exception: pass
        except Exception:
            pass

    def _update_loop(self):
        interval = max(1, self.prefs.get("update_interval", 2))
        show_gpu = self.prefs.get("show_gpu", True)
        while self._running:
            try:
                stats = _get_stats(show_gpu)
                self.root.after(0, lambda s=stats: self._update_display(s))
            except Exception:
                pass
            time.sleep(interval)

    def _update_display(self, stats: dict):
        if not self._running or not self._win:
            return
        try:
            c = self._colors()

            cpu_pct = stats.get("cpu", 0)
            cpu_clr = self._color_for_pct(cpu_pct, c)
            self._labels["cpu"].config(
                text=f"{cpu_pct:.0f}%",
                fg=cpu_clr)
            self._labels["cpu_bar"].config(
                text=self._make_bar(cpu_pct))

            ram_pct = stats.get("ram_pct", 0)
            ram_clr = self._color_for_pct(ram_pct, c)
            self._labels["ram"].config(
                text=f"{stats.get('ram_used',0)}G/{stats.get('ram_total',0)}G",
                fg=ram_clr)
            self._labels["ram_bar"].config(
                text=self._make_bar(ram_pct))

            gpu_load = stats.get("gpu_load")
            if gpu_load is not None:
                gpu_clr = self._color_for_pct(gpu_load, c)
                gpu_mem  = stats.get("gpu_mem", 0)
                gpu_temp = stats.get("gpu_temp", 0)
                self._labels["gpu"].config(
                    text=f"{gpu_load:.0f}%  {gpu_mem:.0f}MB  {gpu_temp}°C",
                    fg=gpu_clr)
                self._labels["gpu_bar"].config(
                    text=self._make_bar(gpu_load))
                self._gpu_row.pack(fill=tk.X, pady=1)
            else:
                self._gpu_row.pack_forget()

        except Exception:
            pass


# ── Lifecycle hooks ───────────────────────────────────────────────────────────

def on_startup(context: dict):
    global _overlay, _context
    _context = context
    try:
        import tkinter as tk
        root = tk._default_root
        if not root:
            return
        prefs_raw = {
            "position":        context["cfg"].get("monitor_position", "top-right") if hasattr(context["cfg"], "get") else "top-right",
            "opacity":         85,
            "show_gpu":        True,
            "update_interval": 2,
        }
        # Read from plugin settings if available
        try:
            from utils.prefs import Prefs
            p = Prefs()
            prefs_raw["position"]        = p.get("monitor_position") or "top-right"
            prefs_raw["opacity"]         = int(p.get("monitor_opacity") or 85)
            prefs_raw["show_gpu"]        = bool(p.get("monitor_show_gpu") if p.get("monitor_show_gpu") is not None else True)
            prefs_raw["update_interval"] = int(p.get("monitor_interval") or 2)
        except Exception:
            pass

        _overlay = SystemOverlay(root, prefs_raw)

        # Register rebuild hook for skin changes
        context["shared_state"]["on_gui_rebuild"] = lambda: (
            _overlay.refresh_skin() if _overlay else None)

    except Exception as e:
        print(f"[system_monitor] startup error: {e}")


def on_shutdown(context: dict):
    global _overlay
    if _overlay:
        try: _overlay.destroy()
        except Exception: pass
        _overlay = None


# ── Run (triggered by chat) ───────────────────────────────────────────────────

def run(query: str, context: dict) -> str:
    global _overlay
    text = context["user_input"].lower().strip()

    # Show stats in chat
    if any(k in text for k in ["system stats","how is my pc","pc stats",
                                "cpu usage","ram usage"]):
        show_gpu = True
        if _overlay:
            show_gpu = _overlay.prefs.get("show_gpu", True)
        stats = _get_stats(show_gpu)
        return _format_stats_chat(stats)

    # Show/hide overlay
    if "hide" in text or "close" in text:
        if _overlay:
            _overlay.hide()
            return "System monitor hidden."
        return "System monitor is not running."

    if "show" in text or "open" in text:
        if _overlay:
            _overlay.show()
            return "System monitor shown."
        return "System monitor could not start — is psutil installed?"

    # Default — show if hidden, hide if showing
    if _overlay:
        if _overlay._running:
            _overlay.hide()
            return "System monitor hidden."
        else:
            _overlay.show()
            return "System monitor shown."

    return "Say 'show monitor' or 'hide monitor' to control the overlay."
