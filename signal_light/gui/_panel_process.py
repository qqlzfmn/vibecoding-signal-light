"""Panel child process — runs a standalone tkinter window.

Launched by the GUI daemon as a subprocess.  Reads JSON commands from
stdin (one per line) and drives the tkinter panel accordingly.

The subprocess computes flash/blink animations locally using
``time.monotonic()`` so that the panel and the menu-bar icon share
exactly the same timing source and stay perfectly in sync.

Expected commands::

    {"action": "show"}
    {"action": "show", "signal": "working", "repeat": true, "started_at": 123.4,
     "poll_interval": 0.5, "leave_on": [], "summary": "...", "sessions": 1}
    {"action": "update", ...}   # same fields as show (minus action)
    {"action": "hide"}
    {"action": "quit"}

When stdin closes (parent exited) the window is destroyed and the
process exits.
"""

from __future__ import annotations

import json
import sys
import time
import tkinter as tk

from signal_light.gui.const import (
    COLOR_DIM_HEX,
    COLOR_HEX_MAP,
    COLOR_OUTLINE_HEX,
    LIGHT_GAP,
    LIGHT_R,
    LIGHT_X,
    PANEL_H,
    PANEL_W,
)


class _DetailPanel:
    """Floating traffic-light panel with local flash animation."""

    def __init__(self, root: tk.Tk) -> None:
        self._root = root

        # Animation state (updated by commands from the daemon).
        self._repeat: bool = False
        self._flash_color: str = "green"
        self._started_at: float = 0.0
        self._poll_interval: float = 0.5
        self._leave_on: list[str] = []
        self._current_signal: str = "idle"

        self._win = tk.Toplevel(root)
        self._win.title("Signal Light")
        self._win.attributes("-topmost", True)
        try:
            self._win.attributes("-alpha", 0.95)
        except Exception:
            pass
        self._win.configure(bg="#1E1E1E")
        self._win.geometry(f"{PANEL_W}x{PANEL_H}")
        self._win.withdraw()
        self._win.protocol("WM_DELETE_WINDOW", self.hide)

        # ---- traffic light canvas ----
        self._canvas = tk.Canvas(
            self._win,
            width=LIGHT_X * 2,
            height=PANEL_H - 100,
            bg="#1E1E1E",
            highlightthickness=0,
        )
        self._canvas.pack(pady=(16, 4))

        cx = LIGHT_X
        self._ovals: dict[str, int] = {}
        y = 30
        for color in ("red", "yellow", "green"):
            oid = self._canvas.create_oval(
                cx - LIGHT_R, y - LIGHT_R,
                cx + LIGHT_R, y + LIGHT_R,
                fill=COLOR_DIM_HEX, outline=COLOR_OUTLINE_HEX, width=2,
            )
            self._ovals[color] = oid
            y += LIGHT_R * 2 + LIGHT_GAP

        # ---- labels ----
        self._signal_label = tk.Label(
            self._win, text="—", fg="#CCCCCC", bg="#1E1E1E",
            font=("SF Pro Text", 16, "bold"),
        )
        self._signal_label.pack(anchor="w", padx=16, pady=(8, 0))

        self._summary_label = tk.Label(
            self._win, text="", fg="#999999", bg="#1E1E1E",
            font=("SF Pro Text", 11), wraplength=PANEL_W - 32, justify="left",
        )
        self._summary_label.pack(anchor="w", padx=16)

        self._session_label = tk.Label(
            self._win, text="", fg="#777777", bg="#1E1E1E",
            font=("SF Pro Text", 10), wraplength=PANEL_W - 32, justify="left",
        )
        self._session_label.pack(anchor="w", padx=16, pady=(12, 0))

    # ---- public API -----------------------------------------------------

    def show(self) -> None:
        self._position()
        self._win.deiconify()
        self._win.lift()
        self._win.focus_force()

    def hide(self) -> None:
        self._win.withdraw()

    def apply_cmd(self, cmd: dict) -> None:
        """Apply an update command from the daemon."""
        self._current_signal = cmd.get("signal", self._current_signal)
        self._repeat = cmd.get("repeat", False)
        self._flash_color = cmd.get("flash_color", self._flash_color)
        self._started_at = cmd.get("started_at", self._started_at)
        self._poll_interval = cmd.get("poll_interval", 0.5)
        self._leave_on = cmd.get("leave_on", self._leave_on)

        # Update text labels immediately.
        self._signal_label.config(
            text=self._current_signal.replace("_", " ").title(),
        )
        self._summary_label.config(text=cmd.get("summary", ""))
        self._session_label.config(
            text=f"Active sessions: {cmd.get('sessions', 0)}",
        )
        # Lights are refreshed by tick_animation().

    def tick_animation(self) -> None:
        """Recompute light state — called every ~16 ms from the event loop."""
        active: list[str] = []
        if self._repeat:
            # Same algorithm as the menu-bar icon: toggle every poll_interval.
            elapsed = time.monotonic() - self._started_at
            flash_on = int(elapsed / self._poll_interval) % 2 == 0
            if flash_on:
                active = [self._flash_color]
        else:
            active = list(self._leave_on)

        for color, oid in self._ovals.items():
            fill = COLOR_HEX_MAP.get(color, COLOR_DIM_HEX) if color in active else COLOR_DIM_HEX
            self._canvas.itemconfig(oid, fill=fill)

    def destroy(self) -> None:
        try:
            self._win.destroy()
        except Exception:
            pass

    # ---- private --------------------------------------------------------

    def _position(self) -> None:
        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        x = sw - PANEL_W - 20
        y = min(32, sh - PANEL_H - 20)
        self._win.geometry(f"+{x}+{y}")


def main() -> None:
    root = tk.Tk()
    root.withdraw()
    panel = _DetailPanel(root)

    def _process_stdin() -> None:
        """Read one JSON command per line from stdin."""
        line = sys.stdin.readline()
        if not line:
            # stdin closed — parent exited.
            root.destroy()
            return
        try:
            cmd = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            root.after(16, _process_stdin)
            return

        action = cmd.get("action")

        if action == "show":
            panel.apply_cmd(cmd)
            panel.show()
        elif action == "update":
            panel.apply_cmd(cmd)
        elif action == "hide":
            panel.hide()
        elif action == "quit":
            root.destroy()
            return

        root.after(16, _process_stdin)

    def _tick() -> None:
        """Drive the local flash animation."""
        panel.tick_animation()
        root.after(16, _tick)

    root.after(16, _process_stdin)
    root.after(16, _tick)
    root.mainloop()


if __name__ == "__main__":
    main()
