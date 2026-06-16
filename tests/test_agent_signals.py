import io
import json
import os
from pathlib import Path

import pytest

from signal_light.agent_signals import SIGNALS
from signal_light import cli
from signal_light.codex_hook import CodexHookInput, choose_signal, session_key
from signal_light import hook_installer
from signal_light import runtime
from signal_light.runtime import aggregate_sessions, apply_session_signal


class RecordingLight:
    def __init__(self) -> None:
        self.states: list[tuple[bool, bool, bool]] = []
        self.brightness_states: list[tuple[float, float, float]] = []

    def write(self, *, green: bool = False, yellow: bool = False, red: bool = False) -> None:
        self.states.append((green, yellow, red))

    def write_brightness(self, *, green: float = 0.0, yellow: float = 0.0, red: float = 0.0) -> None:
        self.brightness_states.append((green, yellow, red))

    def off(self) -> None:
        self.write()


# ---------------------------------------------------------------------------
# Signal playback tests (AgentSignal.play — pure lamp language, no hardware)
# ---------------------------------------------------------------------------

def test_idle_signal_leaves_green_on() -> None:
    light = RecordingLight()

    SIGNALS["idle"].play(light, speed=0.05)

    assert SIGNALS["idle"].repeat is False
    assert light.states[-1] == (True, False, False)


def test_working_signal_flashes_green() -> None:
    light = RecordingLight()

    SIGNALS["working"].play(light, speed=0.05, cycles=1)

    assert SIGNALS["working"].repeat is True
    assert light.states[:2] == [(True, False, False), (False, False, False)]


def test_attention_signal_flashes_yellow() -> None:
    light = RecordingLight()

    SIGNALS["attention"].play(light, speed=0.05, cycles=1)

    assert SIGNALS["attention"].repeat is True
    assert light.states[:2] == [(False, True, False), (False, False, False)]


def test_thinking_signal_flashes_green() -> None:
    light = RecordingLight()

    SIGNALS["thinking"].play(light, speed=0.05, cycles=1)

    assert SIGNALS["thinking"].frames == SIGNALS["working"].frames
    assert light.states[:2] == [(True, False, False), (False, False, False)]


def test_permission_signal_flashes_yellow() -> None:
    light = RecordingLight()

    SIGNALS["permission"].play(light, speed=0.05, cycles=1)

    assert SIGNALS["permission"].repeat is True
    assert light.states[:2] == [(False, True, False), (False, False, False)]


def test_session_end_returns_to_idle_green() -> None:
    light = RecordingLight()

    SIGNALS["session_end"].play(light, speed=0.05)

    assert light.states[-1] == (True, False, False)


def test_session_done_signal_briefly_flashes_green() -> None:
    light = RecordingLight()

    SIGNALS["session_done"].play(light, speed=0.05, cycles=1)

    assert SIGNALS["session_done"].repeat is False
    assert light.states[:2] == [(True, False, False), (False, False, False)]
    assert light.states[-1] == (False, False, False)


# ---------------------------------------------------------------------------
# Codex hook signal mapping
# ---------------------------------------------------------------------------

def test_codex_stop_maps_to_turn_end() -> None:
    signal = choose_signal(CodexHookInput(event_name="Stop", payload={}))

    assert signal == "turn_end"


def test_failed_payload_maps_to_blocked() -> None:
    signal = choose_signal(
        CodexHookInput(
            event_name="PostToolUse",
            payload={"status": "failed"},
        )
    )

    assert signal == "blocked"


def test_structured_error_payload_maps_to_blocked() -> None:
    signal = choose_signal(
        CodexHookInput(
            event_name="PostToolUse",
            payload={"error": {"message": "command failed"}},
        )
    )

    assert signal == "blocked"


def test_prompt_text_containing_error_does_not_map_to_blocked() -> None:
    signal = choose_signal(
        CodexHookInput(
            event_name="UserPromptSubmit",
            payload={"prompt": "please fix this error"},
        )
    )

    assert signal == "thinking"


def test_success_status_does_not_become_unknown_signal() -> None:
    signal = choose_signal(
        CodexHookInput(
            event_name="PostToolUse",
            payload={"status": "success"},
        )
    )

    assert signal == "tool_done"


# ---------------------------------------------------------------------------
# Session aggregation
# ---------------------------------------------------------------------------

def test_aggregate_keeps_attention_over_other_working_session() -> None:
    aggregate = aggregate_sessions(
        {
            "a": {"signal": "attention", "updated_at": 1},
            "b": {"signal": "working", "updated_at": 1},
        }
    )

    assert aggregate == "attention"


def test_aggregate_keeps_permission_over_attention_and_working() -> None:
    aggregate = aggregate_sessions(
        {
            "a": {"signal": "attention", "updated_at": 1},
            "b": {"signal": "working", "updated_at": 1},
            "c": {"signal": "permission", "updated_at": 1},
        }
    )

    assert aggregate == "permission"


def test_aggregate_returns_working_when_any_session_is_working() -> None:
    aggregate = aggregate_sessions(
        {
            "a": {"signal": "idle", "updated_at": 1},
            "b": {"signal": "tool_done", "updated_at": 1},
        }
    )

    assert aggregate == "working"


def test_aggregate_returns_idle_for_empty_sessions() -> None:
    assert aggregate_sessions({}) == "idle"


# ---------------------------------------------------------------------------
# Session key extraction
# ---------------------------------------------------------------------------

def test_session_key_prefers_payload_session_id() -> None:
    key = session_key(
        CodexHookInput(event_name="Stop", payload={"session_id": "session-a", "cwd": "/tmp/x"}),
        {},
    )

    assert key == "session-a"


def test_session_key_falls_back_to_cwd() -> None:
    key = session_key(
        CodexHookInput(event_name="Stop", payload={"cwd": "/tmp/project"}),
        {},
    )

    assert key == "cwd:/tmp/project"


def test_session_key_ignores_turn_id_and_uses_cwd() -> None:
    key = session_key(
        CodexHookInput(event_name="Stop", payload={"turn_id": "turn-a", "cwd": "/tmp/project"}),
        {"CODEX_TURN_ID": "turn-env"},
    )

    assert key == "cwd:/tmp/project"


# ---------------------------------------------------------------------------
# CLI codex-hook
# ---------------------------------------------------------------------------

def test_cli_codex_hook_uses_session_aware_path(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr("sys.stdin", io.StringIO('{"session_id":"session-a","event":"Stop"}'))
    monkeypatch.setattr(
        cli,
        "play_hook_signal",
        lambda signal_name, *, session_key, quiet=False: calls.append(
            (signal_name, session_key)
        )
        or 0,
    )

    assert cli.main(["codex-hook"]) == 0
    assert calls == [("turn_end", "session-a")]


def test_cli_codex_hook_without_event_uses_stdin_event(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr("sys.stdin", io.StringIO('{"session_id":"session-a","event":"PermissionRequest"}'))
    monkeypatch.setattr(
        cli,
        "play_hook_signal",
        lambda signal_name, *, session_key, quiet=False: calls.append(
            (signal_name, session_key)
        )
        or 0,
    )

    assert cli.main(["codex-hook"]) == 0
    assert calls == [("permission", "session-a")]


# ---------------------------------------------------------------------------
# Multi-session behavior
# ---------------------------------------------------------------------------

def test_apply_session_signal_preserves_attention_over_other_work(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(runtime, "STATE_DIR", tmp_path)
    monkeypatch.setattr(runtime, "SESSION_FILE", tmp_path / "sessions.json")
    monkeypatch.setattr(runtime, "LOCK_FILE", tmp_path / "state.lock")

    assert apply_session_signal("session-a", "attention") == "attention"
    assert apply_session_signal("session-b", "working") == "attention"


def test_apply_session_signal_escalates_permission_over_attention(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(runtime, "STATE_DIR", tmp_path)
    monkeypatch.setattr(runtime, "SESSION_FILE", tmp_path / "sessions.json")
    monkeypatch.setattr(runtime, "LOCK_FILE", tmp_path / "state.lock")

    assert apply_session_signal("session-a", "attention") == "attention"
    assert apply_session_signal("session-b", "permission") == "permission"


def test_apply_session_signal_removes_session_on_end(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(runtime, "STATE_DIR", tmp_path)
    monkeypatch.setattr(runtime, "SESSION_FILE", tmp_path / "sessions.json")
    monkeypatch.setattr(runtime, "LOCK_FILE", tmp_path / "state.lock")

    assert apply_session_signal("session-a", "working") == "working"
    assert apply_session_signal("session-a", "session_end") == "idle"

    assert runtime.read_session_snapshot() == {"aggregate": "idle", "sessions": {}}


def test_apply_session_signal_notices_one_session_end_while_another_works(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(runtime, "STATE_DIR", tmp_path)
    monkeypatch.setattr(runtime, "SESSION_FILE", tmp_path / "sessions.json")
    monkeypatch.setattr(runtime, "LOCK_FILE", tmp_path / "state.lock")

    assert apply_session_signal("session-a", "working") == "working"
    assert apply_session_signal("session-b", "working") == "working"
    assert apply_session_signal("session-a", "session_end") == "working"


def test_apply_session_signal_does_not_notice_unknown_session_end(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(runtime, "STATE_DIR", tmp_path)
    monkeypatch.setattr(runtime, "SESSION_FILE", tmp_path / "sessions.json")
    monkeypatch.setattr(runtime, "LOCK_FILE", tmp_path / "state.lock")

    assert apply_session_signal("missing-session", "session_end") == "idle"


def test_apply_session_signal_keeps_red_alert_on_session_end(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(runtime, "STATE_DIR", tmp_path)
    monkeypatch.setattr(runtime, "SESSION_FILE", tmp_path / "sessions.json")
    monkeypatch.setattr(runtime, "LOCK_FILE", tmp_path / "state.lock")

    assert apply_session_signal("session-a", "working") == "working"
    assert apply_session_signal("session-b", "permission") == "permission"
    assert apply_session_signal("session-a", "session_end") == "permission"


def test_apply_session_signal_clears_non_urgent_session_on_turn_end(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(runtime, "STATE_DIR", tmp_path)
    monkeypatch.setattr(runtime, "SESSION_FILE", tmp_path / "sessions.json")
    monkeypatch.setattr(runtime, "LOCK_FILE", tmp_path / "state.lock")

    assert apply_session_signal("session-a", "working") == "working"
    assert apply_session_signal("session-a", "turn_end") == "idle"

    assert runtime.read_session_snapshot() == {"aggregate": "idle", "sessions": {}}


def test_session_turn_end_while_other_sessions_working(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(runtime, "STATE_DIR", tmp_path)
    monkeypatch.setattr(runtime, "SESSION_FILE", tmp_path / "sessions.json")
    monkeypatch.setattr(runtime, "LOCK_FILE", tmp_path / "state.lock")

    assert apply_session_signal("session-a", "working") == "working"
    assert apply_session_signal("session-b", "working") == "working"
    assert apply_session_signal("session-b", "turn_end") == "working"

    snapshot = runtime.read_session_snapshot()
    assert "session-a" in snapshot["sessions"]
    assert "session-b" not in snapshot["sessions"]


def test_apply_session_signal_keeps_permission_on_turn_end(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(runtime, "STATE_DIR", tmp_path)
    monkeypatch.setattr(runtime, "SESSION_FILE", tmp_path / "sessions.json")
    monkeypatch.setattr(runtime, "LOCK_FILE", tmp_path / "state.lock")

    assert apply_session_signal("session-a", "permission") == "permission"
    assert apply_session_signal("session-a", "turn_end") == "permission"

    assert runtime.read_session_snapshot()["aggregate"] == "permission"


def test_manual_idle_clears_all_session_state(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(runtime, "STATE_DIR", tmp_path)
    monkeypatch.setattr(runtime, "SESSION_FILE", tmp_path / "sessions.json")
    monkeypatch.setattr(runtime, "LOCK_FILE", tmp_path / "state.lock")

    assert apply_session_signal("session-a", "attention") == "attention"
    assert cli.play_signal("idle") == 0
    assert runtime.read_session_snapshot() == {"aggregate": "idle", "sessions": {}}


def test_manual_off_clears_all_session_state(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(runtime, "STATE_DIR", tmp_path)
    monkeypatch.setattr(runtime, "SESSION_FILE", tmp_path / "sessions.json")
    monkeypatch.setattr(runtime, "LOCK_FILE", tmp_path / "state.lock")

    assert apply_session_signal("session-a", "permission") == "permission"
    assert cli.play_signal("off") == 0
    assert runtime.read_session_snapshot() == {"aggregate": "idle", "sessions": {}}


# ---------------------------------------------------------------------------
# Hook installer
# ---------------------------------------------------------------------------

def test_supported_agents_exposes_codex_and_claude_code(tmp_path) -> None:
    agents = hook_installer.supported_agents(home=tmp_path)

    assert set(agents) == {"codex", "claude-code"}
    assert agents["codex"].config_path == tmp_path / ".codex" / "hooks.json"
    assert agents["claude-code"].config_path == tmp_path / ".claude" / "settings.json"


def test_inspect_agent_marks_missing_config_as_needing_install(tmp_path) -> None:
    spec = hook_installer.supported_agents(home=tmp_path)["codex"]

    status = hook_installer.inspect_agent(spec)

    assert not status.installed
    assert status.message == "config missing"


def test_install_agent_writes_codex_hooks_and_backups_existing_file(tmp_path) -> None:
    spec = hook_installer.supported_agents(home=tmp_path)["codex"]
    spec.config_path.parent.mkdir(parents=True, exist_ok=True)
    existing_hook = {"hooks": [{"type": "command", "command": "echo keep-me", "timeout": 1}]}
    spec.config_path.write_text(json.dumps({"hooks": {"Stop": [existing_hook]}}, indent=2))

    result = hook_installer.install_agent(spec)

    assert result.status.installed
    assert result.backup_path is not None
    data = json.loads(spec.config_path.read_text())
    assert set(data["hooks"]) == {"SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "PermissionRequest", "Stop", "SessionEnd"}
    assert existing_hook in data["hooks"]["Stop"]


def test_install_agent_replaces_existing_signal_light_hooks_but_keeps_other_hooks(tmp_path) -> None:
    spec = hook_installer.supported_agents(home=tmp_path)["claude-code"]
    spec.config_path.parent.mkdir(parents=True, exist_ok=True)
    existing = {
        "hooks": {
            "Stop": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": str(hook_installer.CLAUDE_CODE_HOOK_SCRIPT),
                            "timeout": 1,
                        }
                    ],
                    "matcher": "",
                },
                {
                    "hooks": [{"type": "command", "command": "echo keep-me", "timeout": 1}],
                    "matcher": "",
                },
            ]
        }
    }
    spec.config_path.write_text(json.dumps(existing, indent=2))

    hook_installer.install_agent(spec)

    data = json.loads(spec.config_path.read_text())
    stop_groups = data["hooks"]["Stop"]
    assert len(stop_groups) == 2
    assert stop_groups[0]["hooks"][0]["command"] == str(hook_installer.CLAUDE_CODE_HOOK_SCRIPT)
    assert stop_groups[0]["hooks"][0]["timeout"] == 5
    assert stop_groups[1]["hooks"][0]["command"] == "echo keep-me"


def test_install_agent_preserves_existing_hook_order_when_repairing(tmp_path) -> None:
    spec = hook_installer.supported_agents(home=tmp_path)["claude-code"]
    spec.config_path.parent.mkdir(parents=True, exist_ok=True)
    existing = {
        "hooks": {
            "Stop": [
                {
                    "hooks": [
                        {"type": "command", "command": "echo before", "timeout": 1},
                        {
                            "type": "command",
                            "command": str(hook_installer.CLAUDE_CODE_HOOK_SCRIPT),
                            "timeout": 1,
                        },
                        {"type": "command", "command": "echo after", "timeout": 1},
                    ],
                    "matcher": "",
                }
            ]
        }
    }
    spec.config_path.write_text(json.dumps(existing, indent=2))

    hook_installer.install_agent(spec)

    data = json.loads(spec.config_path.read_text())
    hooks = data["hooks"]["Stop"][0]["hooks"]
    assert [hook["command"] for hook in hooks] == [
        "echo before",
        str(hook_installer.CLAUDE_CODE_HOOK_SCRIPT),
        "echo after",
    ]
    assert hooks[1]["timeout"] == 5


def test_inspect_agent_marks_wrong_timeout_as_broken(tmp_path) -> None:
    spec = hook_installer.supported_agents(home=tmp_path)["codex"]
    spec.config_path.parent.mkdir(parents=True, exist_ok=True)
    hook_command = f"{hook_installer.CODEX_HOOK_SCRIPT} PermissionRequest"
    spec.config_path.write_text(
        json.dumps(
            {
                "hooks": {
                    event: [
                        {
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": f"{hook_installer.CODEX_HOOK_SCRIPT} {event}",
                                    "timeout": 5,
                                }
                            ]
                        }
                    ]
                    for event in hook_installer.CODEX_EVENTS
                }
            },
            indent=2,
        )
    )
    data = json.loads(spec.config_path.read_text())
    data["hooks"]["PermissionRequest"][0]["hooks"][0]["command"] = hook_command
    data["hooks"]["PermissionRequest"][0]["hooks"][0]["timeout"] = 5
    spec.config_path.write_text(json.dumps(data, indent=2))

    status = hook_installer.inspect_agent(spec)

    assert not status.installed
    assert status.broken_events == ("PermissionRequest",)


def test_hook_command_quotes_paths_with_spaces() -> None:
    spec = hook_installer.AgentSpec(
        key="codex",
        name="Codex",
        config_path=Path("/tmp/unused.json"),
        hook_script=Path("/tmp/signal light/scripts/codex-signal-hook"),
        events={},
        passes_event_arg=True,
    )

    command = hook_installer._hook_command(spec, "Stop")

    assert command == "'/tmp/signal light/scripts/codex-signal-hook' Stop"


def test_install_wizard_selects_missing_agents_by_default(tmp_path, monkeypatch) -> None:
    codex_spec = hook_installer.supported_agents(home=tmp_path)["codex"]
    claude_spec = hook_installer.supported_agents(home=tmp_path)["claude-code"]
    codex_spec.config_path.parent.mkdir(parents=True, exist_ok=True)
    codex_spec.config_path.write_text(json.dumps({"hooks": {}}, indent=2))

    written: list[str] = []

    def fake_install(spec, backup=True):
        written.append(spec.key)
        return hook_installer.InstallResult(
            status=hook_installer.inspect_agent(spec), changed=True, backup_path=None
        )

    monkeypatch.setattr(hook_installer, "install_agent", fake_install)

    stdin = io.StringIO("\n")
    stdout = io.StringIO()
    assert hook_installer.run_install_wizard(stdin=stdin, stdout=stdout, home=tmp_path, yes=True) == 0

    assert written == ["codex", "claude-code"]
    assert "Signal Light hook installer" in stdout.getvalue()


def test_install_wizard_supports_explicit_agent_selection(tmp_path, monkeypatch) -> None:
    selected: list[str] = []

    def fake_install(spec, backup=True):
        selected.append(spec.key)
        return hook_installer.InstallResult(
            status=hook_installer.inspect_agent(spec), changed=True, backup_path=None
        )

    monkeypatch.setattr(hook_installer, "install_agent", fake_install)

    assert hook_installer.run_install_wizard(selected_agents=["codex"], home=tmp_path, yes=True) == 0

    assert selected == ["codex"]


def test_install_hooks_cli_invokes_wizard(monkeypatch) -> None:
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(hook_installer, "run_install_wizard", lambda **kwargs: calls.append(kwargs) or 0)

    assert cli.main(["install-hooks", "--agent", "codex", "--dry-run"]) == 0

    assert calls == [{"selected_agents": ["codex"], "all_agents": False, "yes": False, "dry_run": True, "no_gui": False}]
