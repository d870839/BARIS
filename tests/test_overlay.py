"""Tests for the engine-agnostic pygame overlay (step 2 of the
UI refactor). The Ursina-side host (overlay_host.py) needs a real
GPU + window so it isn't tested here; this file just exercises
the surface, the panel registry, and the event-dispatch loop."""
from __future__ import annotations

import os

# Force pygame to skip opening a window. Has to happen before
# pygame is imported anywhere, including transitively through
# the overlay module under test.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from baris.client.ui_overlay.overlay import OverlayPanel, PygameOverlay
from baris.client.ui_overlay.panels import WatermarkPanel


class _RecordingPanel(OverlayPanel):
    """Test fixture: counts draw / event calls and remembers the
    last surface size it was painted onto."""

    def __init__(self) -> None:
        self.draw_count = 0
        self.events: list[pygame.event.Event] = []
        self.last_size: tuple[int, int] | None = None

    def draw(self, surface: pygame.Surface) -> None:
        self.draw_count += 1
        self.last_size = surface.get_size()

    def handle_event(self, event: pygame.event.Event) -> None:
        self.events.append(event)


def test_overlay_initial_render_paints_panels() -> None:
    """The overlay starts dirty so the first render() draws every
    registered panel onto the surface, even without any events."""
    overlay = PygameOverlay((640, 480))
    panel = _RecordingPanel()
    overlay.add_panel(panel)
    drew = overlay.render()
    assert drew is True
    assert panel.draw_count == 1
    assert panel.last_size == (640, 480)


def test_overlay_skips_redraw_when_clean() -> None:
    """If nothing has changed (no events, no request_redraw), a
    second render() should be a no-op so the host can skip the
    GPU upload."""
    overlay = PygameOverlay((320, 240))
    overlay.add_panel(_RecordingPanel())
    overlay.render()
    drew_again = overlay.render()
    assert drew_again is False


def test_overlay_dispatches_events_to_panels() -> None:
    """A queued event hits every registered panel before the next
    redraw, in registration order."""
    overlay = PygameOverlay((320, 240))
    a = _RecordingPanel()
    b = _RecordingPanel()
    overlay.add_panel(a)
    overlay.add_panel(b)
    overlay.render()  # consume initial dirty
    overlay.post_mouse_motion((100, 50))
    overlay.render()
    assert len(a.events) == 1
    assert len(b.events) == 1
    assert a.events[0].type == pygame.MOUSEMOTION
    assert a.events[0].pos == (100, 50)


def test_overlay_request_redraw_forces_next_frame() -> None:
    """request_redraw() bumps the dirty flag so the next render
    actually repaints — used by panels driven by external timers
    (e.g. cinematic phase reveals) where there's no triggering
    event."""
    overlay = PygameOverlay((320, 240))
    panel = _RecordingPanel()
    overlay.add_panel(panel)
    overlay.render()
    overlay.request_redraw()
    overlay.render()
    assert panel.draw_count == 2


def test_overlay_remove_panel_drops_it_from_subsequent_draws() -> None:
    """Removing a panel pulls it out of the registry so it stops
    receiving events and stops being drawn."""
    overlay = PygameOverlay((320, 240))
    panel = _RecordingPanel()
    overlay.add_panel(panel)
    overlay.render()
    overlay.remove_panel(panel)
    overlay.post_mouse_motion((10, 10))
    overlay.render()
    # Only one draw — from the initial registration.
    assert panel.draw_count == 1
    assert panel.events == []


def test_overlay_to_rgba_bytes_returns_full_surface_payload() -> None:
    """The host uploads the surface bytes to a Panda3D texture each
    frame. The byte-count should match the surface dimensions exactly."""
    overlay = PygameOverlay((64, 48))
    overlay.render()
    raw = overlay.to_rgba_bytes()
    assert len(raw) == 64 * 48 * 4   # RGBA, 1 byte per channel


def test_watermark_panel_renders_visible_pixels() -> None:
    """Smoke test for the WatermarkPanel: after rendering, the
    overlay surface should contain at least one non-transparent
    pixel in the bottom-left corner where the badge sits."""
    overlay = PygameOverlay((640, 480))
    overlay.add_panel(WatermarkPanel((640, 480)))
    overlay.render()
    # Watermark badge sits at (12, 480-30..480-8). Sample a pixel
    # well inside it and confirm alpha > 0.
    sample = overlay.surface.get_at((20, 460))
    assert sample.a > 0, f"watermark badge should paint visible pixels, got {sample}"
