"""Session state management — read/write/aggregate sessions.json."""

from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

STATE_DIR = Path(os.environ.get("SIGNAL_LIGHT_STATE_DIR", "/private/tmp/signal-light"))
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


def apply_session_signal(session_key: str, signal_name: str) -> str:
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
    """Clear all tracked session states."""
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
