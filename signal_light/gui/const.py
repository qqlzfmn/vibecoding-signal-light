"""Shared constants for the GUI package.

Single source of truth for colours, panel dimensions, and the
signal-to-colour mapping used by both the daemon and the panel subprocess.
"""

# ---------------------------------------------------------------------------
# Colour palette — Material Design inspired
# ---------------------------------------------------------------------------

# Hex strings used by tkinter (panel subprocess).
COLOR_GREEN_HEX = "#4CAF50"
COLOR_YELLOW_HEX = "#FFC107"
COLOR_RED_HEX = "#F44336"
COLOR_GREY_HEX = "#9E9E9E"
COLOR_DIM_HEX = "#3A3A3A"
COLOR_OUTLINE_HEX = "#555555"

# RGB tuples (0-255) used by icon PNG generation.
COLOR_GREEN_RGB: tuple[int, int, int] = (76, 175, 80)
COLOR_YELLOW_RGB: tuple[int, int, int] = (255, 193, 7)
COLOR_RED_RGB: tuple[int, int, int] = (244, 67, 54)
COLOR_GREY_RGB: tuple[int, int, int] = (158, 158, 158)

# Name → RGB mapping (icon_generator uses this to produce PNGs).
COLORS: dict[str, tuple[int, int, int]] = {
    "green": COLOR_GREEN_RGB,
    "yellow": COLOR_YELLOW_RGB,
    "red": COLOR_RED_RGB,
    "grey": COLOR_GREY_RGB,
}

# Name → hex mapping (panel subprocess uses this for tkinter fill).
COLOR_HEX_MAP: dict[str, str] = {
    "green": COLOR_GREEN_HEX,
    "yellow": COLOR_YELLOW_HEX,
    "red": COLOR_RED_HEX,
    "grey": COLOR_GREY_HEX,
}

# ---------------------------------------------------------------------------
# Signal → colour mapping
# ---------------------------------------------------------------------------

ICON_COLOR_MAP: dict[str, str] = {
    "idle": "green",
    "thinking": "green",
    "working": "green",
    "tool_done": "green",
    "attention": "yellow",
    "permission": "yellow",
    "done": "yellow",
    "blocked": "red",
    "session_start": "green",
    "session_end": "green",
    "session_done": "green",
    "off": "grey",
}

# ---------------------------------------------------------------------------
# Panel layout (shared between daemon positioning and subprocess rendering)
# ---------------------------------------------------------------------------

PANEL_W = 260
PANEL_H = 340
LIGHT_R = 20
LIGHT_GAP = 16
LIGHT_X = 50
