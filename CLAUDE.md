# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Vibecoding Signal Light provides ambient status display for AI coding agents (Codex, Claude Code). It supports two backends: a **physical traffic light** (red/yellow/green LEDs via MCP2221A USB GPIO) and a **macOS menu bar app** (colored icon + floating panel via `rumps` + `tkinter`). The two backends share the same lamp language, session state, and hook adapters.

## Commands

```bash
# Install (choose extras as needed)
uv sync                              # Core only — no hardware, no GUI
uv sync --extra gui                  # With macOS menu bar support
uv sync --extra hardware             # With MCP2221A GPIO support
uv sync --extra all                  # Everything

# Run tests
uv run pytest -v
uv run pytest tests/test_gui.py::TestComputeCurrentFrame -v

# CLI
uv run python -m signal_light list
uv run python -m signal_light play working --dry-run
uv run python -m signal_light gui status
uv run python -m signal_light gui start   # Start menu bar daemon
uv run python -m signal_light gui stop    # Stop menu bar daemon
```

**Important**: Always `uv sync --extra <desired>` before `uv run`. The `uv run` command re-syncs from the lockfile without extras, which removes optional packages like `rumps`.

There is no linter or formatter configured. No CI pipeline.

## Architecture

### Module responsibilities

- **`agent_signals.py`** — Core "lamp language": `Frame`, `AgentSignal` dataclasses, `LightWriter`/`BrightnessWriter` protocols, and the `SIGNALS` dictionary (12 named signals). The `_soft_pulse()` function generates breathing-effect brightness ramps.
- **`runtime.py`** — The most complex module. Manages multi-session state (JSON at `/tmp/signal-light/sessions.json` with `fcntl.flock`), signal priority aggregation (`blocked > permission > attention > working > idle`), background worker process lifecycle (PID files, owner tokens, orphan cleanup), idle sleep timeout, session-end notice cues, and GUI daemon start/stop management.
- **`gui/daemon.py`** — macOS menu bar daemon (`rumps.App`). Polls `sessions.json` every 500ms, updates a colored circle icon based on the aggregate signal, and manages a floating tkinter detail panel. Runs rumps on the main thread, tkinter in a daemon thread. Contains the pure function `compute_current_frame()` for animation frame calculation.
- **`gui/icon_generator.py`** — Generates RGBA PNG circle icons using raw `struct` + `zlib` (no PIL). Caches icons by color and brightness in `STATE_DIR/icons/`.
- **`gui/launchd.py`** — Generates and manages a macOS launchd plist for auto-starting the GUI daemon.
- **`hardware.py`** — `SignalLight` wraps `EasyMCP2221.Device()` with lazy init, active-low inversion, and env-var-configurable pin mapping. Implements `LightWriter`. `EasyMCP2221` is an optional dependency.
- **`codex_hook.py`** — Maps Codex lifecycle events (from CLI args + JSON payload) to signal names. Deep payload introspection for failure detection.
- **`claude_code_hook.py`** — Same role for Claude Code hooks (reads JSON from stdin). Supports additional events like `SubagentStart`/`SubagentStop`.
- **`hook_installer.py`** — Interactive wizard that merges hook entries into `~/.codex/hooks.json` and `~/.claude/settings.json`. Optionally installs the GUI daemon via launchd.
- **`cli.py`** — argparse CLI with subcommands: `play`, `list`, `status`, `install-hooks`, `codex-hook`, `claude-code-hook`, `worker`, `test`, `gui`, `gui-daemon`.

### Key patterns

- **GUI daemon as pure reader**: The menu bar daemon polls `sessions.json` and never writes to it. Hook processes write session state; the daemon reads it. No IPC needed — the JSON file is the shared contract.
- **Background workers for animated signals**: Hook processes must return fast (5-10s timeout). Signals with `repeat=True` spawn background `python -m signal_light worker <signal>` child processes, tracked via PID files with SHA-256 owner tokens.
- **Protocol-based hardware abstraction**: `LightWriter` / `BrightnessWriter` protocols let the signal logic work with real hardware (`SignalLight`), console output (`DryRunLight`), or test doubles (`RecordingLight`).
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
| `SIGNAL_LIGHT_GREEN_PIN` / `YELLOW_PIN` / `RED_PIN` | GPIO pin names | `gp0` / `gp1` / `gp2` |
| `SIGNAL_LIGHT_ACTIVE_LOW` | LED polarity (`0` = active-high) | active-low |
| `SIGNAL_LIGHT_STATE_DIR` | Session state directory | `/private/tmp/signal-light` |
| `SIGNAL_LIGHT_IDLE_SLEEP_SECONDS` | Idle-to-off timeout | `600` |
| `SIGNAL_LIGHT_DRY_RUN` | Skip hardware in hooks | unset |
| `SIGNAL_LIGHT_GUI_POLL_MS` | GUI polling interval | `500` |

## Testing

Tests are in `tests/test_agent_signals.py` and `tests/test_gui.py`. They use `monkeypatch` extensively to mock hardware, file I/O, process management, and signal application. The `RecordingLight` test double records `write()`/`write_brightness()` calls for assertion. GUI tests cover animation frame computation (pure function), icon generation (PNG validity), launchd plist generation, CLI gui subcommands, and runtime GUI daemon management — all without requiring a display.
