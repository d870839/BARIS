"""Lazy-cached fonts + the two text-blit helpers every panel uses.

`font(size, bold)` caches by (size, bold) so we don't pay for a
fresh SysFont each frame. `draw_text` / `draw_text_centered` are
the only two ways UI code is allowed to put glyphs on a Surface —
keeps the look consistent and pre-bakes the antialias flag."""
from __future__ import annotations

import pygame

from baris.client.ui_overlay.palette import FG


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
