"""Generate and manage a macOS launchd plist for the GUI daemon."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PLIST_LABEL = "com.starlight36.signal-light.gui"


def plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{PLIST_LABEL}.plist"


def generate_plist(project_root: Path, state_dir: Path | None = None) -> str:
    """Return the XML content for a launchd plist that starts the GUI daemon."""
    uv = _find_uv()
    log_path = (state_dir or Path("/private/tmp/signal-light")) / "gui-daemon.log"

    env_block = ""
    if state_dir is not None:
        env_block = f"    <key>SIGNAL_LIGHT_STATE_DIR</key>\n    <string>{state_dir}</string>\n"

    return f"""\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{PLIST_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{uv}</string>
        <string>run</string>
        <string>--directory</string>
        <string>{project_root}</string>
        <string>python</string>
        <string>-m</string>
        <string>signal_light</string>
        <string>gui-daemon</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>StandardOutPath</key>
    <string>{log_path}</string>
    <key>StandardErrorPath</key>
    <string>{log_path}</string>
{env_block}</dict>
</plist>
"""


def install_plist(project_root: Path, state_dir: Path | None = None) -> Path:
    """Write the launchd plist and load it."""
    path = plist_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(generate_plist(project_root, state_dir))
    subprocess.run(["launchctl", "load", "-w", str(path)], check=False)
    return path


def uninstall_plist() -> None:
    """Unload and remove the launchd plist."""
    path = plist_path()
    subprocess.run(["launchctl", "unload", str(path)], check=False)
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _find_uv() -> str:
    """Return the full path to ``uv`` or fall back to ``/usr/bin/env``."""
    from shutil import which

    uv = which("uv")
    if uv:
        return uv
    return "/usr/bin/env"
