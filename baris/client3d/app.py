"""BarisClient — the Ursina Entity that owns the 3D scene, drives the
network loop, and dispatches panel-open / launch-animation events.

Keeps no game logic of its own; everything flows through the existing
NetClient + server + GameState pipeline."""
from __future__ import annotations

import logging
from typing import Any

from ursina import (
    AmbientLight,
    DirectionalLight,
    Entity,
    Text,
    camera,
    color,
    curve,
    destroy,
    invoke,
    mouse,
    window,
)
from ursina.prefabs.first_person_controller import FirstPersonController

from baris import protocol
from baris.client.net import NetClient
from baris.client3d import launch as launch_scene
from baris.client3d import panels_action, panels_info
from baris.client3d.interior_astro import AstroInterior
from baris.client3d.interior_intel import IntelInterior
from baris.client3d.interior_library import LibraryInterior
from baris.client3d.interior_mc import MCInterior
from baris.client3d.interior_museum import MuseumInterior
from baris.client3d.interior_rd import RDInterior
from baris.state import (
    Architecture,
    GameState,
    LaunchReport,
    MISSIONS_BY_ID,
    MissionId,
    Module,
    ObjectiveId,
    Phase,
    Rocket,
    Side,
    objectives_for,
)

log = logging.getLogger("baris.client3d")


# (id, label, (x, z), roof color, interactive)
# NASA-era roof accents: saturated Space-Race palette against white bodies.
BUILDINGS: tuple[tuple[str, str, tuple[float, float], Any, bool], ...] = (
    ("mc",      "Mission Control",   (0.0,   28.0), color.rgb32(240, 130,  50), True),   # NASA orange
    ("rd",      "R&D Complex",       (0.0,  -28.0), color.rgb32( 60, 150,  90), True),   # lab green
    ("astro",   "Astronaut Complex", (28.0,   0.0), color.rgb32( 40, 100, 200), True),   # sky blue
    ("library", "Library",           (-28.0,  0.0), color.rgb32(200, 170, 110), True),   # archive tan
    ("intel",   "Intelligence",      (20.0, -20.0), color.rgb32(120,  90, 160), True),   # dim purple
    ("museum",  "Museum",            (-20.0, 20.0), color.rgb32(180, 150,  60), True),   # bronze
)

INTERACT_RANGE = 8.0


class BarisClient(Entity):
    def __init__(self, server_url: str, username: str, auto_ready: bool = False) -> None:
        super().__init__()
        self.server_url = server_url
        self.username = username
        self.auto_ready = auto_ready
        self.net = NetClient(server_url)
        self.net.start()

        self.state: GameState | None = None
        self.player_id: str | None = None
        self.joined_sent = False
        self._auto_readied = False

        # Pending-turn selections mirrored from the 2D client semantics.
        self.rd_target: str | None = None     # Rocket.value or Module.value
        self.rd_spend: int = 10
        self.queued_mission: MissionId | None = None
        self.queued_objectives: set[ObjectiveId] = set()
        # Phase O — Astronaut.id values for the queued manned mission.
        # Empty list = auto top-skilled (legacy default).
        self.queued_crew: list[str] = []

        # Launch-sequence playback state.
        self.report_queue: list[LaunchReport] = []
        self.report_idx: int = 0
        self.launch_phase: str = "idle"   # idle | ascend | result
        self._consumed_launch_sig: tuple | None = None

        # Panel tracking.
        self.panel: Entity | None = None
        self.panel_id: str | None = None
        # True once the lobby panel has auto-opened for this game.
        self._lobby_opened = False

        # Interior-walk state: which building the player is currently inside,
        # if any. None = outside in the main facility.
        self.in_interior: str | None = None
        # Remember where the player left the facility from, so exit drops
        # them back on the right side of the building.
        self._exit_return_pos: tuple[float, float, float] | None = None

        self._build_scene()
        self._build_hud()

        # Pre-build each building's interior off to the side. They start
        # hidden; walking into the outdoor building + pressing E swaps
        # the player into the matching room.
        self.interiors: dict[str, Any] = {
            "rd":      RDInterior(origin=(100.0, 0.0, 0.0)),
            "mc":      MCInterior(origin=(200.0, 0.0, 0.0)),
            "astro":   AstroInterior(origin=(100.0, 0.0, 100.0)),
            "library": LibraryInterior(origin=(200.0, 0.0, 100.0)),
            "intel":   IntelInterior(origin=(300.0, 0.0, -100.0)),
            "museum":  MuseumInterior(origin=(-100.0, 0.0, 200.0)),
        }
        # Back-compat shim: existing code that references self.rd_interior
        # continues to work without a big rename.
        self.rd_interior = self.interiors["rd"]

    # ------------------------------------------------------------------
    # Scene
    # ------------------------------------------------------------------
    def _build_scene(self) -> None:
        # Sky via the window clear color — more reliable than Sky(color=...)
        # across Ursina versions, which sometimes ignores the color arg and
        # draws a default texture.
        window.color = color.rgb32(130, 180, 225)
        # Soft ambient so facades don't blow out against the sky; a single
        # directional sun adds side-lit shading without full shadows.
        AmbientLight(color=color.rgba32(70, 75, 85, 255))
        sun = DirectionalLight(shadows=False)
        sun.look_at((0.3, -0.8, 0.4))

        # Ground — concrete apron, with a collider so the FPC doesn't fall
        # through. `texture_scale` tiles the built-in white_cube texture so
        # the eye can pick up movement across the apron.
        Entity(
            model="plane", scale=(160, 1, 160),
            color=color.rgb32(180, 180, 190),
            texture="white_cube", texture_scale=(80, 80),
            collider="box",
        )
        # Far ground ring — slightly tinted desert / scrub so the eye
        # doesn't see the concrete apron's hard edge against the sky.
        # Larger than the apron and a touch lower to avoid z-fighting
        # at the seam.
        Entity(
            model="plane", scale=(360, 1, 360), y=-0.05,
            color=color.rgb32(150, 130, 100),
            texture="white_cube", texture_scale=(40, 40),
        )
        # Central plaza — slightly warmer concrete with a ring of paving.
        Entity(
            model="plane", scale=(26, 1, 26), y=0.02,
            color=color.rgb32(210, 205, 195),
            texture="white_cube", texture_scale=(13, 13),
        )
        # Painted taxi lines from the plaza out to each building. Cardinal
        # paths (N/S/E/W) get rectangular stripes so they read as runways;
        # the two diagonal paths to Intelligence (SE) and Museum (NW) use a
        # short cube-chain so they don't fight with the cardinal lines.
        for (x, z) in ((0, 14), (0, -14), (14, 0), (-14, 0)):
            Entity(
                model="cube",
                position=(x * 0.5, 0.03, z * 0.5),
                scale=(1.0 if z == 0 else 0.5, 0.02, 1.0 if x == 0 else 0.5),
                color=color.rgb32(240, 225, 120),
            )
        # Diagonals — small dashes laid down the line from the plaza edge
        # towards each diagonal building. Five dashes at 4-unit spacing
        # land within the plaza-to-building gap (~14 units).
        for (sign_x, sign_z) in ((1, -1), (-1, 1)):  # SE, NW
            for step in range(1, 6):
                d = step * 2.0
                Entity(
                    model="cube",
                    position=(sign_x * d, 0.03, sign_z * d),
                    scale=(0.5, 0.02, 0.5),
                    color=color.rgb32(240, 225, 120),
                )

        self.buildings: dict[str, Entity] = {}
        for bid, label, (x, z), roof, interactive in BUILDINGS:
            # White NASA-facility body.
            body = Entity(
                model="cube", position=(x, 3, z),
                scale=(7, 6, 7), color=color.rgb32(245, 245, 248),
            )
            body._bid = bid
            body._interactive = interactive
            self.buildings[bid] = body
            # Roof slab — saturated accent so each building is identifiable
            # at a glance from across the complex.
            Entity(
                parent=body, model="cube",
                scale=(1.05, 0.18, 1.05),
                y=0.5, color=roof,
            )
            # Trim strip between roof and body (a faint shadow line).
            Entity(
                parent=body, model="cube",
                scale=(1.02, 0.03, 1.02),
                y=0.4, color=color.rgb32(180, 185, 200),
            )
            # Window strips — two horizontal bands of dark rectangles on
            # each of the four facades, suggesting a multi-storey building
            # without modelling each window individually. Local space:
            # front face is z=-0.5, back z=+0.5, sides x=±0.5; bands sit
            # one above + one below the visual midline.
            for band_y in (0.18, -0.18):
                for face_z in (-0.505, 0.505):
                    Entity(
                        parent=body, model="cube",
                        position=(0, band_y, face_z),
                        scale=(0.78, 0.06, 0.005),
                        color=color.rgb32(45, 60, 85),
                    )
                for face_x in (-0.505, 0.505):
                    Entity(
                        parent=body, model="cube",
                        position=(face_x, band_y, 0),
                        scale=(0.005, 0.06, 0.78),
                        color=color.rgb32(45, 60, 85),
                    )
            # Tiny ground-level doorway stripe on the player-facing side.
            Entity(
                parent=body, model="cube",
                scale=(0.25, 0.4, 0.01),
                y=-0.35, z=-0.505,
                color=color.rgb32(60, 70, 90),
            )
            # Floating sign. In Ursina's world-space, text scale is meters,
            # so we keep it small — a tiny plate above the roof instead of
            # a billboard that swallows the building. No `background=True`
            # because that draws a huge world-space quad around the text.
            Text(
                text=label, parent=body,
                y=0.75, scale=1.8,
                origin=(0, 0), billboard=True,
                color=color.rgb32(30, 35, 45),
            )
            # Per-building silhouette accessory so each one is memorable
            # by shape, not just roof colour. All world-space so collider
            # boxes around the body stay simple.
            self._add_building_silhouette(bid, x, z)
        # Big central SUBMIT TURN button on the plaza. Pedestal + cap +
        # a billboard label. The cap's colour is swapped every frame by
        # _tick_submit_button() to signal lock state.
        submit_pos = (0.0, 0.0, 6.0)   # a bit north of spawn so it's in view
        Entity(
            model="cube",
            position=(submit_pos[0], 0.7, submit_pos[2]),
            scale=(1.6, 1.4, 1.6),
            color=color.rgb32(65, 70, 85),
            collider="box",
        )
        self.submit_button_cap = Entity(
            model="cube",
            position=(submit_pos[0], 1.5, submit_pos[2]),
            scale=(1.2, 0.25, 1.2),
            color=color.rgb32(90, 200, 110),
        )
        self.submit_button_cap._rest_y = self.submit_button_cap.y
        self.submit_button_pos = submit_pos
        Text(
            text="SUBMIT TURN",
            position=(submit_pos[0], 2.8, submit_pos[2]),
            scale=6, origin=(0, 0),
            billboard=True,
            color=color.rgb32(240, 240, 245),
        )

        # Plaza ambience — perimeter lamp posts at the four corners of the
        # 26x26 plaza, and a pair of ceremonial flagpoles flanking the
        # SUBMIT TURN pedestal (USA blue + USSR red, for joint-mission
        # flavour). All decorative; no gameplay effect.
        for (lx, lz) in ((10, 10), (-10, 10), (10, -10), (-10, -10)):
            Entity(  # pole
                model="cube",
                position=(lx, 1.7, lz),
                scale=(0.16, 3.4, 0.16),
                color=color.rgb32(70, 70, 80),
            )
            Entity(  # arm extending toward the plaza
                model="cube",
                position=(lx * 0.9, 3.3, lz * 0.9),
                scale=(0.5, 0.08, 0.5),
                color=color.rgb32(70, 70, 80),
            )
            Entity(  # lamp head
                model="cube",
                position=(lx * 0.85, 3.1, lz * 0.85),
                scale=(0.45, 0.28, 0.45),
                color=color.rgb32(240, 230, 160),
            )
        for (fx, fz, flag_color) in (
            (-2.5, 6.0, color.rgb32(80, 140, 220)),    # USA blue
            ( 2.5, 6.0, color.rgb32(220, 90,  90)),    # USSR red
        ):
            Entity(  # pole
                model="cube",
                position=(fx, 2.5, fz),
                scale=(0.08, 5.0, 0.08),
                color=color.rgb32(220, 220, 230),
            )
            Entity(  # flag
                model="cube",
                position=(fx + 0.55, 4.4, fz),
                scale=(1.0, 0.6, 0.02),
                color=flag_color,
            )

        # Three launch pads laid out west-to-east north of Mission Control.
        # Pad A (centre) carries the active rocket silhouette + animates
        # liftoff during the launch sequence; B and C are visual siblings
        # whose status markers live-recolour to mirror their pad state.
        self.pad = launch_scene.build_launch_pad(
            launch_scene.PAD_POSITION, pad_label="A",
        )
        self.pad_b = launch_scene.build_launch_pad(
            launch_scene.PAD_B_POSITION, pad_label="B",
        )
        self.pad_c = launch_scene.build_launch_pad(
            launch_scene.PAD_C_POSITION, pad_label="C",
        )
        self.rockets: dict[str, Entity] = {}
        self.flames: dict[str, Entity] = {}
        for cls in ("Light", "Medium", "Heavy"):
            rocket = launch_scene.build_rocket(cls)
            flame = launch_scene.build_exhaust_flame(rocket)
            rocket.enabled = False
            self.rockets[cls] = rocket
            self.flames[cls] = flame
        self.current_rocket_class = "Light"
        self.rockets["Light"].enabled = True

        self.player = FirstPersonController(position=(0, 2, -5), speed=8)

        self._build_opponent_facility(origin=(140.0, 0.0, 0.0))

        self._add_horizon_props()

    def _add_horizon_props(self) -> None:
        """Distant background props so the world doesn't end at the
        concrete apron. Everything here is far enough out (radius ≥80)
        that it reads as horizon flavour, never something the player
        walks into. No colliders — pure visual."""
        import math
        # Ring of low rolling hills around the perimeter. Spaced
        # roughly evenly with a touch of jitter so they don't feel
        # mechanically placed; heights step gently so the silhouette
        # is varied.
        hill_color_a = color.rgb32(95, 110, 80)
        hill_color_b = color.rgb32(115, 125, 95)
        radius = 110.0
        for i in range(36):
            theta = (i / 36) * 2 * math.pi
            r = radius + (4.0 if i % 3 == 0 else 0.0)
            hx = math.cos(theta) * r
            hz = math.sin(theta) * r
            hill_h = 6.0 + (3.0 if i % 4 == 0 else 0.0) + (2.0 if i % 7 == 0 else 0.0)
            hill_w = 28.0
            Entity(
                model="sphere",
                position=(hx, hill_h * 0.2, hz),
                scale=(hill_w, hill_h, hill_w),
                color=hill_color_a if i % 2 == 0 else hill_color_b,
            )
        # A water tower out past the far end of the launch pads — a
        # familiar Cape Canaveral landmark in silhouette.
        tower_x, tower_z = 35.0, 70.0
        Entity(  # legs (4)
            model="cube",
            position=(tower_x - 1.5, 5.0, tower_z - 1.5),
            scale=(0.3, 10.0, 0.3),
            color=color.rgb32(170, 170, 180),
        )
        Entity(
            model="cube",
            position=(tower_x + 1.5, 5.0, tower_z - 1.5),
            scale=(0.3, 10.0, 0.3),
            color=color.rgb32(170, 170, 180),
        )
        Entity(
            model="cube",
            position=(tower_x - 1.5, 5.0, tower_z + 1.5),
            scale=(0.3, 10.0, 0.3),
            color=color.rgb32(170, 170, 180),
        )
        Entity(
            model="cube",
            position=(tower_x + 1.5, 5.0, tower_z + 1.5),
            scale=(0.3, 10.0, 0.3),
            color=color.rgb32(170, 170, 180),
        )
        Entity(  # tank
            model="sphere",
            position=(tower_x, 11.0, tower_z),
            scale=(5.0, 4.0, 5.0),
            color=color.rgb32(220, 220, 230),
        )
        # A distant antenna farm to the south-west — three masts of
        # varying height suggesting a tracking-station outpost.
        for (mx, mz, h) in (
            (-78, -50, 18.0),
            (-72, -44, 14.0),
            (-66, -52, 11.0),
        ):
            Entity(
                model="cube",
                position=(mx, h / 2, mz),
                scale=(0.6, h, 0.6),
                color=color.rgb32(170, 170, 180),
            )
            Entity(  # warning light at top
                model="cube",
                position=(mx, h + 0.3, mz),
                scale=(0.4, 0.4, 0.4),
                color=color.rgb32(220, 70, 70),
            )
        # A long, low hangar building visible past the east buildings
        # — corrugated-roof, vaguely Cold-War-era.
        Entity(
            model="cube",
            position=(70, 4.0, -8),
            scale=(20.0, 8.0, 10.0),
            color=color.rgb32(195, 190, 180),
        )
        Entity(  # roof slab
            model="cube",
            position=(70, 8.1, -8),
            scale=(20.4, 0.3, 10.4),
            color=color.rgb32(140, 135, 125),
        )
        Entity(  # a few horizontal trim bands
            model="cube",
            position=(70, 4.5, -2.95),
            scale=(20.2, 0.15, 0.05),
            color=color.rgb32(140, 135, 125),
        )
        Entity(
            model="cube",
            position=(70, 3.0, -2.95),
            scale=(20.2, 0.15, 0.05),
            color=color.rgb32(140, 135, 125),
        )

    def _build_opponent_facility(
        self, origin: tuple[float, float, float],
    ) -> None:
        """Mirror of the player's hub placed far east at `origin`. Buildings
        and pads only, no colliders — the player can walk towards it but
        nothing here is interactive. Pad status markers + deck tints are
        live-driven by _tick_pad_status() from the OPPONENT'S pads, so
        you can see the goat land when you fire a Catapult Calamity."""
        ox, _oy, oz = origin
        # Six buildings in the same star-pattern as the player's hub.
        opp_layout = (
            ("mc",      ( 0.0,  28.0), color.rgb32(240, 130,  50)),
            ("rd",      ( 0.0, -28.0), color.rgb32( 60, 150,  90)),
            ("astro",   (28.0,   0.0), color.rgb32( 40, 100, 200)),
            ("library", (-28.0,  0.0), color.rgb32(200, 170, 110)),
            ("intel",   (20.0, -20.0), color.rgb32(120,  90, 160)),
            ("museum",  (-20.0, 20.0), color.rgb32(180, 150,  60)),
        )
        for bid, (bx, bz), roof in opp_layout:
            body = Entity(
                model="cube", position=(ox + bx, 3, oz + bz),
                scale=(7, 6, 7), color=color.rgb32(245, 245, 248),
            )
            Entity(
                parent=body, model="cube",
                scale=(1.05, 0.18, 1.05),
                y=0.5, color=roof,
            )
            Entity(
                parent=body, model="cube",
                scale=(1.02, 0.03, 1.02),
                y=0.4, color=color.rgb32(180, 185, 200),
            )
        # A small "OPPONENT" sign so the player isn't confused which
        # facility they're looking at.
        Text(
            text="OPPONENT",
            position=(ox, 9.5, oz),
            scale=12, origin=(0, 0),
            billboard=True,
            color=color.rgb32(220, 90, 90),
        )
        # Three simple opponent pad slabs. We don't bother with the
        # full gantry — at this distance the legs would just clutter
        # the silhouette. Each pad is a deck slab + a status marker
        # cube on top, recoloured by _tick_pad_status() each frame.
        opp_pad_visuals: list[Entity] = []
        for i, (px, pz) in enumerate(
            ((-12.0, 40.0), (0.0, 40.0), (12.0, 40.0))
        ):
            deck = Entity(
                model="cube",
                position=(ox + px, 0.3, oz + pz),
                scale=(5, 0.6, 5),
                color=color.rgb32(165, 165, 175),
            )
            deck._deck_color = deck.color
            deck._status_marker = Entity(
                model="cube",
                position=(ox + px, 0.65, oz + pz - 1.6),
                scale=(1.6, 0.08, 0.4),
                color=color.rgb32(120, 200, 120),
            )
            Text(
                text=f"PAD {chr(ord('A') + i)}",
                position=(ox + px, 1.4, oz + pz),
                scale=3.5, origin=(0, 0),
                billboard=True,
                color=color.rgb32(220, 90, 90),
            )
            opp_pad_visuals.append(deck)
        self.opponent_pads = opp_pad_visuals

    def _add_building_silhouette(self, bid: str, x: float, z: float) -> None:
        """Per-building decorative geometry — antennas, domes, columns,
        portico — so each building has a memorable shape, not just a
        coloured roof. Built in world space relative to the building's
        ground footprint at (x, z); body itself is 7×6×7 centred at y=3."""
        # Vector from origin to building gives us "back" (away from plaza)
        # vs "front" (toward plaza). Most decorative bits go on the back
        # so they don't block the doorway, except entrance pillars which
        # are explicitly out front.
        if bid == "mc":
            # Mission Control — tall radio-tower mast with a satellite
            # dish, behind the building (NASA tracking-station look).
            mast_x = x + 0.0
            mast_z = z + 4.5  # behind the building (further from origin)
            for y_seg in (7.0, 9.5, 12.0):
                Entity(
                    model="cube",
                    position=(mast_x, y_seg, mast_z),
                    scale=(0.3, 2.0, 0.3),
                    color=color.rgb32(190, 195, 210),
                )
            # Lattice cross-bracing
            for y_seg in (8.0, 10.5):
                Entity(
                    model="cube",
                    position=(mast_x, y_seg, mast_z),
                    scale=(0.5, 0.06, 0.06),
                    color=color.rgb32(170, 175, 190),
                )
            # Dish at the top
            Entity(
                model="sphere",
                position=(mast_x, 13.5, mast_z),
                scale=(1.4, 0.5, 1.4),
                color=color.rgb32(230, 230, 240),
            )
            # Red aircraft-warning light
            Entity(
                model="cube",
                position=(mast_x, 14.1, mast_z),
                scale=(0.18, 0.18, 0.18),
                color=color.rgb32(220, 60, 60),
            )
        elif bid == "rd":
            # R&D Complex — three exhaust stacks on the roof, evoking
            # an industrial / propellant test stand. Base sits clearly
            # above the roof slab top (~y=6.6) so the stacks don't dip
            # into the body geometry.
            for dx in (-1.8, 0.0, 1.8):
                Entity(
                    model="cube",
                    position=(x + dx, 7.9, z + 2.0),
                    scale=(0.6, 2.4, 0.6),
                    color=color.rgb32(155, 155, 165),
                )
                # Black soot tip
                Entity(
                    model="cube",
                    position=(x + dx, 9.2, z + 2.0),
                    scale=(0.7, 0.15, 0.7),
                    color=color.rgb32(45, 45, 50),
                )
        elif bid == "astro":
            # Astronaut Complex — half-dome on the roof, evoking a
            # planetarium / centrifuge training building. Centre sits
            # one full radius above the roof slab so the lower
            # hemisphere doesn't penetrate the body.
            Entity(
                model="sphere",
                position=(x, 8.4, z),
                scale=(5.5, 2.6, 5.5),
                color=color.rgb32(70, 130, 220),
            )
            # Antenna spire
            Entity(
                model="cube",
                position=(x, 10.4, z),
                scale=(0.1, 1.4, 0.1),
                color=color.rgb32(200, 200, 215),
            )
        elif bid == "library":
            # Library — four pillars + a stepped portico in front.
            front_z = z + 4.0  # plaza side (origin side)
            Entity(  # entrance steps
                model="cube",
                position=(x, 0.15, front_z),
                scale=(6.0, 0.3, 1.4),
                color=color.rgb32(220, 215, 200),
            )
            for px in (-2.5, -0.85, 0.85, 2.5):
                Entity(  # column
                    model="cube",
                    position=(x + px, 2.5, front_z),
                    scale=(0.5, 4.7, 0.5),
                    color=color.rgb32(235, 230, 215),
                )
                # Capital
                Entity(
                    model="cube",
                    position=(x + px, 4.95, front_z),
                    scale=(0.7, 0.15, 0.7),
                    color=color.rgb32(220, 215, 200),
                )
            # Architrave — horizontal beam across the columns
            Entity(
                model="cube",
                position=(x, 5.2, front_z),
                scale=(6.4, 0.4, 0.7),
                color=color.rgb32(225, 220, 205),
            )
        elif bid == "intel":
            # Intelligence — radar dome (sphere) + a satellite dish that
            # sits on the roof, not penetrating it.
            Entity(
                model="sphere",
                position=(x, 7.5, z + 1.6),
                scale=(2.4, 1.2, 2.4),
                color=color.rgb32(220, 215, 230),
            )
            # Small antenna mast on top of the dome
            Entity(
                model="cube",
                position=(x, 8.7, z + 1.6),
                scale=(0.12, 1.2, 0.12),
                color=color.rgb32(190, 190, 210),
            )
            # Roof-mounted satellite dish (clear of the body)
            Entity(
                model="sphere",
                position=(x - 1.8, 7.6, z - 1.2),
                scale=(1.6, 0.4, 1.6),
                color=color.rgb32(230, 225, 240),
            )
        elif bid == "museum":
            # Museum — long, low-profile stone facade with a bronze sign
            # over a centred entrance. Evokes a Smithsonian wing.
            front_z = z - 4.0  # plaza side for this NW-positioned building
            Entity(  # broad entrance steps
                model="cube",
                position=(x, 0.2, front_z),
                scale=(8.0, 0.4, 1.6),
                color=color.rgb32(220, 200, 160),
            )
            # Two squat entrance pillars
            for px in (-2.0, 2.0):
                Entity(
                    model="cube",
                    position=(x + px, 2.0, front_z),
                    scale=(0.7, 3.7, 0.7),
                    color=color.rgb32(230, 215, 175),
                )
            # Big bronze sign over the doorway
            Entity(
                model="cube",
                position=(x, 4.2, front_z + 0.05),
                scale=(4.5, 1.0, 0.1),
                color=color.rgb32(180, 150, 60),
            )
            Text(
                text="MUSEUM",
                position=(x, 4.2, front_z - 0.06),
                scale=4.5, origin=(0, 0),
                color=color.rgb32(60, 50, 30),
            )

    def _build_hud(self) -> None:
        self.status_text = Text(
            text="Connecting…",
            position=(-0.88, 0.47), scale=1.05,
            parent=camera.ui, color=color.white,
            background=True,
            background_color=color.rgba32(0, 0, 0, 130),
        )
        self.prompt_text = Text(
            text="", position=(0, -0.32),
            origin=(0, 0), scale=1.8,
            parent=camera.ui, color=color.yellow,
        )

    # ------------------------------------------------------------------
    # Ursina hooks
    # ------------------------------------------------------------------
    def update(self) -> None:
        self._pump_network()
        self._update_prompt()
        self._update_pad_rocket()
        self._tick_submit_button()
        self._tick_pad_status()
        # Once the player has committed the turn, there's nothing useful
        # to do inside a room — kick them back out so they see the rocket
        # + submit lamp and can't tap the physical buttons.
        me = self.me()
        if me is not None and me.turn_submitted and self.in_interior is not None:
            self._exit_interior()
        # Live-sync whichever interior is currently visible.
        if self.in_interior is not None:
            interior = self.interiors[self.in_interior]
            if self.in_interior == "rd":
                interior.sync_state(self.me(), self.rd_target, self.rd_spend)
            elif self.in_interior == "mc":
                interior.sync_state(self.me(), self.state, self)
            else:
                interior.sync_state(self.me(), self.state)

    _SUBMIT_RANGE = 3.0

    def _tick_submit_button(self) -> None:
        """Recolour the big plaza button so the player can see at a glance
        whether it's armed (green), disabled while waiting (grey), or the
        game is not in a submittable state (dim red)."""
        cap = self.submit_button_cap
        if self.state is None or self.state.phase != Phase.PLAYING:
            cap.color = color.rgb32(120, 60, 60)
            return
        me = self.me()
        if me is None or me.turn_submitted:
            cap.color = color.rgb32(110, 115, 125)
            return
        cap.color = color.rgb32(90, 200, 110)

    def _tick_pad_status(self) -> None:
        """Light each pad's status marker so a player walking by can read
        the state of A / B / C without opening Mission Control:
          * green  — idle, ready to accept a launch.
          * amber  — a launch is scheduled and will fly next turn.
          * red    — pad is damaged, repair countdown still running.
        Also tints the deck red for damaged pads, and spawns a brief
        flame puff whenever a pad transitions from undamaged → damaged
        so sabotage hits feel kinetic on both sides of the apron."""
        if self.state is None or self.state.phase != Phase.PLAYING:
            return
        me = self.me()
        if me is None:
            return
        if not hasattr(self, "_prev_pad_damage"):
            self._prev_pad_damage: dict[tuple[str, int], bool] = {}
        pad_visuals = (self.pad, self.pad_b, self.pad_c)
        for i, (pad_data, visual) in enumerate(zip(me.pads, pad_visuals)):
            self._maybe_spawn_pad_puff(("me", i), pad_data, visual)
            if pad_data.damaged:
                visual._status_marker.color = color.rgb32(220, 80, 80)
                visual.color = color.rgb32(120, 80, 80)
            elif pad_data.scheduled_launch is not None:
                visual._status_marker.color = color.rgb32(240, 200, 90)
                visual.color = visual._deck_color
            else:
                visual._status_marker.color = color.rgb32(110, 200, 120)
                visual.color = visual._deck_color
        # Mirror the OPPONENT'S pad state onto the far-east silhouette
        # so the player sees their sabotage land. Same colour scheme
        # so the legend stays consistent across both bases.
        opp = self.state.other_player(me.player_id) if self.state else None
        if opp is not None and getattr(self, "opponent_pads", None):
            for i, (pad_data, visual) in enumerate(
                zip(opp.pads, self.opponent_pads)
            ):
                self._maybe_spawn_pad_puff(("opp", i), pad_data, visual)
                if pad_data.damaged:
                    visual._status_marker.color = color.rgb32(220, 80, 80)
                    visual.color = color.rgb32(120, 80, 80)
                elif pad_data.scheduled_launch is not None:
                    visual._status_marker.color = color.rgb32(240, 200, 90)
                    visual.color = visual._deck_color
                else:
                    visual._status_marker.color = color.rgb32(110, 200, 120)
                    visual.color = visual._deck_color

    def _maybe_spawn_pad_puff(
        self, key: tuple[str, int], pad_data: Any, visual: Entity,
    ) -> None:
        """Compare current vs previously-seen damage state for `key`
        and spawn a transient flame ball when it just flipped on."""
        was_damaged = self._prev_pad_damage.get(key, False)
        self._prev_pad_damage[key] = pad_data.damaged
        if pad_data.damaged and not was_damaged:
            self._spawn_pad_damage_puff(visual)

    def _spawn_pad_damage_puff(self, visual: Entity) -> None:
        """Bright orange ball that quickly shrinks to nothing and
        self-destroys. Two seconds total — long enough to read across
        the apron, short enough not to clutter the scene if multiple
        sabotages chain."""
        flame = Entity(
            model="sphere",
            position=(visual.x, visual.y + 1.5, visual.z),
            scale=(3.0, 3.0, 3.0),
            color=color.rgb32(245, 150, 50),
        )
        flame.animate_scale(0.05, duration=1.4)
        invoke(destroy, flame, delay=1.6)

    def _near_submit_button(self) -> bool:
        sx, _, sz = self.submit_button_pos
        px, _, pz = self.player.position
        return ((px - sx) ** 2 + (pz - sz) ** 2) ** 0.5 < self._SUBMIT_RANGE

    def _press_submit_button(self) -> None:
        """Big-button equivalent of the Mission Control panel's SUBMIT."""
        if self._turn_locked():
            return
        cap = self.submit_button_cap
        cap.animate_y(cap._rest_y - 0.1, duration=0.08)
        invoke(setattr, cap, "y", cap._rest_y, delay=0.18)
        self.mc_submit_turn()

    def _update_pad_rocket(self) -> None:
        """Swap which rocket silhouette sits on the pad based on what the
        player is about to launch. Priority: queued mission's effective
        rocket > already-scheduled launch's frozen rocket_class > current
        R&D target > whatever was already showing. No-op while a launch
        animation is actually playing."""
        if self.launch_phase != "idle":
            return
        desired = None
        me = self.me()
        if self.queued_mission is not None and me is not None:
            from baris.resolver import effective_rocket
            mission = MISSIONS_BY_ID[self.queued_mission]
            desired = effective_rocket(me, mission).value
        elif me is not None and me.scheduled_launch is not None:
            desired = me.scheduled_launch.rocket_class
        elif self.rd_target in ("Light", "Medium", "Heavy"):
            desired = self.rd_target
        if desired is None or desired == self.current_rocket_class:
            return
        for cls, rkt in self.rockets.items():
            rkt.enabled = (cls == desired)
        self.current_rocket_class = desired

    def input(self, key: str) -> None:
        if self.panel_id == "result" and key in ("space", "enter", "escape"):
            self.advance_result_panel()
            return
        if self.launch_phase == "ascend" and key in ("space", "enter"):
            self._skip_ascend()
            return
        if key == "escape":
            if self.panel_id not in (None, "lobby"):
                self.close_current_panel()
                return
            if self.in_interior is not None:
                self._exit_interior()
            return
        if key == "1" and self.panel_id == "lobby":
            self.lobby_pick_side("USA")
            return
        if key == "2" and self.panel_id == "lobby":
            self.lobby_pick_side("USSR")
            return
        if key == "enter" and self.panel_id == "lobby":
            self.lobby_toggle_ready()
            return
        if key == "enter" and self.panel_id == "mc":
            self.mc_submit_turn()
            return
        if key == "e" and self.panel is None:
            # Inside an interior: press physical buttons or walk out.
            if self.in_interior is not None:
                self._press_interior_button()
                return
            # Outside: check the big central submit pedestal first so it
            # always wins proximity even if you're near the plaza edge of
            # a building.
            if self._near_submit_button():
                self._press_submit_button()
                return
            # Approaching a building enters its walk-in interior.
            nearby = self._nearby_interactive_building()
            if nearby is None:
                return
            self._enter_interior(nearby._bid)

    # ------------------------------------------------------------------
    # Network
    # ------------------------------------------------------------------
    def _pump_network(self) -> None:
        if not self.net.connected.is_set():
            return
        if not self.joined_sent:
            self.net.send(protocol.JOIN, username=self.username)
            self.joined_sent = True
            self.status_text.text = "Joining…"
        for msg in self.net.drain_inbound():
            self._handle_message(msg)

    def _handle_message(self, msg: dict) -> None:
        mtype = msg.get("type")
        if mtype == protocol.JOINED:
            self.player_id = msg["player_id"]
            self.state = GameState.from_dict(msg["state"])
        elif mtype == protocol.STATE:
            self.state = GameState.from_dict(msg["state"])
            if self.auto_ready and not self._auto_readied:
                me = self.me()
                if me is not None and self.state.phase == Phase.LOBBY and not me.ready:
                    self._auto_readied = True
                    self.net.send(protocol.READY)
            self._maybe_auto_open_lobby()
            self._maybe_start_launch_sequence()
            self._maybe_close_lobby_on_start()
        elif mtype == protocol.ERROR:
            self.status_text.text = f"Error: {msg.get('message', '?')}"
        self._refresh_status()

    def _refresh_status(self) -> None:
        if self.state is None:
            return
        me = self.me()
        phase = self.state.phase.value
        if me is None:
            self.status_text.text = f"[{phase}] (no player)"
            return
        side = me.side.value if me.side else "?"
        turn = "submitted" if me.turn_submitted else "your turn"
        self.status_text.text = (
            f"[{phase.upper()}]  {self.state.season.value} {self.state.year}  |  "
            f"{me.username} [{side}]  Budget {me.budget} MB  "
            f"Prestige {me.prestige}  ({turn})"
        )

    def me(self):
        if self.state is None or self.player_id is None:
            return None
        return self.state.find_player(self.player_id)

    def _turn_locked(self) -> bool:
        """True once the player has submitted this turn. Every action that
        mutates pending selections should early-out while this is set so
        the player can't queue changes mid-resolve."""
        me = self.me()
        if self.state is None or me is None:
            return True
        if self.state.phase != Phase.PLAYING:
            return True
        return me.turn_submitted

    _INTERIOR_LABELS = {
        "rd":      "R&D Complex",
        "mc":      "Mission Control",
        "astro":   "Astronaut Complex",
        "library": "Library",
        "intel":   "Intelligence Office",
        "museum":  "Museum",
    }

    def _prompt_for_interior_button(self, bid: str | None) -> str:
        """Human-readable hint for the currently-closest interior button."""
        room_label = self._INTERIOR_LABELS.get(self.in_interior or "", "")
        if bid is None:
            if self.in_interior in ("astro", "library", "intel", "museum"):
                return f"Inside the {room_label} — [Esc] walks out"
            return "Walk up to a button and press E"
        if bid == "exit":
            return f"[E] Exit {room_label}"
        if bid == "scrub":
            me = self.me()
            if me is not None and me.scheduled_launch is not None:
                return "[E] SCRUB scheduled launch (refund ~half assembly)"
            return "Nothing to scrub"
        if bid == "training":
            return "[E] Open Advanced Training console"
        if bid == "recruit":
            return "[E] Open Recruitment console"
        if bid == "intel":
            from baris.state import INTEL_COST
            return f"[E] Request intelligence report ({INTEL_COST} MB)"
        if bid == "sabotage":
            return "[E] Open DIRTY TRICKS — sabotage cards"
        if bid.startswith("target:"):
            return f"[E] Set R&D target: {bid.split(':', 1)[1]}"
        if bid == "spend_plus":
            return "[E] +5 MB"
        if bid == "spend_minus":
            return "[E] -5 MB"
        if bid == "mc_panel":
            return "[E] Open MISSION SELECT — pick mission / objectives / arch"
        return ""

    # ------------------------------------------------------------------
    # Proximity / prompts
    # ------------------------------------------------------------------
    def _nearby_interactive_building(self) -> Entity | None:
        if self.state is None or self.state.phase != Phase.PLAYING:
            return None
        px, _, pz = self.player.position
        closest: Entity | None = None
        closest_d = INTERACT_RANGE
        for ent in self.buildings.values():
            if not ent._interactive:
                continue
            d = ((px - ent.x) ** 2 + (pz - ent.z) ** 2) ** 0.5
            if d < closest_d:
                closest_d = d
                closest = ent
        return closest

    def _update_prompt(self) -> None:
        if self.panel is not None or self.launch_phase != "idle":
            self.prompt_text.text = ""
            return
        me = self.me()
        if me is None or self.state is None:
            return
        if self.state.phase == Phase.LOBBY:
            self.prompt_text.text = "Lobby open — pick a side and ready up"
            return
        # Locked: while the turn is already submitted, everything reads as
        # waiting; buttons still render hover but actions are guarded.
        if me.turn_submitted:
            self.prompt_text.text = "Turn submitted — waiting for opponent…"
            return
        # Interior prompts override the outdoor proximity prompt — inside a
        # walk-in building, we surface the nearest physical button instead.
        if self.in_interior is not None:
            interior = self.interiors[self.in_interior]
            px, _, pz = self.player.position
            bid = interior.nearby_button((px, pz))
            self.prompt_text.text = self._prompt_for_interior_button(bid)
            return
        if self._near_submit_button():
            self.prompt_text.text = "[E] SUBMIT TURN"
            return
        nearby = self._nearby_interactive_building()
        if nearby is not None:
            labels = {b[0]: b[1] for b in BUILDINGS}
            self.prompt_text.text = f"[E] Enter {labels[nearby._bid]}"
        else:
            self.prompt_text.text = ""

    # ------------------------------------------------------------------
    # Panel management
    # ------------------------------------------------------------------
    def _open_panel(self, panel_id: str, *, report: LaunchReport | None = None) -> None:
        self._close_panel_silent()
        self.panel_id = panel_id
        if panel_id == "lobby":
            self.panel = panels_info.build_lobby_panel(self, camera.ui)
        elif panel_id == "mc":
            self.panel = panels_action.build_mc_panel(self, camera.ui)
        elif panel_id == "rd":
            self.panel = panels_action.build_rd_panel(self, camera.ui)
        elif panel_id == "astro":
            self.panel = panels_info.build_astro_panel(self, camera.ui)
        elif panel_id == "library":
            self.panel = panels_info.build_library_panel(self, camera.ui)
        elif panel_id == "training":
            self.panel = panels_info.build_training_panel(self, camera.ui)
        elif panel_id == "recruit":
            self.panel = panels_info.build_recruit_panel(self, camera.ui)
        elif panel_id == "sabotage":
            self.panel = panels_info.build_sabotage_panel(self, camera.ui)
        elif panel_id == "result" and report is not None:
            self.panel = panels_action.build_result_panel(self, camera.ui, report)
        self._enter_ui_mode()

    def close_current_panel(self) -> None:
        """Public: callable from panel buttons. Lobby panel can't be closed
        manually — the server must transition the phase first."""
        if self.panel_id == "lobby":
            return
        self._close_panel_silent()
        self._exit_ui_mode()

    def _close_panel_silent(self) -> None:
        if self.panel is not None:
            destroy(self.panel)
        self.panel = None
        self.panel_id = None

    def _enter_ui_mode(self) -> None:
        self.player.enabled = False
        mouse.locked = False
        mouse.visible = True

    def _exit_ui_mode(self) -> None:
        self.player.enabled = True
        mouse.locked = True
        mouse.visible = False

    def _refresh_current_panel(self) -> None:
        """Some actions (side pick, ready toggle, target change, queue change)
        update state the panel displays. Cheapest correct thing is to rebuild."""
        if self.panel_id is None:
            return
        current = self.panel_id
        self._close_panel_silent()
        self._open_panel(current)

    # ------------------------------------------------------------------
    # Building interiors — walkable rooms, not panels
    # ------------------------------------------------------------------
    def _enter_interior(self, bid: str) -> None:
        interior = self.interiors.get(bid)
        if interior is None:
            return
        # Remember where the player was so exit can drop them back there.
        self._exit_return_pos = tuple(self.player.position)
        self.in_interior = bid
        interior.show()
        # Prime the displays so they don't flash empty on first frame.
        if bid == "rd":
            interior.sync_state(self.me(), self.rd_target, self.rd_spend)
        elif bid == "mc":
            interior.sync_state(self.me(), self.state, self)
        else:
            interior.sync_state(self.me(), self.state)
        self.player.position = interior.entry_world_pos
        mouse.locked = True
        mouse.visible = False

    # Legacy alias so earlier code paths keep working.
    def _enter_rd_interior(self) -> None:
        self._enter_interior("rd")

    def _exit_interior(self) -> None:
        if self.in_interior is not None:
            self.interiors[self.in_interior].hide()
        self.in_interior = None
        if self._exit_return_pos is not None:
            self.player.position = self._exit_return_pos
            self._exit_return_pos = None

    def _press_interior_button(self) -> None:
        """Dispatch an E press while inside any interior. The set of valid
        button ids is per-room; everything else is a no-op."""
        if self.in_interior is None:
            return
        interior = self.interiors[self.in_interior]
        px, _, pz = self.player.position
        bid = interior.nearby_button((px, pz))
        if bid is None:
            return
        interior.press_feedback(bid)
        if bid == "exit":
            self._exit_interior()
            return
        # R&D room buttons
        if self.in_interior == "rd":
            if bid.startswith("target:"):
                self.rd_set_target(bid.split(":", 1)[1])
            elif bid == "spend_plus":
                self.rd_change_spend(5)
            elif bid == "spend_minus":
                self.rd_change_spend(-5)
            return
        # Mission Control buttons. The V2 layout only has three: a single
        # MISSION SELECT console that opens the panel, a SCRUB pedestal,
        # and the EXIT (handled above). Every per-mission / per-objective
        # / per-architecture press happens inside the panel now.
        if self.in_interior == "mc":
            if bid == "scrub":
                self.mc_scrub_scheduled()
                return
            if bid == "mc_panel":
                self._open_panel("mc")
                return
            return
        # Astronaut Complex buttons
        if self.in_interior == "astro":
            if bid == "training":
                self._open_panel("training")
                return
            if bid == "recruit":
                self._open_panel("recruit")
                return
            return
        # Intelligence Office buttons
        if self.in_interior == "intel":
            if bid == "intel":
                self.intel_request_report()
                return
            if bid == "sabotage":
                self._open_panel("sabotage")
                return
            return

    # Legacy alias so existing input dispatch keeps working.
    def _press_rd_interior_button(self) -> None:
        self._press_interior_button()

    # ------------------------------------------------------------------
    # Lobby actions
    # ------------------------------------------------------------------
    def _maybe_auto_open_lobby(self) -> None:
        if (
            self.state is not None
            and self.state.phase == Phase.LOBBY
            and self.panel_id is None
        ):
            self._open_panel("lobby")
            self._lobby_opened = True

    def _maybe_close_lobby_on_start(self) -> None:
        if (
            self.state is not None
            and self.state.phase == Phase.PLAYING
            and self.panel_id == "lobby"
        ):
            self._close_panel_silent()
            self._exit_ui_mode()

    def lobby_pick_side(self, side: str) -> None:
        self.net.send(protocol.CHOOSE_SIDE, side=side)
        # refresh to show highlight; real state will arrive shortly
        self._refresh_current_panel()

    def lobby_toggle_ready(self) -> None:
        me = self.me()
        ready = bool(me and me.ready)
        self.net.send(protocol.UNREADY if ready else protocol.READY)
        self._refresh_current_panel()

    # ------------------------------------------------------------------
    # R&D actions
    # ------------------------------------------------------------------
    def rd_set_target(self, value: str) -> None:
        if self._turn_locked():
            return
        self.rd_target = value
        self._refresh_current_panel()

    def rd_change_spend(self, delta: int) -> None:
        if self._turn_locked():
            return
        me = self.me()
        ceiling = me.budget if me is not None else 999
        self.rd_spend = max(0, min(ceiling, self.rd_spend + delta))
        self._refresh_current_panel()

    # ------------------------------------------------------------------
    # Mission Control actions
    # ------------------------------------------------------------------
    def mc_select_mission(self, mission_id: MissionId) -> None:
        if self._turn_locked() or self._has_scheduled_launch():
            return
        if self.queued_mission == mission_id:
            self.queued_mission = None
            self.queued_objectives.clear()
            self.queued_crew.clear()
        else:
            self.queued_mission = mission_id
            # Drop any objectives that don't apply to the new mission.
            allowed = {o.id for o in objectives_for(mission_id)}
            self.queued_objectives = {o for o in self.queued_objectives if o in allowed}
            # Re-pick the crew for the new mission.
            self.queued_crew = []
        self._refresh_current_panel()

    def mc_toggle_objective(self, obj_id: ObjectiveId) -> None:
        if self._turn_locked() or self._has_scheduled_launch():
            return
        if obj_id in self.queued_objectives:
            self.queued_objectives.discard(obj_id)
        else:
            self.queued_objectives.add(obj_id)
        self._refresh_current_panel()

    def mc_toggle_crew(self, astronaut_id: str) -> None:
        """Add or remove an astronaut from the manually-picked crew for
        the queued manned mission. Honoured at submit time only when
        the count exactly matches mission.crew_size; otherwise the
        resolver falls back to auto top-skilled selection."""
        if self._turn_locked() or self._has_scheduled_launch():
            return
        if self.queued_mission is None:
            return
        mission = MISSIONS_BY_ID.get(self.queued_mission)
        if mission is None or not mission.manned:
            return
        if astronaut_id in self.queued_crew:
            self.queued_crew.remove(astronaut_id)
        elif len(self.queued_crew) < mission.crew_size:
            self.queued_crew.append(astronaut_id)
        # else: cap reached, drop someone before adding another.
        self._refresh_current_panel()

    def _has_scheduled_launch(self) -> bool:
        me = self.me()
        return me is not None and me.scheduled_launch is not None

    def mc_scrub_scheduled(self) -> None:
        """Send the SCRUB_SCHEDULED message to void the upcoming launch.
        Server refunds a fraction of the assembly cost and clears the
        manifest slot. Safe to call even if nothing is scheduled — the
        server guards against no-ops."""
        self.net.send(protocol.SCRUB_SCHEDULED)

    # ------------------------------------------------------------------
    # Astronaut training
    # ------------------------------------------------------------------
    def astro_start_training(self, astronaut_id: str, skill) -> None:
        """Fire START_TRAINING; server validates budget + state. Immediately
        rebuild the open training panel so the button state updates."""
        self.net.send(
            protocol.START_TRAINING,
            astronaut_id=astronaut_id,
            skill=skill.value,
        )
        self._refresh_current_panel()

    def astro_cancel_training(self, astronaut_id: str) -> None:
        self.net.send(protocol.CANCEL_TRAINING, astronaut_id=astronaut_id)
        self._refresh_current_panel()

    def astro_recruit_group(self) -> None:
        """Ask the server to hire the next recruitment group. Server
        validates year + budget; we just refresh the panel so the new
        status line shows up once state echoes back."""
        self.net.send(protocol.RECRUIT_GROUP)
        self._refresh_current_panel()

    def intel_request_report(self) -> None:
        """Fire REQUEST_INTEL. Server validates budget + one-per-season
        and echoes back new state with latest_intel populated."""
        self.net.send(protocol.REQUEST_INTEL)

    def intel_execute_sabotage(self, card_id: str) -> None:
        """Fire EXECUTE_SABOTAGE. Server validates budget + per-season
        gate, applies the per-card effect, and echoes back state.
        Refresh the open panel so the in-progress card list updates."""
        self.net.send(protocol.EXECUTE_SABOTAGE, card_id=card_id)
        self._refresh_current_panel()

    def mc_choose_architecture(self, arch: Architecture) -> None:
        if self._turn_locked():
            return
        self.net.send(protocol.CHOOSE_ARCHITECTURE, architecture=arch.value)
        self._refresh_current_panel()

    def mc_submit_turn(self) -> None:
        me = self.me()
        if me is None or me.turn_submitted:
            return
        payload: dict[str, Any] = {
            "rd_spend": min(self.rd_spend, me.budget),
            "launch": self.queued_mission.value if self.queued_mission else None,
            "objectives": [o.value for o in self.queued_objectives],
            "crew": list(self.queued_crew),
        }
        # rd_target may be a Rocket.value or Module.value.
        if self.rd_target in (m.value for m in Module):
            payload["rd_module"] = self.rd_target
        elif self.rd_target in (r.value for r in Rocket):
            payload["rd_rocket"] = self.rd_target
        self.net.send(protocol.END_TURN, **payload)
        self.queued_mission = None
        self.queued_objectives.clear()
        self.queued_crew.clear()
        self._close_panel_silent()
        self._exit_ui_mode()

    # ------------------------------------------------------------------
    # Launch sequence
    # ------------------------------------------------------------------
    def _maybe_start_launch_sequence(self) -> None:
        if self.state is None or not self.state.last_launches:
            return
        sig = (self.state.year, self.state.season.value, self.state.phase.value)
        if sig == self._consumed_launch_sig:
            return
        self._consumed_launch_sig = sig
        # Order own launch first so the animation hits for the local player.
        me = self.me()
        my_side = me.side.value if me and me.side else None
        own = [r for r in self.state.last_launches if my_side and r.side == my_side]
        other = [r for r in self.state.last_launches if not my_side or r.side != my_side]
        self.report_queue = own + other
        if not self.report_queue:
            return
        # Make sure the player is standing on the main facility so the
        # rocket animation is actually visible — otherwise they'd be
        # locked inside a windowless room while their rocket lifts off.
        if self.in_interior is not None:
            self._exit_interior()
        self.report_idx = 0
        self._start_next_report()

    def _start_next_report(self) -> None:
        if self.report_idx >= len(self.report_queue):
            self._finish_launch_sequence()
            return
        report = self.report_queue[self.report_idx]
        me = self.me()
        is_own = bool(me and me.side and report.side == me.side.value)
        # Own non-aborted launches get the ascend animation; everything else
        # jumps straight to the result panel.
        if is_own and not report.aborted:
            # Make sure the rocket on the pad matches the class that
            # actually launched (the player may have been showing R&D
            # target instead of the queued mission's rocket).
            self._show_only_rocket(report.rocket_class or self.current_rocket_class)
            self._close_panel_silent()
            self._enter_ui_mode()
            self.launch_phase = "ascend"
            rocket = self.rockets[self.current_rocket_class]
            flame = self.flames[self.current_rocket_class]
            flame.enabled = True
            rocket.animate_y(
                launch_scene.APEX_Y,
                duration=launch_scene.LIFTOFF_DURATION,
                curve=curve.linear,
            )
            invoke(self._show_result_after_ascend, delay=launch_scene.LIFTOFF_DURATION)
        else:
            self._show_result_panel(report)

    def _show_only_rocket(self, cls: str) -> None:
        if cls not in self.rockets:
            cls = "Light"
        for name, rkt in self.rockets.items():
            rkt.enabled = (name == cls)
        self.current_rocket_class = cls

    def _show_result_after_ascend(self) -> None:
        if self.launch_phase != "ascend":
            return
        if self.report_idx >= len(self.report_queue):
            return
        self.flames[self.current_rocket_class].enabled = False
        self._show_result_panel(self.report_queue[self.report_idx])

    def _show_result_panel(self, report: LaunchReport) -> None:
        self.launch_phase = "result"
        self._open_panel("result", report=report)

    def advance_result_panel(self) -> None:
        if self.launch_phase != "result":
            return
        self.report_idx += 1
        self._close_panel_silent()
        if self.report_idx < len(self.report_queue):
            self.launch_phase = "idle"
            self._start_next_report()
        else:
            self._finish_launch_sequence()

    def _skip_ascend(self) -> None:
        rocket = self.rockets[self.current_rocket_class]
        flame = self.flames[self.current_rocket_class]
        rocket.y = launch_scene.APEX_Y
        flame.enabled = False
        if self.report_idx < len(self.report_queue):
            self._show_result_panel(self.report_queue[self.report_idx])

    def _finish_launch_sequence(self) -> None:
        self.report_queue = []
        self.report_idx = 0
        self.launch_phase = "idle"
        # Drop every rocket back onto the pad so whichever one gets shown
        # next is at its rest height, not still floating at apex.
        for cls, rkt in self.rockets.items():
            launch_scene.reset_rocket(rkt, self.flames[cls])
        self._exit_ui_mode()
