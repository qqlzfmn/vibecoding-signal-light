"""Command line interface for AI agent signal lights."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from signal_light.session import read_session_snapshot


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="signal-light",
        description="AI agent signal light — manages hooks and session state.",
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("status", help="show aggregated session signal state")

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

    hook = subparsers.add_parser("codex-hook", help="run Codex hook adapter")
    hook.add_argument("event", nargs="?", help="event name")
    hook.add_argument("--event", dest="event_option", help="event name")

    cc_hook = subparsers.add_parser("claude-code-hook", help="run Claude Code hook adapter")
    cc_hook.add_argument("event", nargs="?", help="event name")
    cc_hook.add_argument("--event", dest="event_option", help="event name")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "status":
        print(json.dumps(read_session_snapshot(), ensure_ascii=False, indent=2))
        return 0

    if args.command == "install-hooks":
        from signal_light.hooks.installer import run_install_wizard

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
        from signal_light.hooks.codex import main as codex_hook_main
        return codex_hook_main()

    if args.command == "claude-code-hook":
        from signal_light.hooks.claude_code import main as cc_hook_main
        return cc_hook_main()

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
