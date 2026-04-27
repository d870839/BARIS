"""Bridge between the engine-agnostic PygameOverlay and Ursina /
Panda3D's render. Owns a Texture mirror of the overlay surface
and a fullscreen quad on camera.ui that displays it.

camera.ui is Ursina's separate 2D HUD layer — it has its own
orthographic camera that doesn't z-fight with world entities, so
we get a stable composite without any of the perspective-camera
weirdness that motivated the refactor."""
from __future__ import annotations

import pygame
from panda3d.core import Texture, TransparencyAttrib
from ursina import Entity, camera, window

from baris.client.ui_overlay.overlay import PygameOverlay


class OverlayHost:
    """Ursina-side wrapper that drives the PygameOverlay and pushes
    its surface to the GPU each frame."""

    def __init__(self, overlay: PygameOverlay) -> None:
        self.overlay = overlay
        w, h = overlay.size

        self.tex = Texture("baris-overlay")
        self.tex.setup_2d_texture(
            w, h, Texture.T_unsigned_byte, Texture.F_rgba,
        )
        self.tex.set_minfilter(Texture.FT_linear)
        self.tex.set_magfilter(Texture.FT_linear)

        # Fullscreen quad parented to camera.ui. camera.ui covers the
        # screen as (aspect_ratio x 1.0) units of orthographic space:
        # X spans [-aspect/2, +aspect/2], Y spans [-0.5, +0.5]. Older
        # Ursina versions don't expose camera.ui_size, so we derive
        # the values from window.aspect_ratio directly.
        ui_w, ui_h = self._ui_size()
        self.entity = Entity(
            parent=camera.ui,
            model="quad",
            scale=(ui_w, ui_h),
            z=-9,   # render in front of every other camera.ui child
        )
        # Set the texture via Panda3D's NodePath API rather than
        # Ursina's Entity(texture=...) — Ursina's setter expects a
        # filename or its own Texture wrapper, not a raw Panda3D
        # Texture, so we bypass it.
        self.entity.set_texture(self.tex)
        self.entity.set_transparency(TransparencyAttrib.M_alpha)

        # First frame: the overlay's _dirty defaults to True so a
        # one-shot upload happens on the next update().
        self._uploaded_once = False
        # Last forwarded cursor position (overlay-pixel space). Used
        # to dedupe MOUSEMOTION events — without this every frame
        # would post a fresh motion event even when the cursor was
        # stationary, which would dirty the overlay, force a re-
        # render, and re-upload the full surface bytes to the GPU.
        # That's the difference between idle-frame "free" and
        # idle-frame "100MB/s of texture transfer".
        self._last_mouse_xy: tuple[int, int] | None = None

    @staticmethod
    def _ui_size() -> tuple[float, float]:
        """Return (ui_width, ui_height) in Ursina's HUD coordinate
        space — i.e. (aspect_ratio, 1.0). Reads window.aspect_ratio
        on every Ursina version we care about."""
        ui_size = getattr(camera, "ui_size", None)
        if ui_size is not None:
            return float(ui_size[0]), float(ui_size[1])
        # Fallback: derive from window. Some pygame-ce / panda3d
        # combinations expose `aspect_ratio` as a property; if it
        # isn't available, compute from the window size directly.
        aspect = getattr(window, "aspect_ratio", None)
        if aspect is None:
            size = getattr(window, "size", None) or getattr(
                window, "fullscreen_size", (1280, 720),
            )
            aspect = float(size[0]) / max(1.0, float(size[1]))
        return float(aspect), 1.0

    def shutdown(self) -> None:
        """Detach the overlay quad — used when the 3D client tears
        down (e.g. during testing)."""
        if self.entity is not None:
            self.entity.disable()
            self.entity = None  # type: ignore[assignment]

    # ------------------------------------------------------------------
    # Per-frame
    # ------------------------------------------------------------------
    def update(self) -> None:
        """Run one overlay render and, if anything changed, upload
        the new bitmap to the GPU. Called from the 3D client's
        update() each frame."""
        redrew = self.overlay.render()
        if redrew or not self._uploaded_once:
            self._upload_texture()
            self._uploaded_once = True

    def _upload_texture(self) -> None:
        raw = self.overlay.to_rgba_bytes(flip_y=True)
        self.tex.set_ram_image_as(raw, "RGBA")

    # ------------------------------------------------------------------
    # Input forwarding
    # ------------------------------------------------------------------
    def forward_mouse(self) -> None:
        """Sample the current mouse cursor position and forward a
        MOUSEMOTION event to the overlay so panels see hover state.
        Click events go through forward_click below — Ursina raises
        on_click on the host entity, but for the overlay we want
        the underlying mouse event so Buttons can hit-test.

        Two short-circuits, both important for framerate:

        1. If the FirstPersonController has the mouse locked, the
           player is mouse-looking around the world. Each rotation
           still nudges the SDL cursor, which would otherwise
           flood the overlay with motion events, dirty its surface
           every frame, and force a fresh GPU texture upload —
           making look-around feel laggy while WASD-walking stays
           smooth. Bail before doing any work.
        2. Even when the cursor is unlocked, only post if it
           actually moved since last frame (see _last_mouse_xy)."""
        from ursina import mouse  # imported here so test code can
        # stub the engine without importing Ursina at module load.
        if getattr(mouse, "locked", False):
            return
        if mouse.x is None or mouse.y is None:
            return
        px, py = self._mouse_to_pixel(mouse.x, mouse.y)
        if self._last_mouse_xy == (px, py):
            return
        self._last_mouse_xy = (px, py)
        self.overlay.post_mouse_motion((px, py))

    def forward_click(self, button: int = 1, down: bool = True) -> None:
        from ursina import mouse
        if mouse.x is None or mouse.y is None:
            return
        px, py = self._mouse_to_pixel(mouse.x, mouse.y)
        if down:
            self.overlay.post_mouse_down((px, py), button=button)
        else:
            self.overlay.post_mouse_up((px, py), button=button)

    def _mouse_to_pixel(self, mx: float, my: float) -> tuple[int, int]:
        """Translate Ursina's [-aspect/2, +aspect/2] x [-0.5, +0.5]
        mouse coords into pixel space matching the overlay surface.
        Y is flipped so (0, 0) is the top-left of the surface."""
        ui_w, _ = self._ui_size()
        w, h = self.overlay.size
        px = int((mx + ui_w / 2) / ui_w * w)
        py = int((0.5 - my) * h)
        return px, py

    def forward_scroll(self, direction: int) -> None:
        """Forward a mouse-wheel notch (+1 up, -1 down) to the
        overlay as a MOUSEWHEEL event. Ursina's input() raises
        'scroll up' / 'scroll down' as discrete events, so the
        host translates those into pygame's continuous-axis
        MOUSEWHEEL shape."""
        self.overlay.post_event(pygame.event.Event(
            pygame.MOUSEWHEEL, x=0, y=int(direction),
        ))

    def forward_pygame_event(self, event: pygame.event.Event) -> None:
        """Pass-through for callers that already have a pygame event
        in hand (e.g. keyboard events forwarded by hooks). Useful
        when we eventually port the 2D client's text-input handlers."""
        self.overlay.post_event(event)
