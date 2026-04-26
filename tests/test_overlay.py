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


# -----------------------------------------------------------------------
# ResultPanel — first real panel migrated onto the overlay
# -----------------------------------------------------------------------
def _make_launch_report(**overrides):
    """Build a minimal LaunchReport for panel rendering tests."""
    from baris.state import LaunchReport, MissionId
    base = dict(
        side="USA",
        username="Tester",
        mission_id=MissionId.SUBORBITAL.value,
        mission_name="Sub-orbital flight",
        rocket="Atlas",
        rocket_class="Light",
        success=True,
        effective_success=0.85,
        prestige_delta=3,
        reliability_before=60,
        reliability_after=65,
    )
    base.update(overrides)
    return LaunchReport(**base)


def test_result_panel_animates_then_settles() -> None:
    """is_animating() returns True while the cinematic ticker is
    still revealing rows, then False once every row has appeared."""
    from baris.client.ui_overlay.panels import (
        PHASE_TICKER_STEP_S, ResultPanel,
    )
    now = [0.0]
    panel = ResultPanel(
        screen_size=(1280, 720),
        report=_make_launch_report(),
        is_own=True,
        on_continue=lambda: None,
        clock=lambda: now[0],
    )
    # SUBORBITAL has 2 phases. Animation lasts ~ 2 * step_s + slack.
    assert panel.is_animating() is True
    now[0] = 2 * PHASE_TICKER_STEP_S + 0.5
    assert panel.is_animating() is False


def test_result_panel_continue_button_invokes_callback() -> None:
    """Clicking the Continue button fires on_continue(). Mouse
    coordinates are translated by the host before reaching us, so
    here we forge them directly into the panel's button rect."""
    from baris.client.ui_overlay.panels import ResultPanel
    fired = {"n": 0}
    panel = ResultPanel(
        screen_size=(1280, 720),
        report=_make_launch_report(),
        is_own=True,
        on_continue=lambda: fired.__setitem__("n", fired["n"] + 1),
    )
    cx, cy = panel.continue_button.rect.center
    panel.handle_event(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, pos=(cx, cy), button=1,
    ))
    panel.handle_event(pygame.event.Event(
        pygame.MOUSEBUTTONUP, pos=(cx, cy), button=1,
    ))
    assert fired["n"] == 1


def test_result_panel_space_key_invokes_callback() -> None:
    """Pressing Space / Enter on the result panel skips ahead the
    same way the legacy Ursina version did."""
    from baris.client.ui_overlay.panels import ResultPanel
    fired = {"n": 0}
    panel = ResultPanel(
        screen_size=(1280, 720),
        report=_make_launch_report(),
        is_own=True,
        on_continue=lambda: fired.__setitem__("n", fired["n"] + 1),
    )
    panel.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE))
    assert fired["n"] == 1


def test_result_panel_renders_failure_banner() -> None:
    """Failed mission paints a red banner with the failed phase named
    in the sub-line. Smoke-tests the banner branch without asserting
    on pixel values — we just check the panel paints SOME pixels in
    the banner area without throwing."""
    from baris.client.ui_overlay.overlay import PygameOverlay
    from baris.client.ui_overlay.panels import ResultPanel
    overlay = PygameOverlay((1280, 720))
    panel = ResultPanel(
        screen_size=(1280, 720),
        report=_make_launch_report(
            success=False,
            failed_phase="Re-entry",
            effective_success=0.45,
        ),
        is_own=True,
        on_continue=lambda: None,
    )
    overlay.add_panel(panel)
    overlay.render()
    # Banner sits at (cx-280, 190) of size (560, 90). Sample a pixel
    # well inside it; alpha must be > 0.
    sample = overlay.surface.get_at((640, 230))
    assert sample.a > 0


def test_result_panel_renders_partial_banner_with_abort_label() -> None:
    """P-deep partial outcomes render the abort_label in the
    sub-line (e.g. 'aborted to Earth orbit after Trans-lunar
    injection'). The overlay version reuses the same logic the
    Ursina banner had."""
    from baris.client.ui_overlay.overlay import PygameOverlay
    from baris.client.ui_overlay.panels import ResultPanel
    overlay = PygameOverlay((1280, 720))
    panel = ResultPanel(
        screen_size=(1280, 720),
        report=_make_launch_report(
            success=False,
            partial=True,
            failed_phase="Trans-lunar injection",
            abort_label="aborted to Earth orbit",
            effective_success=0.55,
        ),
        is_own=True,
        on_continue=lambda: None,
    )
    overlay.add_panel(panel)
    # Should render without crashing; banner pixels visible.
    overlay.render()
    sample = overlay.surface.get_at((640, 230))
    assert sample.a > 0


# -----------------------------------------------------------------------
# Fruit-character data lookups (engine-agnostic parts of FruitCharacter)
# -----------------------------------------------------------------------
def test_known_character_returns_canonical_glyph_and_swatch() -> None:
    """The fruit-character model reads its colour + glyph straight
    from CHARACTER_PORTRAITS. Every brainrot recruit should have
    an entry there; this verifies one well-known name resolves to
    a real swatch (RGB tuple, all values in 0-255)."""
    from baris.state import character_portrait
    glyph, swatch = character_portrait("Bombardiro Crocodilo")
    assert isinstance(glyph, str) and len(glyph) >= 1
    assert isinstance(swatch, tuple) and len(swatch) == 3
    for ch in swatch:
        assert 0 <= ch <= 255


def test_unknown_character_falls_back_to_neutral_swatch() -> None:
    """An astronaut whose name isn't in CHARACTER_PORTRAITS still
    renders — the model just paints a grey '?' fruit. Keeps roster
    refresh from crashing on hand-rolled or migrated saves."""
    from baris.state import character_portrait
    glyph, swatch = character_portrait("Definitely Not A Real Brainrot Name")
    assert glyph == "?"
    assert swatch == (160, 160, 170)


def test_fruit_face_glyph_falls_back_for_non_ascii() -> None:
    """Panda3D's default font lacks glyphs for the brainrot
    portrait emoji, so the 3D fruit body falls back to the first
    letter of the character's name (uppercased). ASCII glyphs
    pass through unchanged."""
    from baris.client3d.character_model import _ascii_face_glyph
    # Emoji portrait → first letter of name.
    assert _ascii_face_glyph("🐊", "Bombardiro Crocodilo") == "B"
    assert _ascii_face_glyph("🦫", "Tralalero Tralala") == "T"
    # ASCII glyph → keep as-is.
    assert _ascii_face_glyph("?", "Unknown Pilot") == "?"
    assert _ascii_face_glyph("X", "X-Pilot") == "X"
    # Empty + nameless astronaut → '?' fallback.
    assert _ascii_face_glyph("", "") == "?"
