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

        # Fullscreen quad parented to camera.ui. camera.ui_size is
        # Ursina's coordinate space for HUD widgets — usually
        # (aspect_ratio, 1.0) so a quad of (aspect, 1) fills the
        # screen.
        ui_w, ui_h = camera.ui_size
        self.entity = Entity(
            parent=camera.ui,
            model="quad",
            scale=(ui_w, ui_h),
            texture=self.tex,
            color=(1, 1, 1, 1),
            z=-9,   # render in front of every other camera.ui child
        )
        self.entity.set_transparency(TransparencyAttrib.M_alpha)

        # First frame: the overlay's _dirty defaults to True so a
        # one-shot upload happens on the next update().
        self._uploaded_once = False

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
        the underlying mouse event so Buttons can hit-test."""
        # Translate Ursina's [-aspect, +aspect] / [-0.5, +0.5] mouse
        # coords into pixel-space matching the overlay surface.
        from ursina import mouse  # imported here so test code can
        # stub the engine without importing Ursina at module load.
        if mouse.x is None or mouse.y is None:
            return
        ui_w, ui_h = camera.ui_size
        # mouse.position is (x, y) in ui coordinates: x in [-aspect/2, +aspect/2],
        # y in [-0.5, +0.5]. Map to pixel (0..size).
        w, h = self.overlay.size
        px = int((mouse.x + ui_w / 2) / ui_w * w)
        py = int((0.5 - mouse.y) * h)   # flip Y so 0 is top
        self.overlay.post_mouse_motion((px, py))

    def forward_click(self, button: int = 1, down: bool = True) -> None:
        from ursina import mouse
        if mouse.x is None or mouse.y is None:
            return
        ui_w, ui_h = camera.ui_size
        w, h = self.overlay.size
        px = int((mouse.x + ui_w / 2) / ui_w * w)
        py = int((0.5 - mouse.y) * h)
        if down:
            self.overlay.post_mouse_down((px, py), button=button)
        else:
            self.overlay.post_mouse_up((px, py), button=button)

    def forward_pygame_event(self, event: pygame.event.Event) -> None:
        """Pass-through for callers that already have a pygame event
        in hand (e.g. keyboard events forwarded by hooks). Useful
        when we eventually port the 2D client's text-input handlers."""
        self.overlay.post_event(event)
