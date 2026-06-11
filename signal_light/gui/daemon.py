"""macOS menu-bar GUI daemon for the signal light.

Runs a persistent ``rumps.App`` in the menu bar that polls
``sessions.json`` and renders the current aggregate signal as a coloured
icon.  Clicking the status item opens a small tkinter traffic-light panel.
"""

from __future__ import annotations

import atexit
import os
import time
from pathlib import Path
from typing import Any

from signal_light.agent_signals import SIGNALS, Frame
from signal_light.gui.icon_generator import generate_all_icons, get_icon_path
from signal_light.runtime import read_session_snapshot

POLL_INTERVAL = float(os.environ.get("SIGNAL_LIGHT_GUI_POLL_MS", "500")) / 1000.0

ICON_COLOR_MAP: dict[str, str] = {
    "idle": "green",
    "thinking": "green",
    "working": "green",
    "tool_done": "green",
    "attention": "yellow",
    "permission": "yellow",
    "done": "yellow",
    "blocked": "red",
    "session_start": "green",
    "session_end": "green",
    "session_done": "green",
    "off": "grey",
}


# ---------------------------------------------------------------------------
# Pure animation helpers (testable without any GUI).
# ---------------------------------------------------------------------------

def compute_current_frame(elapsed: float, frames: tuple[Frame, ...]) -> tuple[int, Frame]:
    """Return the *(index, frame)* that should be displayed at *elapsed* seconds."""
    if not frames:
        return (0, Frame())
    total = sum(f.seconds for f in frames)
    if total <= 0:
        return (0, frames[0])
    t = elapsed % total
    cumulative = 0.0
    for i, frame in enumerate(frames):
        cumulative += frame.seconds
        if t < cumulative:
            return (i, frame)
    return (len(frames) - 1, frames[-1])


# ---------------------------------------------------------------------------
# GUI daemon
# ---------------------------------------------------------------------------

def run_gui_daemon() -> int:
    """Entry-point: create and run the menu-bar application."""
    import rumps  # Lazy import — only needed when actually running the GUI.

    state_dir = Path(os.environ.get("SIGNAL_LIGHT_STATE_DIR", "/private/tmp/signal-light"))
    pid_file = state_dir / "gui-daemon.pid"

    state_dir.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(str(os.getpid()))
    atexit.register(_cleanup_pid_file, pid_file)

    app = _SignalLightApp(state_dir, rumps)
    app.run()
    return 0


def _cleanup_pid_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass


class _SignalLightApp:
    """Menu-bar application that shows the aggregate agent signal.

    Instantiated with the ``rumps`` module so the import is deferred to runtime.

    tkinter is driven from the rumps timer (no separate thread) to avoid
    macOS framework conflicts between NSApplication and Tk.
    """

    def __init__(self, state_dir: Path, rumps_mod: Any) -> None:
        self._rumps = rumps_mod
        self._icons = generate_all_icons(state_dir / "icons")
        grey_icon = get_icon_path(self._icons, "grey")

        # ``title=None`` prevents rumps from displaying a text label next to
        # the icon — we only want the coloured circle.
        self._app = rumps_mod.App("Signal Light", icon=str(grey_icon), title=None)

        # Disable rumps' built-in Quit button; we add our own in _build_menu.
        self._app.quit_button = None

        self._current_aggregate: str = "off"
        self._signal_started_at: float = time.monotonic()

        # tkinter — created lazily on first panel show, driven by the timer.
        self._tk_root: Any = None
        self._panel: _DetailPanel | None = None

        self._build_menu()

        self._timer = rumps_mod.Timer(self._on_tick, POLL_INTERVAL)
        self._timer.start()

    def run(self) -> None:
        self._app.run()

    # ---- menu -----------------------------------------------------------

    def _build_menu(self) -> None:
        rumps = self._rumps
        self._app.menu.clear()
        self._app.menu = [
            rumps.MenuItem("Show Details", callback=self._on_toggle_panel),
            rumps.separator,
            rumps.MenuItem("Quit", callback=self._on_quit),
        ]

    # ---- timer callback (main thread) -----------------------------------

    def _on_tick(self, _timer: Any = None) -> None:
        self._poll_session()
        self._pump_tk()

    def _poll_session(self) -> None:
        try:
            snapshot = read_session_snapshot()
            aggregate = snapshot.get("aggregate", "idle")
        except Exception:
            return

        if aggregate != self._current_aggregate:
            old_signal = SIGNALS.get(self._current_aggregate)
            new_signal = SIGNALS.get(aggregate)
            old_repeat = old_signal.repeat if old_signal else False
            new_repeat = new_signal.repeat if new_signal else False
            self._current_aggregate = aggregate
            if old_repeat != new_repeat:
                self._signal_started_at = time.monotonic()

        self._update_icon(aggregate)
        self._update_panel(aggregate, snapshot)

    def _update_icon(self, aggregate: str) -> None:
        signal = SIGNALS.get(aggregate)
        if signal is None:
            self._app.icon = str(get_icon_path(self._icons, "grey"))
            return

        color = ICON_COLOR_MAP.get(aggregate, "grey")

        if signal.repeat and signal.frames:
            elapsed = time.monotonic() - self._signal_started_at
            flash_on = int(elapsed / POLL_INTERVAL) % 2 == 0
            brightness = 1.0 if flash_on else 0.0
        elif signal.leave_on is not None:
            brightness = 1.0
        else:
            brightness = 1.0

        self._app.icon = str(get_icon_path(self._icons, color, brightness))

    def _update_panel(self, aggregate: str, snapshot: dict) -> None:
        panel = self._panel
        if panel is None:
            return
        try:
            signal = SIGNALS.get(aggregate)
            frame: Frame | None = None
            if signal and signal.repeat and signal.frames:
                elapsed = time.monotonic() - self._signal_started_at
                _, frame = compute_current_frame(elapsed, signal.frames)
            elif signal and signal.leave_on is not None:
                frame = Frame(
                    green=signal.leave_on[0],
                    yellow=signal.leave_on[1],
                    red=signal.leave_on[2],
                )
            panel.update(aggregate, frame, snapshot)
        except Exception:
            pass

    # ---- tkinter pump (main thread, driven by rumps timer) --------------

    def _pump_tk(self) -> None:
        """Process pending tkinter events — called every timer tick."""
        root = self._tk_root
        if root is None:
            return
        try:
            root.update()
        except Exception:
            self._tk_root = None
            self._panel = None

    # ---- panel toggle ---------------------------------------------------

    def _on_toggle_panel(self, _sender: Any = None) -> None:
        if self._panel is not None and self._panel.is_visible:
            self._hide_panel()
            return
        self._ensure_tk()
        self._show_panel()

    def _ensure_tk(self) -> None:
        if self._tk_root is not None:
            return
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        self._tk_root = root
        self._panel = _DetailPanel(root)

    def _show_panel(self) -> None:
        if self._panel is None:
            return
        self._panel.show()

    def _hide_panel(self) -> None:
        if self._panel is not None:
            self._panel.hide()

    # ---- quit -----------------------------------------------------------

    def _on_quit(self, _sender: Any = None) -> None:
        if self._panel is not None:
            self._panel.destroy()
            self._panel = None
        if self._tk_root is not None:
            try:
                self._tk_root.destroy()
            except Exception:
                pass
            self._tk_root = None
        self._rumps.quit_application()


# ---------------------------------------------------------------------------
# Floating detail panel (tkinter, driven from main thread)
# ---------------------------------------------------------------------------

class _DetailPanel:
    """Small floating window that visualises the traffic light and session state."""

    _PANEL_W = 260
    _PANEL_H = 340
    _LIGHT_R = 20
    _LIGHT_GAP = 16
    _LIGHT_X = 50

    _ACTIVE_COLORS: dict[str, str] = {"green": "#4CAF50", "yellow": "#FFC107", "red": "#F44336"}
    _DIM_COLOR = "#3A3A3A"

    def __init__(self, root: Any) -> None:
        import tkinter as tk

        self._root = root
        self._visible = False

        self._win = tk.Toplevel(root)
        self._win.title("Signal Light")
        self._win.attributes("-topmost", True)
        try:
            self._win.attributes("-alpha", 0.95)
        except Exception:
            pass
        self._win.configure(bg="#1E1E1E")
        self._win.geometry(f"{self._PANEL_W}x{self._PANEL_H}")
        self._win.withdraw()

        self._win.protocol("WM_DELETE_WINDOW", self.hide)

        # ---- traffic light canvas ----
        self._canvas = tk.Canvas(
            self._win,
            width=self._LIGHT_X * 2,
            height=self._PANEL_H - 100,
            bg="#1E1E1E",
            highlightthickness=0,
        )
        self._canvas.pack(pady=(16, 4))

        cx = self._LIGHT_X
        self._oval_ids: dict[str, int] = {}
        y = 30
        for color in ("red", "yellow", "green"):
            oid = self._canvas.create_oval(
                cx - self._LIGHT_R, y - self._LIGHT_R,
                cx + self._LIGHT_R, y + self._LIGHT_R,
                fill=self._DIM_COLOR, outline="#555555", width=2,
            )
            self._oval_ids[color] = oid
            y += self._LIGHT_R * 2 + self._LIGHT_GAP

        # ---- labels ----
        self._signal_label = tk.Label(
            self._win, text="—", fg="#CCCCCC", bg="#1E1E1E",
            font=("SF Pro Text", 16, "bold"),
        )
        self._signal_label.pack(anchor="w", padx=16, pady=(8, 0))

        self._summary_label = tk.Label(
            self._win, text="", fg="#999999", bg="#1E1E1E",
            font=("SF Pro Text", 11), wraplength=self._PANEL_W - 32, justify="left",
        )
        self._summary_label.pack(anchor="w", padx=16)

        self._session_label = tk.Label(
            self._win, text="", fg="#777777", bg="#1E1E1E",
            font=("SF Pro Text", 10), wraplength=self._PANEL_W - 32, justify="left",
        )
        self._session_label.pack(anchor="w", padx=16, pady=(12, 0))

    # ---- public API -----------------------------------------------------

    @property
    def is_visible(self) -> bool:
        return self._visible

    def show(self) -> None:
        self._position()
        self._win.deiconify()
        self._win.lift()
        self._visible = True

    def hide(self) -> None:
        self._win.withdraw()
        self._visible = False

    def destroy(self) -> None:
        try:
            self._win.destroy()
        except Exception:
            pass

    def update(self, aggregate: str, frame: Frame | None, snapshot: dict) -> None:
        signal = SIGNALS.get(aggregate)
        # Traffic light circles.
        for color, oid in self._oval_ids.items():
            if frame is not None and _frame_has_color(frame, color):
                self._canvas.itemconfig(oid, fill=self._ACTIVE_COLORS[color])
            else:
                self._canvas.itemconfig(oid, fill=self._DIM_COLOR)

        # Signal name.
        display = aggregate.replace("_", " ").title()
        self._signal_label.config(text=display)

        # Summary text.
        summary = signal.summary if signal else ""
        self._summary_label.config(text=summary)

        # Session count.
        sessions = snapshot.get("sessions", {})
        count = len(sessions) if isinstance(sessions, dict) else 0
        self._session_label.config(text=f"Active sessions: {count}")

    # ---- private helpers ------------------------------------------------

    def _position(self) -> None:
        try:
            screen_w = self._root.winfo_screenwidth()
            screen_h = self._root.winfo_screenheight()
            x = screen_w - self._PANEL_W - 20
            y = min(32, screen_h - self._PANEL_H - 20)
            self._win.geometry(f"+{x}+{y}")
        except Exception:
            pass


def _frame_has_color(frame: Frame, color: str) -> bool:
    if color == "green":
        return frame.green
    if color == "yellow":
        return frame.yellow
    if color == "red":
        return frame.red
    return False
