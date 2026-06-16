# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Vibecoding Signal Light provides ambient status display for AI coding agents (Codex, Claude Code) via a **macOS menu bar app** (colored icon + floating panel via `rumps` + `tkinter`). Hook adapters map agent lifecycle events to a shared lamp language; the GUI daemon polls session state and renders it visually.

## Commands

```bash
# Install
uv sync                              # Core only
uv sync --extra gui                  # With macOS menu bar support

# Run tests
uv run pytest -v
uv run pytest tests/test_gui.py::TestComputeCurrentFrame -v

# CLI
uv run python -m signal_light list
uv run python -m signal_light gui status
uv run python -m signal_light gui start   # Start menu bar daemon
uv run python -m signal_light gui stop    # Stop menu bar daemon
```

**Important**: Always `uv sync --extra gui` before `uv run` if you need the GUI. The `uv run` command re-syncs from the lockfile without extras, which removes optional packages like `rumps`.

There is no linter or formatter configured. No CI pipeline.

## Architecture

### Module responsibilities

- **`agent_signals.py`** — Core "lamp language": `Frame`, `AgentSignal` dataclasses, `LightWriter`/`BrightnessWriter` protocols, and the `SIGNALS` dictionary (12 named signals). The `_soft_pulse()` function generates breathing-effect brightness ramps.
- **`runtime.py`** — Manages multi-session state (JSON at `/tmp/signal-light/sessions.json` with `fcntl.flock`), signal priority aggregation (`blocked > permission > attention > working > idle`), and GUI daemon start/stop management.
- **`gui/daemon.py`** — macOS menu bar daemon (`rumps.App`). Polls `sessions.json` every 500ms, updates a colored circle icon based on the aggregate signal, and manages a floating tkinter detail panel. Contains the pure function `compute_current_frame()` for animation frame calculation.
- **`gui/icon_generator.py`** — Generates RGBA PNG circle icons using raw `struct` + `zlib` (no PIL). Caches icons by color and brightness in `STATE_DIR/icons/`.
- **`gui/launchd.py`** — Generates and manages a macOS launchd plist for auto-starting the GUI daemon.
- **`codex_hook.py`** — Maps Codex lifecycle events (from CLI args + JSON payload) to signal names. Deep payload introspection for failure detection.
- **`claude_code_hook.py`** — Same role for Claude Code hooks (reads JSON from stdin). Supports additional events like `SubagentStart`/`SubagentStop`.
- **`hook_installer.py`** — Interactive wizard that merges hook entries into `~/.codex/hooks.json` and `~/.claude/settings.json`. Optionally installs the GUI daemon via launchd.
- **`cli.py`** — argparse CLI with subcommands: `play`, `list`, `status`, `install-hooks`, `codex-hook`, `claude-code-hook`, `gui`, `gui-daemon`.

### Key patterns

- **GUI daemon as pure reader**: The menu bar daemon polls `sessions.json` and never writes to it. Hook processes write session state; the daemon reads it. No IPC needed — the JSON file is the shared contract.
- **Multi-session aggregation**: Multiple concurrent agent sessions share state via a locked JSON file. `aggregate_sessions()` picks the highest-priority signal so urgent alerts (red/yellow) are never masked by normal activity.
- **File-lock concurrency**: `_state_lock()` uses `fcntl.flock` for exclusive access to the shared session state file across concurrent hook processes.

### Entry points (defined in pyproject.toml)

| Command | Target |
|---|---|
| `signal-light` | `signal_light.cli:main` |
| `codex-signal-hook` | `signal_light.codex_hook:main` |
| `claude-code-signal-hook` | `signal_light.claude_code_hook:main` |

### Environment variables

| Variable | Purpose | Default |
|---|---|---|
| `SIGNAL_LIGHT_STATE_DIR` | Session state directory | `/private/tmp/signal-light` |
| `SIGNAL_LIGHT_SESSION_TTL_SECONDS` | Session expiry | `86400` |
| `SIGNAL_LIGHT_GUI_POLL_MS` | GUI polling interval | `500` |

## Testing

Tests are in `tests/test_agent_signals.py` and `tests/test_gui.py`. They use `monkeypatch` extensively to mock file I/O, process management, and signal application. The `RecordingLight` test double records `write()`/`write_brightness()` calls for assertion. GUI tests cover animation frame computation (pure function), icon generation (PNG validity), launchd plist generation, CLI gui subcommands, and runtime GUI daemon management — all without requiring a display.
