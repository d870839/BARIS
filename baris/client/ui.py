"""DEPRECATED — kept as a re-export shim. The toolkit moved into
baris.client.ui_overlay so it can be reused by the 3D client's
overlay layer. Import from there directly:

    from baris.client.ui_overlay import draw_text, Button, FG

This module will be removed once external scripts (if any) catch
up with the rename.
"""
from baris.client.ui_overlay import *  # noqa: F401,F403
from baris.client.ui_overlay import (  # noqa: F401  -- explicit re-exports
    ACCENT_USA,
    ACCENT_USSR,
    BG,
    BG_DEEP,
    BORDER,
    BORDER_HOVER,
    Button,
    DIM,
    FG,
    GREEN,
    HIGHLIGHT,
    MUTED,
    PANEL,
    PANEL_DISABLED,
    PANEL_HOVER,
    RED,
    draw_text,
    draw_text_centered,
    font,
)
