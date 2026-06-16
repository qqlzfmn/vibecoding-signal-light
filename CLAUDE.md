# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Vibecoding Signal Light provides ambient status display for AI coding agents (Codex, Claude Code). It consists of two parts:

- **Python package** — Hook adapters that map agent lifecycle events to a shared lamp language and manage session state in a JSON file.
- **Swift macOS app** — Native menu bar app (`SignalLightApp/`) that reads session state and renders a colored icon + floating detail panel.

The two communicate via a shared JSON file (`/tmp/signal-light/sessions.json`). Python hooks write; the Swift app reads.

## Commands

```bash
# Python
uv sync                              # Install Python dependencies
uv run pytest -v                     # Run tests

# Swift app
cd SignalLightApp && ./build.sh      # Build the macOS app
open SignalLightApp/.build/SignalLightApp.app  # Launch

# CLI
uv run signal-light status                     # Show aggregated session state
uv run signal-light install-hooks              # Install hooks
open SignalLightApp/.build/SignalLightApp.app  # Launch menu bar app
```

There is no linter or formatter configured. No CI pipeline.

## Architecture

### Python package (`signal_light/`)

- **`signals.py`** — Signal definitions: `Signal` dataclass (name + summary) and the `SIGNALS` dictionary (12 named signals). Pure data, no logic.
- **`session.py`** — Session state management: `apply_session_signal()`, `aggregate_sessions()`, `read_session_snapshot()`, `clear_session_state()`. Uses `fcntl.flock` for concurrent access.
- **`cli.py`** — argparse CLI with subcommands: `status`, `install-hooks`, `codex-hook`, `claude-code-hook`.
- **`hooks/`** — Agent hook adapters:
  - `codex.py` — Maps Codex lifecycle events to signal names. Deep payload introspection for failure detection.
  - `claude_code.py` — Same for Claude Code hooks (reads JSON from stdin). Supports `SubagentStart`/`SubagentStop`/`Notification`.
  - `installer.py` — Interactive wizard that merges hook entries into `~/.codex/hooks.json` and `~/.claude/settings.json`.

### Swift app (`SignalLightApp/`)

- **`App/`** — `main.swift` entry point, `AppDelegate` (PID file, poller init).
- **`Models/`** — `SessionState.swift` (Codable JSON model), `SignalDefinition.swift` (12 signals, color mapping, aggregate computation).
- **`Services/`** — `SessionPoller.swift` (500ms Combine-based polling), `LaunchdManager.swift` (launchd plist).
- **`Views/`** — `StatusBarController.swift` (NSStatusItem + flash animation), `DetailPanelWindow.swift` (floating NSPanel), `TrafficLightView.swift` (custom NSView circles).

### Key patterns

- **JSON file as contract**: Hook processes write `sessions.json`; the Swift app reads it. No IPC needed.
- **Multi-session aggregation**: `aggregate_sessions()` picks the highest-priority signal so urgent alerts (red/yellow) are never masked by normal activity.
- **File-lock concurrency**: `_state_lock()` uses `fcntl.flock` for exclusive access across concurrent hook processes.

### Entry points (defined in pyproject.toml)

| Command | Target |
|---|---|
| `signal-light` | `signal_light.cli:main` |
| `codex-signal-hook` | `signal_light.hooks.codex:main` |
| `claude-code-signal-hook` | `signal_light.hooks.claude_code:main` |

### Environment variables

| Variable | Purpose | Default |
|---|---|---|
| `SIGNAL_LIGHT_STATE_DIR` | Session state directory | `/private/tmp/signal-light` |
| `SIGNAL_LIGHT_SESSION_TTL_SECONDS` | Session expiry | `86400` |
| `SIGNAL_LIGHT_GUI_POLL_MS` | GUI polling interval | `500` |

## Testing

Tests are in `tests/test_agent_signals.py`. They use `monkeypatch` extensively to mock file I/O, process management, and signal application.
