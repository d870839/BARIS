"""Concrete OverlayPanel subclasses that the 3D client mounts on
the pygame overlay. As panels migrate off Ursina entities they
land here.

The intent is to share these classes between the 3D client (where
they're the primary UI) and the 2D client (where they replace the
inline `_render_tab_*` methods). For now the 3D client adopts each
panel one at a time as step 3 of the UI refactor lands."""
from __future__ import annotations

import time
from collections.abc import Callable

import pygame

from baris.client.ui_overlay.overlay import OverlayPanel
from baris.client.ui_overlay.palette import (
    BG, BG_DEEP, BORDER, BORDER_HOVER, DIM, FG, GREEN, HIGHLIGHT,
    MUTED, PANEL, PANEL_HOVER, RED,
)
from baris.client.ui_overlay.typography import draw_text, draw_text_centered
from baris.client.ui_overlay.widgets import Button
from baris.state import (
    LaunchReport,
    PHASE_OUTCOME_FAIL,
    PHASE_OUTCOME_PARTIAL,
    PHASE_OUTCOME_PASS,
    character_bio,
    character_portrait,
    phase_outcomes,
)


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


# ----------------------------------------------------------------------
# Launch result panel
# ----------------------------------------------------------------------

PHASE_TICKER_STEP_S = 0.55


class ResultPanel(OverlayPanel):
    """The post-launch debrief: banner + crew/objective details +
    cinematic phase ticker. Read-only except for one Continue
    button.

    First panel to migrate off Ursina entities (step 3 of the UI
    refactor). The Ursina version (panels_action.py:build_result_panel)
    z-fights and wobbles when the camera moves; this version is
    drawn into the pygame overlay surface on a stable 2D HUD layer
    so text stays crisp at any FOV."""

    def __init__(
        self,
        screen_size: tuple[int, int],
        report: LaunchReport,
        is_own: bool,
        on_continue: Callable[[], None],
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.screen_size = screen_size
        self.report = report
        self.is_own = is_own
        self.on_continue = on_continue
        self._clock = clock
        self._start = clock()
        cx = screen_size[0] // 2
        bottom = screen_size[1] - 70
        self.continue_button = Button(
            rect=pygame.Rect(cx - 130, bottom, 260, 42),
            label="Continue",
            key_hint="Space",
        )

    # ------------------------------------------------------------------
    # OverlayPanel hooks
    # ------------------------------------------------------------------
    def is_animating(self) -> bool:
        rows = phase_outcomes(self.report)
        if not rows:
            return False
        elapsed = self._clock() - self._start
        # Keep repainting until every row has had its reveal moment.
        return elapsed < len(rows) * PHASE_TICKER_STEP_S + 0.1

    def handle_event(self, event: pygame.event.Event) -> None:
        if self.continue_button.handle_event(event):
            self.on_continue()
        elif event.type == pygame.KEYDOWN and event.key in (
            pygame.K_SPACE, pygame.K_RETURN, pygame.K_KP_ENTER,
        ):
            self.on_continue()

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------
    def draw(self, surface: pygame.Surface) -> None:
        w, h = self.screen_size
        cx = w // 2

        # Backdrop — full-screen translucent layer so the 3D world
        # behind dims out and the panel reads cleanly.
        backdrop = pygame.Surface((w, h), pygame.SRCALPHA)
        backdrop.fill((4, 6, 14, 220))
        surface.blit(backdrop, (0, 0))

        report = self.report
        # Header
        who = "YOUR MISSION" if self.is_own else f"OPPONENT ({report.side})"
        header_color = HIGHLIGHT if self.is_own else DIM
        draw_text_centered(surface, who, (cx, 70),
                           size=20, color=header_color, bold=True)
        draw_text_centered(surface, report.mission_name.upper(), (cx, 108),
                           size=32, color=FG, bold=True)
        # R-deep — surface the specific unit that flew.
        rocket_line = f"Rocket: {report.rocket}"
        if report.unit_id:
            rocket_line = (
                f"Rocket: {report.rocket}  "
                f"({report.unit_id} @ {report.unit_reliability}%)"
            )
        draw_text_centered(
            surface,
            f"{report.username} [{report.side or '?'}]   {rocket_line}",
            (cx, 148), size=16, color=DIM,
        )

        banner, banner_color, sub = self._banner_for(report)

        banner_rect = pygame.Rect(cx - 280, 190, 560, 90)
        pygame.draw.rect(surface, PANEL, banner_rect, border_radius=10)
        pygame.draw.rect(surface, banner_color, banner_rect, 3, border_radius=10)
        draw_text_centered(surface, banner, banner_rect.center,
                           size=56, color=banner_color, bold=True)
        draw_text_centered(surface, sub, (cx, banner_rect.bottom + 16),
                           size=16, color=DIM)

        # Detail panel
        panel_rect = pygame.Rect(cx - 340, 310, 680, 460)
        pygame.draw.rect(surface, (14, 20, 38), panel_rect, border_radius=8)
        pygame.draw.rect(surface, BORDER, panel_rect, 1, border_radius=8)

        if not report.aborted:
            self._draw_details(surface, panel_rect, report)
            self._draw_phase_ticker(surface, panel_rect, report)
        else:
            draw_text(
                surface, f"Reason: {report.abort_reason}",
                (panel_rect.x + 30, panel_rect.y + 26), size=18, color=FG,
            )

        self.continue_button.draw(surface)

    # ------------------------------------------------------------------
    def _banner_for(
        self, report: LaunchReport,
    ) -> tuple[str, tuple[int, int, int], str]:
        if report.aborted:
            return "MISSION ABORTED", DIM, report.abort_reason or "—"
        if report.success:
            if report.ended_game:
                banner, banner_color = "MOON LANDING", HIGHLIGHT
            else:
                banner, banner_color = "SUCCESS", GREEN
            sub = (
                f"Effective {report.effective_success:.2f} — FIRST!"
                if report.first_claimed
                else f"Effective {report.effective_success:.2f}"
            )
            return banner, banner_color, sub
        if report.partial:
            label = report.abort_label or "aborted"
            if report.failed_phase:
                sub = (
                    f"{label} after {report.failed_phase}  "
                    f"(eff {report.effective_success:.2f})"
                )
            else:
                sub = label
            return "PARTIAL", HIGHLIGHT, sub
        if report.failed_phase:
            sub = (
                f"Lost during {report.failed_phase}  "
                f"(eff {report.effective_success:.2f})"
            )
        else:
            sub = (
                f"Effective {report.effective_success:.2f} — roll did not clear"
            )
        return "FAILURE", RED, sub

    def _draw_details(
        self, surface: pygame.Surface,
        panel_rect: pygame.Rect, report: LaunchReport,
    ) -> None:
        x = panel_rect.x + 30
        y = panel_rect.y + 26
        draw_text(surface, f"Prestige       {report.prestige_delta:+d}",
                  (x, y), size=18, color=FG, bold=True)
        y += 28
        if report.first_claimed:
            draw_text(surface, "  FIRST! bonus applied.",
                      (x, y), size=14, color=HIGHLIGHT)
            y += 22
        draw_text(
            surface,
            f"Reliability    {report.reliability_before}% → {report.reliability_after}%",
            (x, y), size=16, color=FG,
        )
        y += 26
        if report.crew:
            draw_text(surface, f"Crew           {', '.join(report.crew)}",
                      (x, y), size=16, color=FG)
            y += 26
        if report.deaths:
            draw_text(surface, f"KIA            {', '.join(report.deaths)}",
                      (x, y), size=16, color=RED, bold=True)
            y += 26
        if report.budget_cut:
            draw_text(surface, f"Funding cut    {report.budget_cut} MB",
                      (x, y), size=16, color=RED)
            y += 26
        if report.objectives:
            y += 8
            draw_text(surface, "Objectives", (x, y), size=18,
                      color=HIGHLIGHT, bold=True)
            y += 26
            for obj in report.objectives:
                if obj.skipped:
                    line = f"  - {obj.name}: skipped ({obj.skip_reason})"
                    line_color = DIM
                elif obj.ship_lost:
                    line = (f"  - {obj.name}: CATASTROPHIC FAILURE — "
                            f"KIA {', '.join(obj.deaths) or '?'}")
                    line_color = RED
                elif obj.success:
                    line = (f"  - {obj.name}: {obj.performer} succeeded "
                            f"({obj.prestige_delta:+d} prestige)")
                    line_color = GREEN
                elif obj.deaths:
                    line = (f"  - {obj.name}: {', '.join(obj.deaths)} lost "
                            f"({obj.prestige_delta:+d} prestige)")
                    line_color = RED
                else:
                    line = f"  - {obj.name}: failed (no casualties)"
                    line_color = DIM
                draw_text(surface, line, (x, y), size=14, color=line_color)
                y += 20

    def _draw_phase_ticker(
        self, surface: pygame.Surface,
        panel_rect: pygame.Rect, report: LaunchReport,
    ) -> None:
        rows = phase_outcomes(report)
        if not rows:
            return
        elapsed = self._clock() - self._start
        tx = panel_rect.x + 380
        ty = panel_rect.y + 26
        draw_text(surface, "MISSION TIMELINE", (tx, ty),
                  size=18, color=HIGHLIGHT, bold=True)
        ty += 28
        for i, (phase_name, outcome) in enumerate(rows):
            if elapsed < i * PHASE_TICKER_STEP_S:
                break
            if outcome == PHASE_OUTCOME_PASS:
                glyph, line_color = "+", GREEN
            elif outcome == PHASE_OUTCOME_FAIL:
                glyph, line_color = "X", RED
            elif outcome == PHASE_OUTCOME_PARTIAL:
                glyph, line_color = "!", HIGHLIGHT
            else:
                glyph, line_color = "-", DIM
            draw_text(surface, f"{glyph}  {phase_name}", (tx, ty),
                      size=16, color=line_color)
            ty += 24


# ----------------------------------------------------------------------
# Astronaut roster panel
# ----------------------------------------------------------------------

ROSTER_CARD_HEIGHT = 96
ROSTER_CARD_GAP = 10
ROSTER_SCROLL_STEP = 60   # pixels per mouse-wheel notch


class AstroRosterPanel(OverlayPanel):
    """Scrollable browse-the-roster panel.

    Replaces the room-cluttering procedural fruit characters with
    a proper card list: portrait swatch + glyph + name + status +
    skill bars + bio one-liner. Scrollable via mouse wheel and
    PgUp / PgDn / arrow keys. Closes on Escape or the X button.
    """

    def __init__(
        self,
        screen_size: tuple[int, int],
        roster: list,
        on_close: Callable[[], None],
    ) -> None:
        self.screen_size = screen_size
        self.roster = list(roster)
        self.on_close = on_close
        self.scroll = 0
        # Panel geometry — centred, fills most of the screen leaving
        # a margin around the edges so the 3D world peeks through.
        w, h = screen_size
        margin_x = max(60, w // 8)
        margin_y = max(40, h // 12)
        self.panel_rect = pygame.Rect(
            margin_x, margin_y,
            w - 2 * margin_x,
            h - 2 * margin_y,
        )
        self.title_h = 50
        self.list_rect = pygame.Rect(
            self.panel_rect.x + 16,
            self.panel_rect.y + self.title_h + 8,
            self.panel_rect.width - 32,
            self.panel_rect.height - self.title_h - 24,
        )
        self.close_button = Button(
            rect=pygame.Rect(self.panel_rect.right - 80, self.panel_rect.y + 8, 60, 32),
            label="X",
            key_hint="Esc",
        )

    # ------------------------------------------------------------------
    @property
    def _content_height(self) -> int:
        per = ROSTER_CARD_HEIGHT + ROSTER_CARD_GAP
        if not self.roster:
            return 0
        return len(self.roster) * per - ROSTER_CARD_GAP

    @property
    def _max_scroll(self) -> int:
        overflow = self._content_height - self.list_rect.height
        return max(0, overflow)

    def _clamp_scroll(self) -> None:
        if self.scroll < 0:
            self.scroll = 0
        elif self.scroll > self._max_scroll:
            self.scroll = self._max_scroll

    # ------------------------------------------------------------------
    def handle_event(self, event: pygame.event.Event) -> None:
        if self.close_button.handle_event(event):
            self.on_close()
            return
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_ESCAPE,):
                self.on_close()
            elif event.key in (pygame.K_DOWN, pygame.K_PAGEDOWN):
                self.scroll += ROSTER_SCROLL_STEP
                self._clamp_scroll()
            elif event.key in (pygame.K_UP, pygame.K_PAGEUP):
                self.scroll -= ROSTER_SCROLL_STEP
                self._clamp_scroll()
            elif event.key == pygame.K_HOME:
                self.scroll = 0
            elif event.key == pygame.K_END:
                self.scroll = self._max_scroll
        elif event.type == pygame.MOUSEWHEEL:
            # MOUSEWHEEL.y is +1 / -1 per notch on most platforms.
            self.scroll -= event.y * ROSTER_SCROLL_STEP
            self._clamp_scroll()

    # ------------------------------------------------------------------
    def draw(self, surface: pygame.Surface) -> None:
        w, h = self.screen_size
        # Backdrop dims the 3D world behind the panel.
        backdrop = pygame.Surface((w, h), pygame.SRCALPHA)
        backdrop.fill((4, 6, 14, 220))
        surface.blit(backdrop, (0, 0))

        # Panel shell.
        pygame.draw.rect(surface, BG_DEEP, self.panel_rect, border_radius=10)
        pygame.draw.rect(surface, BORDER, self.panel_rect, 2, border_radius=10)
        # Title bar.
        title_bar = pygame.Rect(
            self.panel_rect.x, self.panel_rect.y,
            self.panel_rect.width, self.title_h,
        )
        pygame.draw.rect(surface, PANEL, title_bar,
                         border_top_left_radius=10, border_top_right_radius=10)
        draw_text(
            surface, "ASTRONAUT ROSTER",
            (title_bar.x + 18, title_bar.y + 12),
            size=22, color=HIGHLIGHT, bold=True,
        )
        count_label = f"{len(self.roster)} on the books"
        draw_text(
            surface, count_label,
            (title_bar.x + 280, title_bar.y + 16), size=14, color=DIM,
        )
        self.close_button.draw(surface)

        # Card list — clipped to list_rect so off-edge cards don't
        # bleed into the title bar / close button.
        prev_clip = surface.get_clip()
        surface.set_clip(self.list_rect)
        y = self.list_rect.y - self.scroll
        for astro in self.roster:
            self._draw_card(surface, astro, y)
            y += ROSTER_CARD_HEIGHT + ROSTER_CARD_GAP
        surface.set_clip(prev_clip)

        # Scrollbar (only when there's overflow).
        if self._max_scroll > 0:
            self._draw_scrollbar(surface)

    def _draw_card(self, surface: pygame.Surface, astro, y: int) -> None:
        card_rect = pygame.Rect(
            self.list_rect.x, y,
            self.list_rect.width, ROSTER_CARD_HEIGHT,
        )
        # Skip drawing if entirely above / below the visible area —
        # set_clip handles the visual but skipping spares the work.
        if card_rect.bottom < self.list_rect.y or card_rect.y > self.list_rect.bottom:
            return
        pygame.draw.rect(surface, PANEL, card_rect, border_radius=8)
        pygame.draw.rect(surface, BORDER, card_rect, 1, border_radius=8)

        # Portrait swatch + glyph on the left.
        glyph, swatch = character_portrait(astro.name)
        portrait_size = 64
        portrait_rect = pygame.Rect(
            card_rect.x + 12, card_rect.y + 16,
            portrait_size, portrait_size,
        )
        pygame.draw.rect(surface, swatch, portrait_rect, border_radius=8)
        pygame.draw.rect(surface, BORDER, portrait_rect, 1, border_radius=8)
        draw_text_centered(
            surface, glyph, portrait_rect.center,
            size=40, color=(20, 20, 30), bold=True,
        )

        # Name + status row.
        text_x = portrait_rect.right + 16
        draw_text(
            surface, astro.name, (text_x, card_rect.y + 10),
            size=20, color=FG, bold=True,
        )
        status_label, status_color = _astro_status_label(astro)
        draw_text(
            surface, status_label,
            (text_x, card_rect.y + 34),
            size=14, color=status_color,
        )

        # Skill row.
        skills = [
            ("CAP", astro.capsule),
            ("LM",  astro.lm_pilot),
            ("EVA", astro.eva),
            ("DOC", astro.docking),
            ("END", astro.endurance),
        ]
        sx = text_x
        sy = card_rect.y + 56
        for label, val in skills:
            draw_text(
                surface, f"{label} {val:>3}",
                (sx, sy), size=13, color=FG,
            )
            sx += 70

        # Bio one-liner on the right (if there's room).
        bio = character_bio(astro.name)
        if bio:
            bio_rect = pygame.Rect(
                card_rect.x + portrait_size + 380,
                card_rect.y + 12,
                card_rect.width - portrait_size - 400, 70,
            )
            if bio_rect.width > 60:
                # Truncate gracefully if the bio's longer than the panel.
                clipped = bio if len(bio) < 90 else bio[:87] + "…"
                draw_text(
                    surface, clipped,
                    (bio_rect.x, bio_rect.y), size=13, color=DIM,
                )

    def _draw_scrollbar(self, surface: pygame.Surface) -> None:
        track = pygame.Rect(
            self.list_rect.right + 4, self.list_rect.y,
            8, self.list_rect.height,
        )
        pygame.draw.rect(surface, MUTED, track, border_radius=4)
        # Thumb size proportional to visible / total.
        ratio = self.list_rect.height / max(1, self._content_height)
        thumb_h = max(24, int(track.height * ratio))
        # Thumb position proportional to scroll / max_scroll.
        scroll_ratio = self.scroll / max(1, self._max_scroll)
        thumb_y = track.y + int((track.height - thumb_h) * scroll_ratio)
        thumb = pygame.Rect(track.x, thumb_y, track.width, thumb_h)
        pygame.draw.rect(surface, HIGHLIGHT, thumb, border_radius=4)


def _astro_status_label(astro) -> tuple[str, tuple[int, int, int]]:
    """Pick a single-line status string + colour for the roster card."""
    status = getattr(astro, "status", "active")
    if status == "kia":
        return ("KIA", RED)
    if status == "retired":
        return (f"Retired (mood {astro.mood})", DIM)
    if getattr(astro, "flight_ready", False):
        return (
            f"Ready  mood {astro.mood}  type {astro.compatibility}",
            GREEN,
        )
    reason = getattr(astro, "busy_reason", "")
    return (
        f"{(reason or 'busy').title()}  mood {astro.mood}",
        HIGHLIGHT,
    )
