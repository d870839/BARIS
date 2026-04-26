"""Concrete OverlayPanel subclasses that the 3D client mounts on
the pygame overlay. As panels migrate off Ursina entities they
land here.

WatermarkPanel is the smoke test we ship at step 2 — it paints a
small "BARIS overlay" badge in the corner so we can verify the
compositing pipeline (pygame Surface -> Panda3D texture -> screen)
is wired up correctly before porting real menus. Once at least
one real panel is rendering through the overlay, this class will
likely be retired."""
from __future__ import annotations

import pygame

from baris.client.ui_overlay.overlay import OverlayPanel
from baris.client.ui_overlay.palette import BORDER, DIM, HIGHLIGHT, PANEL
from baris.client.ui_overlay.typography import draw_text


class WatermarkPanel(OverlayPanel):
    """Tiny corner badge so the dev / QA can tell at a glance that
    the pygame overlay is rendering. Positioned in the bottom-left
    so it doesn't clash with the 3D HUD's existing top-row tabs."""

    def __init__(self, screen_size: tuple[int, int], label: str = "BARIS overlay") -> None:
        self.screen_size = screen_size
        self.label = label

    def draw(self, surface: pygame.Surface) -> None:
        w, h = self.screen_size
        rect = pygame.Rect(12, h - 30, 200, 22)
        # Translucent panel so the underlying 3D world peeks through.
        bg = pygame.Surface(rect.size, pygame.SRCALPHA)
        bg.fill((*PANEL, 200))
        surface.blit(bg, rect.topleft)
        pygame.draw.rect(surface, BORDER, rect, 1, border_radius=4)
        draw_text(
            surface, self.label, (rect.x + 8, rect.y + 4),
            size=14, color=HIGHLIGHT,
        )
