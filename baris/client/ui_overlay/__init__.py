"""Pygame-based UI toolkit shared between the 2D client and the 3D
client's overlay layer.

Step 1 of the UI refactor that drops the standalone 2D game in
favour of a pygame overlay composited on top of the 3D world. The
public surface (palette, font, draw_text, Button) is the same one
the 2D client has used since day one — moved here so the 3D
client can render its menus through the same toolkit instead of
trying to fake 2D widgets out of Ursina entities.

Public API is re-exported flat so callers stay short:
    from baris.client.ui_overlay import draw_text, Button, FG
"""
from baris.client.ui_overlay.palette import (
    ACCENT_USA,
    ACCENT_USSR,
    BG,
    BG_DEEP,
    BORDER,
    BORDER_HOVER,
    DIM,
    FG,
    GREEN,
    HIGHLIGHT,
    MUTED,
    PANEL,
    PANEL_DISABLED,
    PANEL_HOVER,
    RED,
)
from baris.client.ui_overlay.typography import (
    draw_text,
    draw_text_centered,
    font,
)
from baris.client.ui_overlay.widgets import Button

__all__ = [
    "ACCENT_USA", "ACCENT_USSR",
    "BG", "BG_DEEP", "BORDER", "BORDER_HOVER",
    "DIM", "FG", "GREEN", "HIGHLIGHT", "MUTED",
    "PANEL", "PANEL_DISABLED", "PANEL_HOVER", "RED",
    "Button",
    "draw_text", "draw_text_centered", "font",
]
