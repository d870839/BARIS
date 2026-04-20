"""Small pygame UI toolkit: colors, fonts, and a reusable Button widget."""
from __future__ import annotations

from dataclasses import dataclass, field

import pygame


# ----- palette --------------------------------------------------------------

BG             = (10, 14, 28)
BG_DEEP        = (5, 8, 18)
PANEL          = (20, 28, 48)
PANEL_HOVER    = (34, 44, 70)
PANEL_DISABLED = (18, 22, 34)
BORDER         = (60, 70, 100)
BORDER_HOVER   = (140, 170, 220)
FG             = (220, 225, 235)
DIM            = (120, 130, 150)
MUTED          = (80, 90, 110)
ACCENT_USA     = (80, 140, 220)
ACCENT_USSR    = (220, 90, 90)
HIGHLIGHT      = (240, 200, 90)
GREEN          = (110, 200, 120)
RED            = (220, 90, 90)


# ----- fonts (lazy init) ----------------------------------------------------

_fonts: dict[tuple[int, bool], pygame.font.Font] = {}


def font(size: int, bold: bool = False) -> pygame.font.Font:
    key = (size, bold)
    if key not in _fonts:
        _fonts[key] = pygame.font.SysFont("consolas", size, bold=bold)
    return _fonts[key]


def draw_text(surface: pygame.Surface, text: str, pos: tuple[int, int],
              size: int = 18, color: tuple[int, int, int] = FG,
              bold: bool = False) -> pygame.Rect:
    rendered = font(size, bold).render(text, True, color)
    return surface.blit(rendered, pos)


def draw_text_centered(surface: pygame.Surface, text: str, center: tuple[int, int],
                       size: int = 18, color: tuple[int, int, int] = FG,
                       bold: bool = False) -> pygame.Rect:
    rendered = font(size, bold).render(text, True, color)
    rect = rendered.get_rect(center=center)
    return surface.blit(rendered, rect)


# ----- buttons --------------------------------------------------------------

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
