"""Reusable UI widgets. Right now: just Button. Future home for any
overlay-side widget (toast, prompt, scrollbar) once panels migrate
off the Ursina-entity layout."""
from __future__ import annotations

from dataclasses import dataclass, field

import pygame

from baris.client.ui_overlay.palette import (
    BORDER,
    BORDER_HOVER,
    DIM,
    FG,
    HIGHLIGHT,
    MUTED,
    PANEL,
    PANEL_DISABLED,
    PANEL_HOVER,
)
from baris.client.ui_overlay.typography import draw_text_centered, font


@dataclass
class Button:
    """Clickable rectangular button with hover/pressed state.

    Call .handle_event(event) for each pygame event; it returns True exactly
    once, on the frame the button is released while hovered. Call .draw()
    each frame.
    """

    rect: pygame.Rect
    label: str
    key_hint: str | None = None
    enabled: bool = True
    selected: bool = False
    _hover: bool = field(default=False, init=False)
    _down: bool = field(default=False, init=False)

    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self.enabled:
            self._hover = False
            self._down = False
            return False
        if event.type == pygame.MOUSEMOTION:
            self._hover = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self._down = True
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            was_down = self._down
            self._down = False
            if was_down and self.rect.collidepoint(event.pos):
                return True
        return False

    def draw(self, surface: pygame.Surface) -> None:
        if not self.enabled:
            bg = PANEL_DISABLED
            border = MUTED
            fg = DIM
        elif self._down and self._hover:
            bg = BORDER
            border = BORDER_HOVER
            fg = FG
        elif self._hover:
            bg = PANEL_HOVER
            border = BORDER_HOVER
            fg = FG
        elif self.selected:
            bg = PANEL_HOVER
            border = HIGHLIGHT
            fg = HIGHLIGHT
        else:
            bg = PANEL
            border = BORDER
            fg = FG
        pygame.draw.rect(surface, bg, self.rect, border_radius=6)
        pygame.draw.rect(surface, border, self.rect, 2, border_radius=6)
        draw_text_centered(surface, self.label, self.rect.center, size=18, color=fg, bold=True)
        if self.key_hint:
            hint = font(12).render(f"[{self.key_hint}]", True, DIM)
            hint_rect = hint.get_rect()
            hint_rect.bottomright = (self.rect.right - 6, self.rect.bottom - 4)
            surface.blit(hint, hint_rect)
