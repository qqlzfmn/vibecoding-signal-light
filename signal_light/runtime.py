"""Runtime process management for persistent signal-light states."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from signal_light.agent_signals import SIGNALS


class SignalLightError(RuntimeError):
    """Raised when signal-light operations fail."""


STATE_DIR = Path(os.environ.get("SIGNAL_LIGHT_STATE_DIR", "/private/tmp/signal-light"))
PROJECT_ROOT = Path(__file__).resolve().parents[1]
GUI_PID_FILE = STATE_DIR / "gui-daemon.pid"
SESSION_FILE = STATE_DIR / "sessions.json"
LOCK_FILE = STATE_DIR / "state.lock"
SESSION_TTL_SECONDS = int(os.environ.get("SIGNAL_LIGHT_SESSION_TTL_SECONDS", "86400"))

RED_SIGNALS = {"blocked"}
YELLOW_SIGNALS = {"permission", "attention", "done"}
WORKING_SIGNALS = {"thinking", "working", "tool_done"}
SESSION_END_SIGNALS = {"session_end"}
SESSION_CLEAR_SIGNALS = {"off"}
TURN_END_SIGNALS = {"turn_end"}
TURN_END_KEEP_SIGNALS = {"permission", "blocked"}


def apply_session_signal(session_key: str, signal_name: str, *, speed: float = 1.0) -> str:
    """Update one session state and return the aggregate signal name."""
    with _state_lock():
        state = _read_session_state()
        sessions = state.setdefault("sessions", {})
        now = time.time()
        _prune_sessions(sessions, now)

        if signal_name in SESSION_END_SIGNALS:
            sessions.pop(session_key, None)
        elif signal_name in SESSION_CLEAR_SIGNALS:
            sessions.pop(session_key, None)
        elif signal_name in TURN_END_SIGNALS:
            current = sessions.get(session_key)
            current_signal = current.get("signal") if isinstance(current, dict) else None
            if current_signal not in TURN_END_KEEP_SIGNALS:
                sessions.pop(session_key, None)
        else:
            sessions[session_key] = {
                "signal": signal_name,
                "updated_at": now,
            }

        aggregate = aggregate_sessions(sessions)
        _write_session_state(state)
        return aggregate


def clear_session_state() -> None:
    """Clear all tracked Codex session states."""
    with _state_lock():
        _write_session_state({"sessions": {}})


def aggregate_sessions(sessions: dict[str, object]) -> str:
    signals = []
    for value in sessions.values():
        if isinstance(value, dict):
            signal_name = value.get("signal")
            if isinstance(signal_name, str):
                signals.append(signal_name)

    if any(signal_name in RED_SIGNALS for signal_name in signals):
        return "blocked"
    if any(signal_name == "permission" for signal_name in signals):
        return "permission"
    if any(signal_name in YELLOW_SIGNALS for signal_name in signals):
        return "attention"
    if any(signal_name in WORKING_SIGNALS for signal_name in signals):
        return "working"
    return "idle"


def read_session_snapshot() -> dict[str, object]:
    with _state_lock():
        return _read_session_snapshot_unlocked()


def _read_session_snapshot_unlocked() -> dict[str, object]:
    state = _read_session_state()
    sessions = state.get("sessions", {})
    if not isinstance(sessions, dict):
        sessions = {}
    now = time.time()
    _prune_sessions(sessions, now)
    aggregate = aggregate_sessions(sessions)
    return {
        "aggregate": aggregate,
        "sessions": sessions,
    }


@contextmanager
def _state_lock() -> Iterator[None]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with LOCK_FILE.open("a+") as lock_file:
        try:
            import fcntl

            fcntl.flock(lock_file, fcntl.LOCK_EX)
            yield
        finally:
            try:
                fcntl.flock(lock_file, fcntl.LOCK_UN)
            except Exception:
                pass


def _read_session_state() -> dict[str, object]:
    try:
        state = json.loads(SESSION_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {"sessions": {}}

    if not isinstance(state, dict):
        return {"sessions": {}}
    if not isinstance(state.get("sessions"), dict):
        state["sessions"] = {}
    return state


def _write_session_state(state: dict[str, object]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    SESSION_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")


def _prune_sessions(sessions: dict[str, object], now: float) -> None:
    expired = []
    for session_key, value in sessions.items():
        if not isinstance(value, dict):
            expired.append(session_key)
            continue
        updated_at = value.get("updated_at")
        if not isinstance(updated_at, (int, float)) or now - updated_at > SESSION_TTL_SECONDS:
            expired.append(session_key)

    for session_key in expired:
        sessions.pop(session_key, None)


# ---------------------------------------------------------------------------
# GUI daemon management
# ---------------------------------------------------------------------------

def start_gui_daemon() -> int | None:
    """Spawn the GUI daemon in the background.  Returns the PID or *None* if already running."""
    if is_gui_daemon_running():
        return None
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    command = [sys.executable, "-m", "signal_light", "gui-daemon"]
    env = os.environ.copy()
    env["UV_PYTHON"] = f"{sys.version_info.major}.{sys.version_info.minor}"

    log = (STATE_DIR / "gui-daemon.log").open("ab")
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            cwd=PROJECT_ROOT,
            env=env,
            start_new_session=True,
        )
    finally:
        log.close()
    GUI_PID_FILE.write_text(str(process.pid))
    return process.pid


def stop_gui_daemon() -> bool:
    """Stop the GUI daemon and all its child processes."""
    pid = _read_gui_daemon_pid()
    was_running = pid is not None and _is_running(pid)
    if was_running:
        _terminate_process_group(pid)
    _clear_gui_daemon_pid()
    return was_running


def is_gui_daemon_running() -> bool:
    pid = _read_gui_daemon_pid()
    return pid is not None and _is_running(pid)


def _read_gui_daemon_pid() -> int | None:
    try:
        return int(GUI_PID_FILE.read_text().strip())
    except (FileNotFoundError, ValueError):
        return None


def _clear_gui_daemon_pid() -> None:
    try:
        GUI_PID_FILE.unlink()
    except FileNotFoundError:
        pass


def _terminate_process_group(pid: int) -> None:
    """Send SIGTERM to the process group rooted at *pid*, then SIGKILL if needed."""
    if not _is_running(pid):
        return

    try:
        pgid = os.getpgid(pid)
    except (ProcessLookupError, OSError):
        pgid = pid

    try:
        os.killpg(pgid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        _terminate(pid)
        return

    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        if not _is_running(pid):
            return
        time.sleep(0.05)

    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        pass


def _terminate(pid: int) -> None:
    if not _is_running(pid):
        return

    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    except PermissionError as exc:
        raise SignalLightError(f"Cannot stop process {pid}: {exc}") from exc

    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        if not _is_running(pid):
            return
        time.sleep(0.05)

    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    except PermissionError as exc:
        raise SignalLightError(f"Cannot stop process {pid}: {exc}") from exc


def _is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
