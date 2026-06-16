# Vibecoding Signal Light

[中文](README.zh.md) | **English**

> A macOS menu bar status light for AI agents.

Vibecoding Signal Light turns the macOS menu bar into an ambient status display for Codex, Claude Code, and other local AI coding agents. When the agent is working, waiting, blocked, or asking for permission, the icon in your menu bar changes with it.

It is deliberately simple: glance at the menu bar, know whether you should keep flowing or look back at your agent.

## Why This Exists

AI coding agents are getting more autonomous, but their state is still trapped inside a terminal or chat window. That creates two awkward modes:

- You keep checking the agent too often and break your own focus.
- You forget it is waiting for permission, a result review, or a failure recovery.

This project gives the agent a visible presence in your menu bar:

- Green means you can relax.
- A flashing green cycle means the agent is busy.
- Yellow means the agent explicitly needs a look.
- Red means stop what you are doing and unblock it.

## Lamp Language

The language is intentionally small and persistent. The current light should always describe the current state.

| Light | Agent state | Human action |
| --- | --- | --- |
| Steady green | Idle | Nothing |
| Flashing green | Working (thinking, tools, tests) | Wait |
| Flashing yellow | Explicit attention needed | Look when convenient |
| Flashing red | Permission, blocked, or failed | Look now |
| Off | Manual clear | Nothing |

## Features

- macOS menu bar app with coloured icon and floating detail panel.
- Codex hook adapter.
- Claude Code hook adapter.
- Session-aware aggregation for multiple concurrent agent sessions.
- Red and yellow alerts are never hidden by another session starting work.
- Auto-start on login via launchd.

## Quick Start

```bash
uv sync                                          # Install Python dependencies
cd SignalLightApp && ./build.sh && cd ..          # Build macOS menu bar app
open SignalLightApp/.build/SignalLightApp.app     # Launch
```

The app lives in the menu bar. Right-click to show details or quit. It writes its own launchd plist for auto-start on first launch.

### Hook Installation

The easiest way to install or repair local hooks is the built-in wizard:

```bash
uv run signal-light install-hooks
uv run signal-light install-hooks --all -y
uv run signal-light install-hooks --agent codex --agent claude-code -y
```

The wizard detects supported local agents, validates the current hook files, creates timestamped backups, and installs only the Signal Light hook entries while keeping other hooks on the same events.

## Codex Integration

Codex hooks are invoked with the event name:

```bash
uv run signal-light codex-hook UserPromptSubmit
uv run signal-light codex-hook PreToolUse
uv run signal-light codex-hook PermissionRequest
uv run signal-light codex-hook Stop
```

Recommended hook mapping:

| Codex event | Signal behavior |
| --- | --- |
| `SessionStart` | Green idle |
| `UserPromptSubmit` | Green flash (working) |
| `PreToolUse` | Green flash (working) |
| `PostToolUse` | Green flash (working) |
| `PermissionRequest` | Yellow flashing |
| `Stop` | Clear normal working state |
| `SessionEnd` | Brief green completion blink, then current aggregate state |

See [docs/LAMP_LANGUAGE.md](docs/LAMP_LANGUAGE.md) for a complete `~/.codex/hooks.json` example.

## Claude Code Integration

Claude Code sends hook data as JSON on stdin, so no event argument is needed:

```bash
echo '{"event":"PreToolUse","session_id":"demo"}' | uv run signal-light claude-code-hook
echo '{"event":"PermissionRequest","session_id":"demo"}' | uv run signal-light claude-code-hook
echo '{"event":"Notification","session_id":"demo"}' | uv run signal-light claude-code-hook
```

Supported Claude Code events include:

| Claude Code event | Signal behavior |
| --- | --- |
| `SessionStart` | Green idle |
| `UserPromptSubmit` | Green flash (working) |
| `PreToolUse` | Green flash (working) |
| `PostToolUse` | Green flash (working) |
| `PostToolUseFailure` | Red flashing |
| `Notification` | Yellow flashing |
| `PermissionRequest` | Yellow flashing |
| `Stop` | Clear normal working state |
| `SessionEnd` | Brief green completion blink, then current aggregate state |

See [docs/LAMP_LANGUAGE.md](docs/LAMP_LANGUAGE.md) for a complete `~/.claude/settings.json` example.

## Multi-Session Behavior

The runtime stores the latest state for each agent session and shows the highest-priority aggregate on the menu bar:

```text
red flashing > yellow flashing > working cycle > steady green
```

That means one session waiting for permission will stay red even if another session starts working. A normal `Stop` only clears non-urgent working state; it does not erase an existing red alert.

When one tracked session ends while other sessions are still running, the runtime briefly flashes green as a completion cue, then restores the current aggregate state. If all sessions have ended, it settles on steady green. Red or yellow alerts are not interrupted by this completion cue.

## Project Status

This is a hackable companion for AI-assisted development. It is designed to be easy to fork and adapt:

- Map other agent systems into the same lamp language.
- Extend the lamp language with new signals.
- Customise the menu bar appearance or detail panel.

If your AI agent has become part of your workflow, give it a signal light.
