"""Generate coloured circle PNG icons for the macOS menu bar.

Uses only the standard library (struct + zlib) — no PIL dependency.
"""

from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

# Material Design inspired palette.
COLORS: dict[str, tuple[int, int, int]] = {
    "green": (76, 175, 80),
    "yellow": (255, 193, 7),
    "red": (244, 67, 54),
    "grey": (158, 158, 158),
}

BRIGHTNESS_LEVELS: list[float] = [0.0, 0.1, 0.2, 0.3, 0.5, 0.7, 1.0]

DEFAULT_ICON_SIZE = 22


def generate_all_icons(cache_dir: Path) -> dict[str, dict[float, Path]]:
    """Pre-generate every colour × brightness variant and return a lookup dict."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    result: dict[str, dict[float, Path]] = {}
    for color, rgb in COLORS.items():
        result[color] = {}
        for brightness in BRIGHTNESS_LEVELS:
            path = cache_dir / _icon_filename(color, brightness)
            if not path.exists():
                path.write_bytes(_create_circle_png(rgb, brightness, DEFAULT_ICON_SIZE))
            result[color][brightness] = path
    return result


def get_icon_path(icons: dict[str, dict[float, Path]], color: str, brightness: float = 1.0) -> Path:
    """Return the closest cached icon path for a given colour and brightness."""
    brightness = max(0.0, min(1.0, brightness))
    levels = icons.get(color, icons.get("grey", {}))
    closest = min(levels.keys(), key=lambda b: abs(b - brightness))
    return levels[closest]


def _icon_filename(color: str, brightness: float) -> str:
    return f"{color}_b{int(brightness * 100):03d}.png"


# ---------------------------------------------------------------------------
# Raw PNG generation
# ---------------------------------------------------------------------------

def _create_circle_png(color_rgb: tuple[int, int, int], brightness: float, size: int) -> bytes:
    """Return PNG bytes for a filled anti-aliased circle on a transparent background."""
    r, g, b = color_rgb
    brightness = max(0.0, min(1.0, brightness))
    # Blend toward black for low brightness; toward white for readability at high brightness.
    ri = int(r * brightness)
    gi = int(g * brightness)
    bi = int(b * brightness)

    width = height = size
    center = (size - 1) / 2.0
    radius = (size - 2) / 2.0

    raw_rows: list[bytes] = []
    for y in range(height):
        row = bytearray([0])  # filter byte: None
        for x in range(width):
            dx = x - center
            dy = y - center
            dist = math.sqrt(dx * dx + dy * dy)
            if dist <= radius - 0.5:
                alpha = 255
            elif dist <= radius + 0.5:
                alpha = int(255 * (radius + 0.5 - dist))
            else:
                alpha = 0
            row.extend((ri, gi, bi, alpha))
        raw_rows.append(bytes(row))

    return _encode_png(width, height, b"".join(raw_rows))


def _encode_png(width: int, height: int, raw_pixels: bytes) -> bytes:
    """Assemble a minimal RGBA PNG from raw filtered scanlines."""
    def _chunk(chunk_type: bytes, data: bytes) -> bytes:
        body = chunk_type + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)  # 8-bit RGBA
    idat = zlib.compress(raw_pixels, 9)
    return (
        signature
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", idat)
        + _chunk(b"IEND", b"")
    )
