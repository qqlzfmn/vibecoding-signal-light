"""macOS menu-bar GUI daemon for the signal light.

Runs a persistent ``rumps.App`` in the menu bar that polls
``sessions.json`` and renders the current aggregate signal as a coloured
icon.  Clicking the status item opens a small tkinter traffic-light panel
that runs in a separate process to avoid Cocoa/Tcl event-loop conflicts.
"""

from __future__ import annotations

import atexit
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from signal_light.agent_signals import SIGNALS, Frame
from signal_light.gui.const import ICON_COLOR_MAP
from signal_light.gui.icon_generator import generate_all_icons, get_icon_path
from signal_light.runtime import read_session_snapshot

POLL_INTERVAL = float(os.environ.get("SIGNAL_LIGHT_GUI_POLL_MS", "500")) / 1000.0


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

    The detail panel runs as a child process (``_panel_process``) with
    its own tkinter event loop, completely isolating Tcl/Tk from Cocoa.
    Commands are sent over the child's stdin as one-JSON-per-line.
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

        # Panel child process — spawned lazily on first toggle.
        self._panel_proc: subprocess.Popen | None = None
        self._panel_visible: bool = False

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
        self._reap_panel()

    def _reap_panel(self) -> None:
        """Detect if the panel child exited on its own (user closed window)."""
        proc = self._panel_proc
        if proc is not None and proc.poll() is not None:
            self._panel_proc = None
            self._panel_visible = False

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
        self._push_panel_update(aggregate, snapshot)

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

    def _push_panel_update(self, aggregate: str, snapshot: dict) -> None:
        if self._panel_proc is None or not self._panel_visible:
            return
        try:
            self._send_panel_cmd(self._build_panel_cmd(aggregate, snapshot))
        except Exception:
            pass

    def _build_panel_cmd(self, aggregate: str, snapshot: dict) -> dict:
        """Build a JSON-serialisable update command for the panel subprocess.

        Sends signal metadata and timing info so the subprocess can compute
        the flash state locally using the same algorithm as the icon.
        """
        signal = SIGNALS.get(aggregate)
        started_at = self._signal_started_at  # time.monotonic() value

        # Static leave_on state for non-repeating signals.
        leave_on: list[str] = []
        if signal and not signal.repeat and signal.leave_on is not None:
            if signal.leave_on[0]:
                leave_on.append("green")
            if signal.leave_on[1]:
                leave_on.append("yellow")
            if signal.leave_on[2]:
                leave_on.append("red")

        summary = signal.summary if signal else ""
        sessions = snapshot.get("sessions", {})
        count = len(sessions) if isinstance(sessions, dict) else 0
        return {
            "action": "update",
            "signal": aggregate,
            "repeat": bool(signal and signal.repeat and signal.frames),
            "flash_color": ICON_COLOR_MAP.get(aggregate, "grey"),
            "started_at": started_at,
            "poll_interval": POLL_INTERVAL,
            "leave_on": leave_on,
            "summary": summary,
            "sessions": count,
        }

    # ---- panel child process management ---------------------------------

    def _send_panel_cmd(self, cmd: dict) -> None:
        proc = self._panel_proc
        if proc is None or proc.poll() is not None:
            return
        try:
            proc.stdin.write((json.dumps(cmd) + "\n").encode())
            proc.stdin.flush()
        except Exception:
            pass

    def _spawn_panel(self) -> None:
        if self._panel_proc is not None and self._panel_proc.poll() is None:
            return
        self._panel_proc = subprocess.Popen(
            [sys.executable, "-m", "signal_light.gui._panel_process"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    # ---- panel toggle ---------------------------------------------------

    def _on_toggle_panel(self, _sender: Any = None) -> None:
        if self._panel_visible:
            self._hide_panel()
            return
        self._show_panel()

    def _show_panel(self) -> None:
        self._spawn_panel()
        # Send show with current state so the panel is never blank.
        try:
            snapshot = read_session_snapshot()
            aggregate = snapshot.get("aggregate", "idle")
            cmd = self._build_panel_cmd(aggregate, snapshot)
            cmd["action"] = "show"
            self._send_panel_cmd(cmd)
        except Exception:
            self._send_panel_cmd({"action": "show"})
        self._panel_visible = True

    def _hide_panel(self) -> None:
        self._send_panel_cmd({"action": "hide"})
        self._panel_visible = False

    # ---- quit -----------------------------------------------------------

    def _on_quit(self, _sender: Any = None) -> None:
        proc = self._panel_proc
        if proc is not None and proc.poll() is None:
            try:
                self._send_panel_cmd({"action": "quit"})
                proc.wait(timeout=2)
            except Exception:
                proc.kill()
            self._panel_proc = None
        self._rumps.quit_application()
