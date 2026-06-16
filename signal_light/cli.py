"""Command line interface for AI agent signal lights."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Sequence

from signal_light.agent_signals import SIGNALS
from signal_light.runtime import (
    apply_session_signal,
    clear_session_state,
    read_session_snapshot,
)


HOOK_CONTROL_SIGNALS = {"turn_end"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="signal-light",
        description="Play AI agent status patterns on a red/yellow/green traffic signal model.",
    )
    subparsers = parser.add_subparsers(dest="command")

    play = subparsers.add_parser("play", help="play one lamp-language signal")
    play.add_argument("signal", choices=sorted(SIGNALS), help="signal name")
    play.add_argument("--speed", type=float, default=1.0, help="delay multiplier; lower is faster")
    play.add_argument("--quiet", action="store_true", help="suppress non-error output")

    subparsers.add_parser("list", help="list available lamp-language signals")
    subparsers.add_parser("status", help="show aggregated Codex session signal state")

    install_hooks = subparsers.add_parser("install-hooks", help="install or repair local agent hooks")
    install_hooks.add_argument(
        "--agent",
        action="append",
        dest="agents",
        help="agent to install: codex or claude-code; can be passed more than once",
    )
    install_hooks.add_argument("--all", action="store_true", help="install or repair all supported agents")
    install_hooks.add_argument("-y", "--yes", action="store_true", help="accept the suggested selection")
    install_hooks.add_argument("--dry-run", action="store_true", help="show planned changes without writing files")
    install_hooks.add_argument("--no-gui", action="store_true", help="skip macOS menu bar app installation")

    hook = subparsers.add_parser("codex-hook", help="read a Codex hook event and play the matching signal")
    hook.add_argument("event", nargs="?", help="Codex hook event name, for example Stop or PermissionRequest")
    hook.add_argument("--event", dest="event_option", help="Codex hook event name")

    cc_hook = subparsers.add_parser("claude-code-hook", help="read a Claude Code hook event and play the matching signal")
    cc_hook.add_argument("event", nargs="?", help="Claude Code hook event name, for example Stop or PreToolUse")
    cc_hook.add_argument("--event", dest="event_option", help="Claude Code hook event name")

    gui = subparsers.add_parser("gui", help="manage the macOS menu bar status app")
    gui.add_argument(
        "action",
        nargs="?",
        default="start",
        choices=["start", "stop", "status", "install", "uninstall"],
        help="action to perform (default: start)",
    )

    subparsers.add_parser("gui-daemon", help=argparse.SUPPRESS)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "list":
        return list_signals()
    if args.command == "play":
        return play_signal(args.signal, speed=args.speed, quiet=args.quiet)
    if args.command == "install-hooks":
        from signal_light.hook_installer import run_install_wizard

        try:
            return run_install_wizard(
                selected_agents=args.agents,
                all_agents=args.all,
                yes=args.yes,
                dry_run=args.dry_run,
                no_gui=args.no_gui,
            )
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
    if args.command == "codex-hook":
        event = args.event_option or args.event
        from signal_light.codex_hook import choose_signal, read_codex_hook_input, session_key

        hook_argv = ["signal-light", "--event", event] if event else ["signal-light"]
        hook_input = read_codex_hook_input(hook_argv, sys.stdin.read(), os.environ)
        signal = choose_signal(hook_input)
        key = session_key(hook_input, os.environ)
        return play_hook_signal(signal, session_key=key, quiet=True)
    if args.command == "claude-code-hook":
        event = args.event_option or args.event
        from signal_light.claude_code_hook import choose_signal as cc_choose_signal
        from signal_light.claude_code_hook import read_hook_input, session_key as cc_session_key

        hook_argv = ["signal-light", "--event", event] if event else ["signal-light"]
        hook_input = read_hook_input(hook_argv, sys.stdin.read())
        signal = cc_choose_signal(hook_input)
        key = cc_session_key(hook_input, os.environ)
        return play_hook_signal(signal, session_key=key, quiet=True)
    if args.command == "status":
        print(json.dumps(read_session_snapshot(), ensure_ascii=False, indent=2))
        return 0
    if args.command == "gui":
        return run_gui_action(args.action)
    if args.command == "gui-daemon":
        from signal_light.gui.daemon import run_gui_daemon
        return run_gui_daemon()

    parser.print_help()
    return 2


def list_signals() -> int:
    print("Signal language:")
    for signal in SIGNALS.values():
        print(f"- {signal.name}: {signal.summary} {signal.attention}")
    return 0


def play_signal(signal_name: str, *, speed: float = 1.0, quiet: bool = False) -> int:
    signal = SIGNALS.get(signal_name)
    if signal is None:
        if not quiet:
            print(f"Unknown signal: {signal_name}", file=sys.stderr)
        return 2

    if not quiet:
        print(f"Playing {signal.name}: {signal.summary}")

    if signal_name in {"idle", "off"}:
        clear_session_state()

    return 0


def play_hook_signal(
    signal_name: str,
    *,
    session_key: str,
    speed: float = 1.0,
    quiet: bool = False,
) -> int:
    signal = SIGNALS.get(signal_name)
    if signal is None and signal_name not in HOOK_CONTROL_SIGNALS:
        if not quiet:
            print(f"Unknown signal: {signal_name}", file=sys.stderr)
        return 2

    try:
        aggregate = apply_session_signal(session_key, signal_name, speed=speed)
    except Exception as exc:
        if not quiet:
            print(str(exc), file=sys.stderr)
        return 1

    if not quiet:
        print(f"Session {session_key}: {signal_name}; aggregate={aggregate}")
    return 0


def run_gui_action(action: str) -> int:
    from signal_light.runtime import (
        is_gui_daemon_running,
        read_session_snapshot,
        start_gui_daemon,
        stop_gui_daemon,
    )

    if action == "start":
        try:
            import rumps  # noqa: F401
        except ImportError:
            print(
                "Error: 'rumps' is not installed. Install the GUI extras first:\n"
                "  uv sync --extra gui",
                file=sys.stderr,
            )
            return 1
        pid = start_gui_daemon()
        if pid is None:
            print("GUI daemon is already running.")
        else:
            print(f"GUI daemon started (PID {pid}).")
        return 0

    if action == "stop":
        if stop_gui_daemon():
            print("GUI daemon stopped.")
        else:
            print("GUI daemon is not running.")
        return 0

    if action == "status":
        running = is_gui_daemon_running()
        snapshot = read_session_snapshot()
        print(f"Daemon running: {running}")
        print(f"Aggregate signal: {snapshot.get('aggregate', 'unknown')}")
        return 0

    if action == "install":
        from signal_light.gui.launchd import install_plist
        from signal_light.runtime import PROJECT_ROOT, STATE_DIR
        path = install_plist(PROJECT_ROOT, STATE_DIR)
        print(f"launchd plist installed: {path}")
        return 0

    if action == "uninstall":
        from signal_light.gui.launchd import uninstall_plist
        uninstall_plist()
        print("launchd plist removed.")
        return 0

    print(f"Unknown gui action: {action}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
