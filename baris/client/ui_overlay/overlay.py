"""Pygame overlay surface — the engine-agnostic core of the 3D
client's UI layer.

The 3D client's menus used to render through Ursina Text / Button
entities, which are 3D quads parented (transitively) to the
perspective camera. That causes z-fighting against world geometry,
font-scale drift with FOV, and a long tail of glitches. The fix is
to stop drawing menus as 3D things at all: we render every panel
into a regular pygame Surface and the engine-side host
(client3d/overlay_host.py) blits that Surface to the screen as a
single full-screen 2D quad.

This module is deliberately Ursina-free so it can be unit-tested
without spinning up a window.

Lifecycle each frame:

    1. host calls overlay.render(); the overlay clears its Surface,
       dispatches any queued events to each registered panel, then
       redraws every panel onto the Surface.
    2. host uploads overlay.surface to a Panda3D Texture.
    3. Ursina renders normally; the overlay quad sits on the
       camera.ui scene so it's drawn on top of everything else.
"""
from __future__ import annotations

import os

# Suppress pygame's banner. We import pygame next, so this has to
# happen at module level before the import resolves — and it has to
# stay regardless of whether we already have a window (the 2D client
# has one of its own, the 3D client uses the dummy driver below).
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
# When the 3D client is the host, pygame doesn't need its own
# window — we only use its drawing primitives. The "dummy" SDL
# video driver lets pygame.font + Surface work without ever
# popping a real OS window. The 2D client overrides this by
# init'ing a real display before importing this module, so the
# default below only kicks in when nobody has chosen a driver.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame


class OverlayPanel:
    """Base class for anything drawn through the overlay.

    Subclasses override draw(surface) to paint themselves; an
    interactive panel additionally overrides handle_event(event)
    to react to mouse / keyboard input. The overlay keeps panels
    in registration order — first-added is drawn first (bottom of
    the stack), so a modal panel registered last is on top.
    """

    def draw(self, surface: pygame.Surface) -> None:
        raise NotImplementedError

    def handle_event(self, event: pygame.event.Event) -> None:
        """Default: ignore. Override in interactive subclasses."""
        return


class PygameOverlay:
    """Shared overlay state: the off-screen Surface every panel
    draws into and the methods that move it onto the screen via
    the engine-specific host."""

    def __init__(self, size: tuple[int, int]) -> None:
        # pygame.font requires the display subsystem to be init'd
        # even if we never present a window. Be defensive: only
        # init what's missing so co-existing 2D clients keep their
        # already-set-up display.
        if not pygame.display.get_init():
            pygame.display.init()
            pygame.display.set_mode((1, 1))
        if not pygame.font.get_init():
            pygame.font.init()

        self.size = size
        self.surface: pygame.Surface = pygame.Surface(size, pygame.SRCALPHA)
        self._panels: list[OverlayPanel] = []
        self._dirty: bool = True
        self._pending_events: list[pygame.event.Event] = []

    # ------------------------------------------------------------------
    # Panel registry
    # ------------------------------------------------------------------
    def add_panel(self, panel: OverlayPanel) -> None:
        self._panels.append(panel)
        self._dirty = True

    def remove_panel(self, panel: OverlayPanel) -> None:
        if panel in self._panels:
            self._panels.remove(panel)
            self._dirty = True

    def clear_panels(self) -> None:
        self._panels.clear()
        self._dirty = True

    @property
    def panels(self) -> tuple[OverlayPanel, ...]:
        return tuple(self._panels)

    def request_redraw(self) -> None:
        """Force the next render() to redraw even if nothing else
        changed. Panels call this when their internal state shifts
        without a fresh event (e.g. timer-driven animations)."""
        self._dirty = True

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------
    def post_event(self, event: pygame.event.Event) -> None:
        """Queue an event for the next dispatch."""
        self._pending_events.append(event)
        self._dirty = True

    def post_mouse_motion(self, pos: tuple[int, int]) -> None:
        self.post_event(pygame.event.Event(
            pygame.MOUSEMOTION, pos=pos, rel=(0, 0), buttons=(0, 0, 0),
        ))

    def post_mouse_down(self, pos: tuple[int, int], button: int = 1) -> None:
        self.post_event(pygame.event.Event(
            pygame.MOUSEBUTTONDOWN, pos=pos, button=button,
        ))

    def post_mouse_up(self, pos: tuple[int, int], button: int = 1) -> None:
        self.post_event(pygame.event.Event(
            pygame.MOUSEBUTTONUP, pos=pos, button=button,
        ))

    # ------------------------------------------------------------------
    # Frame loop
    # ------------------------------------------------------------------
    def render(self) -> bool:
        """Run one overlay frame: dispatch pending events and redraw
        the surface from active panels.

        Returns True if anything was redrawn (so the host can skip
        re-uploading the texture when nothing changed). The host
        always calls this; the host alone decides whether to push
        the new bytes to the GPU."""
        if not self._dirty and not self._pending_events:
            return False
        events = self._pending_events
        self._pending_events = []
        for panel in list(self._panels):
            for ev in events:
                panel.handle_event(ev)
        # Clear to transparent and re-paint every panel each frame.
        # The 2D client takes the same approach — panels are simple
        # enough that a full repaint is cheaper than tracking dirty
        # rects per-panel.
        self.surface.fill((0, 0, 0, 0))
        for panel in self._panels:
            panel.draw(self.surface)
        self._dirty = False
        return True

    def to_rgba_bytes(self, flip_y: bool = True) -> bytes:
        """Surface bytes in RGBA byte order. flip_y flips the row
        order so the result matches OpenGL's bottom-left origin
        (Panda3D textures inherit OpenGL's convention)."""
        return pygame.image.tostring(self.surface, "RGBA", flip_y)
