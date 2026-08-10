# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Vibecoding Signal Light provides ambient status display for AI coding agents (Codex, Claude Code). It is a **single Swift macOS app** that serves both as a menu bar GUI and as a hook CLI for agents.

The same binary operates in two modes:
- **GUI mode** (no arguments) — Menu bar app that reads session state and renders a colored icon + floating detail panel.
- **CLI mode** (`codex-hook`, `claude-code-hook`, `install-hooks`, `status`) — Runs as a hook command invoked by agents, writing session state to a shared JSON file.

Communication between agents and the GUI is via a shared JSON file (`/private/tmp/signal-light/sessions.json`).

## Commands

```bash
# Build
cd SignalLightApp && ./build.sh      # Build the macOS app

# Launch GUI
open SignalLightApp/.build/SignalLightApp.app  # Launch menu bar app

# CLI (run the binary inside the app bundle)
APP=SignalLightApp/.build/SignalLightApp.app/Contents/MacOS/SignalLightApp

$APP status                     # Show aggregated session state
$APP install-hooks --all --yes  # Install hooks for all agents
$APP clear-state                # Clear all session state

# Hook adapters (normally called by agents, not manually)
echo '{"session_id":"abc"}' | $APP codex-hook Stop
echo '{"session_id":"abc"}' | $APP claude-code-hook Stop
```

There is no linter or formatter configured. No CI pipeline.

## Architecture

### Source layout (`SignalLightApp/Sources/SignalLightApp/`)

- **`App/`**
  - `main.swift` — Entry point. Dispatches to CLI mode (hook/status/install-hooks) or launches NSApplication for GUI mode.
  - `AppDelegate` — PID file, poller init, menu bar setup.

- **`Core/`** (hook adapters and session management)
  - `SessionStore.swift` — Reads/writes `sessions.json` with `fcntl.flock` locking, TTL pruning, and priority-based aggregation.
  - `CodexHookAdapter.swift` — Maps Codex lifecycle events to signal names. Deep payload introspection for failure detection (error status, exit_status, tool_error).
  - `ClaudeCodeHookAdapter.swift` — Maps Claude Code hook events to signal names. Supports `stop_reason` handling and `SubagentStart`/`SubagentStop`/`Notification`.
  - `HookInstaller.swift` — Reads/writes `~/.codex/hooks.json` and `~/.claude/settings.json` to register hook commands. Installs the bundled omp/pi-coding-agent hook template into `~/.omp/agent/extensions/` and `~/.pi/agent/extensions/`. Handles merge with existing hooks and creates backups.

- **`Models/`**
  - `SessionState.swift` — Codable JSON model matching the `sessions.json` format.
  - `SignalDefinition.swift` — 12 signal definitions with color mapping, priority classification, and `aggregateSignal()` computation.

- **`Services/`**
  - `SessionPoller.swift` — 500ms Combine-based polling of `sessions.json`.
  - `LaunchdManager.swift` — macOS launchd plist for auto-start on login.

- **`Views/`**
  - `StatusBarController.swift` — NSStatusItem with flash animation and right-click menu (Show Details, Install Hooks, Quit).
  - `DetailPanelWindow.swift` — Floating NSPanel with traffic light animation.
  - `TrafficLightView.swift` — Custom NSView drawing three colored circles (red/yellow/green).

### Key patterns

- **Single binary, dual mode**: `main.swift` checks `CommandLine.arguments` — if a subcommand is present, it runs the CLI handler; otherwise it launches NSApplication.
- **JSON file as contract**: The CLI writes `sessions.json`; the GUI reads it. No IPC needed.
- **Multi-session aggregation**: `SessionStore.aggregateSessions()` picks the highest-priority signal so urgent alerts (red/yellow) are never masked by normal activity.
- **File-lock concurrency**: `SessionStore.withLock()` uses `fcntl.flock(LOCK_EX)` for exclusive access across concurrent hook processes.

### Entry points (subcommands of the single binary)

| Subcommand | Handler |
|---|---|
| `codex-hook` | `CodexHookAdapter.run()` |
| `claude-code-hook` | `ClaudeCodeHookAdapter.run()` |
| `install-hooks` | `HookInstaller.installAgent()` |
| `status` | `SessionStore.readSessionSnapshot()` |
| `clear-state` | `SessionStore.clearSessionState()` |

### Environment variables

| Variable | Purpose | Default |
|---|---|---|
| `SIGNAL_LIGHT_STATE_DIR` | Session state directory | `/private/tmp/signal-light` |
| `SIGNAL_LIGHT_SESSION_TTL_SECONDS` | Session expiry | `86400` |
| `SIGNAL_LIGHT_GUI_POLL_MS` | GUI polling interval | `500` |
