"""Tests for the software UI (menu bar daemon, icon generation, launchd)."""

import json
import os
import struct
from pathlib import Path

import pytest

from signal_light.agent_signals import SIGNALS, Frame
from signal_light.gui import daemon as gui_daemon
from signal_light.gui import icon_generator
from signal_light.gui import launchd
from signal_light import cli
from signal_light import runtime


# ---------------------------------------------------------------------------
# compute_current_frame — pure animation logic
# ---------------------------------------------------------------------------

class TestComputeCurrentFrame:
    def test_returns_first_frame_at_zero_elapsed(self) -> None:
        frames = (Frame(green=True, seconds=0.5), Frame(yellow=True, seconds=0.5))
        idx, frame = gui_daemon.compute_current_frame(0.0, frames)
        assert idx == 0
        assert frame is frames[0]

    def test_advances_after_first_frame_duration(self) -> None:
        frames = (Frame(green=True, seconds=0.5), Frame(yellow=True, seconds=0.5))
        idx, frame = gui_daemon.compute_current_frame(0.6, frames)
        assert idx == 1
        assert frame is frames[1]

    def test_wraps_around_for_repeating_signals(self) -> None:
        frames = (Frame(green=True, seconds=0.5), Frame(yellow=True, seconds=0.5))
        idx, frame = gui_daemon.compute_current_frame(1.0 + 0.3, frames)
        assert idx == 0  # wrapped around, 0.3s into the second cycle
        assert frame is frames[0]

    def test_handles_empty_frames(self) -> None:
        idx, frame = gui_daemon.compute_current_frame(0.5, ())
        assert idx == 0
        assert frame == Frame()

    def test_handles_zero_duration_frames(self) -> None:
        frames = (Frame(green=True, seconds=0.0),)
        idx, frame = gui_daemon.compute_current_frame(0.0, frames)
        assert idx == 0

    def test_work_cycle_flashes_green(self) -> None:
        signal = SIGNALS["working"]
        assert len(signal.frames) == 2
        assert signal.repeat is True
        # First frame is the green flash, second is the off pause.
        assert signal.frames[0].green is True
        assert signal.frames[0].yellow is False
        assert signal.frames[0].red is False
        assert signal.frames[1].green is False


# ---------------------------------------------------------------------------
# Icon generation
# ---------------------------------------------------------------------------

class TestIconGeneration:
    def test_create_circle_png_has_valid_magic(self) -> None:
        data = icon_generator._create_circle_png((76, 175, 80), 1.0, 22)
        assert data[:8] == b"\x89PNG\r\n\x1a\n"

    def test_create_circle_png_has_correct_dimensions(self) -> None:
        data = icon_generator._create_circle_png((76, 175, 80), 1.0, 22)
        # IHDR starts at byte 8 (after signature), width at offset 8+4=12, height at 16.
        width = struct.unpack(">I", data[16:20])[0]
        height = struct.unpack(">I", data[20:24])[0]
        assert width == 22
        assert height == 22

    def test_generate_all_icons_creates_files(self, tmp_path: Path) -> None:
        icons = icon_generator.generate_all_icons(tmp_path)
        for color in icon_generator.COLORS:
            assert color in icons
            for brightness in icon_generator.BRIGHTNESS_LEVELS:
                path = icons[color][brightness]
                assert path.exists()
                assert path.stat().st_size > 0

    def test_get_icon_path_returns_closest_brightness(self, tmp_path: Path) -> None:
        icons = icon_generator.generate_all_icons(tmp_path)
        path = icon_generator.get_icon_path(icons, "green", 0.45)
        # Closest to 0.45 should be 0.5.
        assert "_b050" in path.name

    def test_brightness_clamping(self) -> None:
        data_low = icon_generator._create_circle_png((255, 0, 0), 0.0, 22)
        data_high = icon_generator._create_circle_png((255, 0, 0), 1.0, 22)
        # Both should be valid PNGs.
        assert data_low[:4] == b"\x89PNG"
        assert data_high[:4] == b"\x89PNG"


# ---------------------------------------------------------------------------
# Launchd plist
# ---------------------------------------------------------------------------

class TestLaunchdPlist:
    def test_plist_contains_label(self) -> None:
        xml = launchd.generate_plist(Path("/tmp/project"))
        assert launchd.PLIST_LABEL in xml

    def test_plist_contains_project_root(self) -> None:
        xml = launchd.generate_plist(Path("/tmp/my-project"))
        assert "/tmp/my-project" in xml

    def test_plist_contains_gui_daemon_command(self) -> None:
        xml = launchd.generate_plist(Path("/tmp/project"))
        assert "gui-daemon" in xml

    def test_plist_contains_state_dir_env(self) -> None:
        xml = launchd.generate_plist(Path("/tmp/project"), state_dir=Path("/custom/state"))
        assert "SIGNAL_LIGHT_STATE_DIR" in xml
        assert "/custom/state" in xml

    def test_plist_path_is_in_launch_agents(self) -> None:
        path = launchd.plist_path()
        assert "LaunchAgents" in str(path)
        assert path.name.endswith(".plist")


# ---------------------------------------------------------------------------
# CLI gui subcommand (mocked)
# ---------------------------------------------------------------------------

class TestCliGui:
    def test_gui_start_spawns_daemon(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        spawned: list[int] = []
        monkeypatch.setattr(runtime, "STATE_DIR", tmp_path)
        monkeypatch.setattr(runtime, "GUI_PID_FILE", tmp_path / "gui-daemon.pid")
        monkeypatch.setattr(
            runtime, "is_gui_daemon_running", lambda: False,
        )
        monkeypatch.setattr(
            runtime, "start_gui_daemon", lambda: (tmp_path / "gui-daemon.pid").write_text("12345") or 12345,
        )

        assert cli.main(["gui", "start"]) == 0

    def test_gui_start_reports_already_running(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(runtime, "is_gui_daemon_running", lambda: True)
        monkeypatch.setattr(runtime, "start_gui_daemon", lambda: None)

        assert cli.main(["gui", "start"]) == 0

    def test_gui_stop(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(runtime, "is_gui_daemon_running", lambda: True)
        stopped: list[bool] = []
        monkeypatch.setattr(runtime, "stop_gui_daemon", lambda: stopped.append(True))

        assert cli.main(["gui", "stop"]) == 0
        assert stopped == [True]

    def test_gui_status_shows_aggregate(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(runtime, "STATE_DIR", tmp_path)
        monkeypatch.setattr(runtime, "SESSION_FILE", tmp_path / "sessions.json")
        monkeypatch.setattr(runtime, "LOCK_FILE", tmp_path / "state.lock")
        monkeypatch.setattr(runtime, "is_gui_daemon_running", lambda: False)

        assert cli.main(["gui", "status"]) == 0

    def test_gui_invalid_action_returns_2(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # The argparse will reject invalid actions, so we test via direct call.
        assert cli.run_gui_action("bogus") == 2


# ---------------------------------------------------------------------------
# Runtime GUI daemon management (mocked)
# ---------------------------------------------------------------------------

class TestRuntimeGuiDaemon:
    def test_is_gui_daemon_running_false_when_no_pid_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(runtime, "GUI_PID_FILE", tmp_path / "gui-daemon.pid")
        assert runtime.is_gui_daemon_running() is False

    def test_is_gui_daemon_running_false_when_process_dead(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        pid_file = tmp_path / "gui-daemon.pid"
        pid_file.write_text("999999")  # unlikely to be a running process
        monkeypatch.setattr(runtime, "GUI_PID_FILE", pid_file)
        assert runtime.is_gui_daemon_running() is False

    def test_stop_gui_daemon_cleans_up_pid(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        pid_file = tmp_path / "gui-daemon.pid"
        pid_file.write_text("999999")
        monkeypatch.setattr(runtime, "GUI_PID_FILE", pid_file)
        monkeypatch.setattr(runtime, "_terminate", lambda pid: None)

        runtime.stop_gui_daemon()
        assert not pid_file.exists()
