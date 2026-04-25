from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any


class Side(str, Enum):
    USA = "USA"
    USSR = "USSR"


class Season(str, Enum):
    SPRING = "Spring"
    SUMMER = "Summer"
    FALL = "Fall"
    WINTER = "Winter"


class Phase(str, Enum):
    LOBBY = "lobby"
    PLAYING = "playing"
    ENDED = "ended"


class Rocket(str, Enum):
    LIGHT = "Light"
    MEDIUM = "Medium"
    HEAVY = "Heavy"


class Module(str, Enum):
    """Non-rocket hardware with its own R&D track. Researched the same way
    rockets are (stochastic batched rolls against a single reliability
    score). Individual missions list which modules they need in their
    `requires_modules` tuple; the resolver rejects a launch whose
    required modules aren't built."""
    DOCKING = "Docking Module"
    LUNAR_KICKER = "Lunar Kicker"
    EVA_SUIT = "EVA Suit"


class Skill(str, Enum):
    """Crew skill categories, aligned with the BARIS manual's five tracks.

    CAPSULE — Capsule Pilot (CA): applies to all capsule / shuttle steps.
    LM_PILOT — Lunar Module Pilot (LM): applies to lunar-module steps.
    EVA     — Extra-Vehicular Activity: spacewalks and lunar surface work.
    DOCKING — Docking (DO): applies to orbital docking attempts.
    ENDURANCE — (EN): long-duration missions, hospital recovery.
    """
    CAPSULE = "capsule"
    LM_PILOT = "lm_pilot"
    EVA = "eva"
    DOCKING = "docking"
    ENDURANCE = "endurance"


class AstronautStatus(str, Enum):
    ACTIVE = "active"
    KIA = "kia"
    RETIRED = "retired"


class Compatibility(str, Enum):
    """Rough personality-type tag assigned to each astronaut at roster
    creation. Used to score crew compatibility: same/adjacent types mesh
    well, opposite types (A<->C, B<->D) grind on each other."""
    A = "A"
    B = "B"
    C = "C"
    D = "D"


class MissionId(str, Enum):
    SUBORBITAL = "suborbital"
    SATELLITE = "satellite"
    ORBITAL = "orbital"
    LUNAR_PASS = "lunar_pass"
    LUNAR_ORBIT = "lunar_orbit"
    LUNAR_LANDING = "lunar_landing"
    MANNED_ORBITAL = "manned_orbital"
    MULTI_CREW_ORBITAL = "multi_crew_orbital"
    ORBITAL_EVA = "orbital_eva"
    MANNED_LUNAR_ORBIT = "manned_lunar_orbit"
    MANNED_LUNAR_LANDING = "manned_lunar_landing"
    # Phase G — expanded catalog.
    ORBITAL_DOCKING = "orbital_docking"
    LM_EARTH_TEST = "lm_earth_test"
    LM_LUNAR_TEST = "lm_lunar_test"
    VENUS_FLYBY = "venus_flyby"
    MARS_FLYBY = "mars_flyby"
    MERCURY_FLYBY = "mercury_flyby"
    JUPITER_FLYBY = "jupiter_flyby"
    SATURN_FLYBY = "saturn_flyby"


class ObjectiveId(str, Enum):
    EVA            = "eva"
    DOCKING        = "docking"
    LONG_DURATION  = "long_duration"
    MOONWALK       = "moonwalk"
    SAMPLE_RETURN  = "sample_return"


class ProgramTier(str, Enum):
    ONE = "1"   # Mercury / Vostok
    TWO = "2"   # Gemini / Voskhod
    THREE = "3" # Apollo / Soyuz


class Architecture(str, Enum):
    """Lunar mission architecture — historical design decision that NASA
    actually debated before Apollo. Each option is genuinely different:

    - LOR: single Heavy launch, lander meets command module in lunar orbit.
      Historical winner. Baseline stats.
    - DA (Direct Ascent): single huge rocket lands the whole return vehicle.
      +success, +cost. Would have needed Saturn C-8/Nova in reality.
    - EOR (Earth Orbit Rendezvous): many smaller launches, assemble in Earth
      orbit. Uses Medium rocket instead of Heavy, big cost, lower success.
    - LSR (Lunar Surface Rendezvous): pre-land unmanned return vehicle, then
      send crew. Requires prior unmanned lunar landing success. +success, +cost.
    """
    LOR = "LOR"
    DA  = "DA"
    EOR = "EOR"
    LSR = "LSR"


ARCHITECTURE_FULL_NAMES: dict[Architecture, str] = {
    Architecture.LOR: "Lunar Orbit Rendezvous",
    Architecture.DA:  "Direct Ascent",
    Architecture.EOR: "Earth Orbit Rendezvous",
    Architecture.LSR: "Lunar Surface Rendezvous",
}

# Per-architecture modifiers applied to the manned lunar landing mission only.
# Keys omitted default to 0 / no change.
ARCHITECTURE_SUCCESS_DELTA: dict[Architecture, float] = {
    Architecture.LOR:  0.00,
    Architecture.DA:  +0.10,
    Architecture.EOR: -0.10,
    Architecture.LSR: +0.08,
}
ARCHITECTURE_COST_DELTA: dict[Architecture, int] = {
    Architecture.LOR:  0,
    Architecture.DA:  25,
    Architecture.EOR: 40,
    Architecture.LSR: 15,
}


@dataclass(frozen=True)
class Mission:
    id: MissionId
    name: str
    rocket: Rocket
    launch_cost: int
    base_success: float
    prestige_success: int
    prestige_fail: int
    first_bonus: int
    tier: ProgramTier = ProgramTier.ONE
    manned: bool = False
    crew_size: int = 0
    primary_skill: Skill | None = None
    # Phase F — hardware prereqs beyond the rocket. Each module named
    # here must be built (reliability >= MIN_RELIABILITY_TO_LAUNCH) at
    # schedule time or the launch is rejected. Default: no extra prereqs.
    requires_modules: tuple["Module", ...] = ()


# Ordered catalog — UI iterates this to build the mission list (indices map to keys 1-0 and -).
MISSIONS: tuple[Mission, ...] = (
    # Tier 1 — Mercury / Vostok
    Mission(MissionId.SUBORBITAL,           "Sub-orbital flight",   Rocket.LIGHT,  3, 0.85,  3, 1,  2,
            tier=ProgramTier.ONE),
    Mission(MissionId.SATELLITE,            "Satellite launch",     Rocket.LIGHT,  5, 0.75,  5, 2,  3,
            tier=ProgramTier.ONE),
    Mission(MissionId.ORBITAL,              "Orbital flight",       Rocket.MEDIUM, 8, 0.70,  7, 2,  4,
            tier=ProgramTier.ONE),
    Mission(MissionId.MANNED_ORBITAL,       "Manned orbital",       Rocket.MEDIUM,15, 0.55, 12, 4,  6,
            tier=ProgramTier.ONE, manned=True, crew_size=1, primary_skill=Skill.CAPSULE),
    # Tier 2 — Gemini / Voskhod
    Mission(MissionId.MULTI_CREW_ORBITAL,   "Multi-crew orbital",   Rocket.MEDIUM,18, 0.55, 12, 4,  6,
            tier=ProgramTier.TWO, manned=True, crew_size=2, primary_skill=Skill.ENDURANCE),
    Mission(MissionId.ORBITAL_EVA,          "Orbital EVA",          Rocket.MEDIUM,20, 0.50, 14, 5,  7,
            tier=ProgramTier.TWO, manned=True, crew_size=2, primary_skill=Skill.EVA,
            requires_modules=(Module.EVA_SUIT,)),
    Mission(MissionId.LUNAR_PASS,           "Lunar flyby",          Rocket.MEDIUM,12, 0.60, 10, 3,  5,
            tier=ProgramTier.TWO,
            requires_modules=(Module.LUNAR_KICKER,)),
    Mission(MissionId.LUNAR_ORBIT,          "Lunar orbit",          Rocket.HEAVY, 18, 0.50, 15, 4,  7,
            tier=ProgramTier.TWO,
            requires_modules=(Module.LUNAR_KICKER,)),
    # Tier 3 — Apollo / Soyuz
    Mission(MissionId.LUNAR_LANDING,        "Lunar landing",        Rocket.HEAVY, 25, 0.35, 20, 5, 10,
            tier=ProgramTier.THREE,
            requires_modules=(Module.LUNAR_KICKER,)),
    Mission(MissionId.MANNED_LUNAR_ORBIT,   "Manned lunar orbit",   Rocket.HEAVY, 25, 0.40, 20, 6,  9,
            tier=ProgramTier.THREE, manned=True, crew_size=2, primary_skill=Skill.CAPSULE,
            requires_modules=(Module.LUNAR_KICKER,)),
    Mission(MissionId.MANNED_LUNAR_LANDING, "Manned lunar landing", Rocket.HEAVY, 35, 0.25, 35, 8, 15,
            tier=ProgramTier.THREE, manned=True, crew_size=3, primary_skill=Skill.LM_PILOT,
            requires_modules=(Module.LUNAR_KICKER, Module.EVA_SUIT)),
    # Phase G — manned orbital docking.
    Mission(MissionId.ORBITAL_DOCKING,      "Orbital docking",      Rocket.MEDIUM,22, 0.50, 14, 5,  7,
            tier=ProgramTier.TWO, manned=True, crew_size=2, primary_skill=Skill.DOCKING,
            requires_modules=(Module.DOCKING,)),
    # Phase G — LM hardware tests (grant bonus LM points on success).
    Mission(MissionId.LM_EARTH_TEST,        "LM test (Earth orbit)", Rocket.MEDIUM,24, 0.45, 12, 5,  6,
            tier=ProgramTier.THREE, manned=True, crew_size=2, primary_skill=Skill.LM_PILOT),
    Mission(MissionId.LM_LUNAR_TEST,        "LM test (lunar orbit)", Rocket.HEAVY, 30, 0.40, 18, 6,  8,
            tier=ProgramTier.THREE, manned=True, crew_size=2, primary_skill=Skill.LM_PILOT,
            requires_modules=(Module.LUNAR_KICKER,)),
    # Phase G — interplanetary probes. All need the Lunar Kicker's
    # deep-space injection stage. Distance ≈ difficulty.
    Mission(MissionId.VENUS_FLYBY,          "Venus flyby",          Rocket.MEDIUM,14, 0.55,  8, 3,  4,
            tier=ProgramTier.TWO,
            requires_modules=(Module.LUNAR_KICKER,)),
    Mission(MissionId.MARS_FLYBY,           "Mars flyby",           Rocket.MEDIUM,16, 0.50,  9, 3,  5,
            tier=ProgramTier.TWO,
            requires_modules=(Module.LUNAR_KICKER,)),
    Mission(MissionId.MERCURY_FLYBY,        "Mercury flyby",        Rocket.MEDIUM,18, 0.45,  9, 3,  5,
            tier=ProgramTier.THREE,
            requires_modules=(Module.LUNAR_KICKER,)),
    Mission(MissionId.JUPITER_FLYBY,        "Jupiter flyby",        Rocket.HEAVY, 22, 0.40, 10, 4,  6,
            tier=ProgramTier.THREE,
            requires_modules=(Module.LUNAR_KICKER,)),
    Mission(MissionId.SATURN_FLYBY,         "Saturn flyby",         Rocket.HEAVY, 25, 0.35, 12, 4,  7,
            tier=ProgramTier.THREE,
            requires_modules=(Module.LUNAR_KICKER,)),
)

MISSIONS_BY_ID: dict[MissionId, Mission] = {m.id: m for m in MISSIONS}


@dataclass(frozen=True)
class MissionObjective:
    """An opt-in sub-objective the player can attempt during a manned mission.
    Each objective rolls independently from the main mission success roll."""
    id: ObjectiveId
    name: str
    required_skill: Skill
    base_success: float
    prestige_bonus: int
    # Failure consequences. Exactly one of these should be non-zero for risky
    # objectives; benign objectives (sample return, long duration) leave both 0.
    fail_crew_death_chance: float = 0.0   # single crew member dies on fail
    fail_ship_loss_chance: float = 0.0    # whole ship + crew lost; rocket reliability tanks
    requires_module: Module | None = None


# Objectives attached per manned mission. Not every manned mission has
# objectives — ORBITAL_EVA has EVA baked in as the whole point, so skip it.
MISSION_OBJECTIVES: dict[MissionId, tuple[MissionObjective, ...]] = {
    MissionId.MANNED_ORBITAL: (
        MissionObjective(
            ObjectiveId.EVA, "Orbital EVA", Skill.EVA,
            base_success=0.60, prestige_bonus=4,
            fail_crew_death_chance=0.15,
            requires_module=Module.EVA_SUIT,
        ),
        MissionObjective(
            ObjectiveId.LONG_DURATION, "Long-duration orbit", Skill.ENDURANCE,
            base_success=0.70, prestige_bonus=2,
        ),
    ),
    MissionId.MULTI_CREW_ORBITAL: (
        MissionObjective(
            ObjectiveId.DOCKING, "Orbital docking", Skill.DOCKING,
            base_success=0.55, prestige_bonus=6,
            fail_ship_loss_chance=0.25,
            requires_module=Module.DOCKING,
        ),
        MissionObjective(
            ObjectiveId.EVA, "Spacewalk", Skill.EVA,
            base_success=0.60, prestige_bonus=4,
            fail_crew_death_chance=0.15,
            requires_module=Module.EVA_SUIT,
        ),
    ),
    MissionId.MANNED_LUNAR_LANDING: (
        MissionObjective(
            ObjectiveId.MOONWALK, "Lunar EVA (moonwalk)", Skill.EVA,
            base_success=0.55, prestige_bonus=6,
            fail_crew_death_chance=0.15,
        ),
        MissionObjective(
            ObjectiveId.SAMPLE_RETURN, "Lunar sample return", Skill.ENDURANCE,
            base_success=0.70, prestige_bonus=4,
        ),
    ),
}


def objectives_for(mission_id: MissionId) -> tuple[MissionObjective, ...]:
    return MISSION_OBJECTIVES.get(mission_id, ())

# Per-hardware R&D speed. Keyed by the enum .value so a single dict covers
# both rockets and modules. Heavy rockets are genuinely hard to develop;
# the docking module sits between Light and Medium in difficulty.
RD_SPEED: dict[str, float] = {
    Rocket.LIGHT.value:        1.0,
    Rocket.MEDIUM.value:       0.5,
    Rocket.HEAVY.value:        0.3,
    Module.DOCKING.value:      0.7,
    Module.LUNAR_KICKER.value: 0.5,
    Module.EVA_SUIT.value:     0.8,
}
RD_BATCH_COST = 3  # MB per roll


def hardware_names() -> tuple[str, ...]:
    """All researchable hardware in display order."""
    return tuple(r.value for r in Rocket) + tuple(m.value for m in Module)

STARTING_BUDGET = 30
SEASON_REFILL = 15
PRESTIGE_TO_WIN = 40
STARTING_ASTRONAUTS = 7
DEATH_CHANCE_ON_FAIL = 0.25
DEATH_PRESTIGE_PENALTY = 3

# Phase J — recruitment groups. Group 1 is the starting roster; groups
# 2-4 can be hired in order once their historical earliest_year arrives
# and the player can afford the cost. Fresh recruits enter with
# basic_training_remaining=BASIC_TRAINING_TURNS so they're unavailable
# for a handful of seasons after they arrive.
RECRUIT_SKILL_MIN = 15
RECRUIT_SKILL_MAX = 40


@dataclass(frozen=True)
class RecruitmentGroup:
    number: int
    size: int
    cost: int             # MB; group 1 is free (auto-hired at game start)
    earliest_year: int    # earliest state.year the group can be recruited
    us_names: tuple[str, ...]
    ussr_names: tuple[str, ...]


RECRUITMENT_GROUPS: tuple[RecruitmentGroup, ...] = (
    # Group 1 — starting roster (7 each side). The astronaut pool is
    # drawn from "Italian Brainrot" meme characters rather than the
    # real Mercury Seven / first-Vostok cosmonaut cohorts. The two
    # sides have a vibe split: USA team leans bombers / soldiers /
    # banditos; USSR team leans bestiary / botanical / surreal.
    RecruitmentGroup(
        number=1, size=7, cost=0, earliest_year=1957,
        us_names=(
            "Bombardiro Crocodilo", "Bombombini Gusini",
            "Tung Tung Tung Sahur", "Bobrito Bandito",
            "Cappuccino Assassino", "Glorbo Fruttodrillo",
            "Trippi Troppi",
        ),
        ussr_names=(
            "Tralalero Tralala", "Lirili Larila",
            "Brr Brr Patapim", "Frigo Camelo",
            "Boneca Ambalabu", "Chimpanzini Bananini",
            "Ballerina Cappuccina",
        ),
    ),
    # Group 2 — five reinforcements per side.
    RecruitmentGroup(
        number=2, size=5, cost=25, earliest_year=1962,
        us_names=(
            "Espresso Esecutore", "Calzone Cannoniere",
            "Pizzaiolo Maranello", "Vespa Velocissima",
            "Ferrari Furioso",
        ),
        ussr_names=(
            "Burbaloni Luliloli", "Trulimero Trulichina",
            "Crocodillo Bombardillo", "Patapim Patapum",
            "Coccodrillo Tropicale",
        ),
    ),
    # Group 3 — five more.
    RecruitmentGroup(
        number=3, size=5, cost=35, earliest_year=1963,
        us_names=(
            "Mortadella Maresciallo", "Limoncello Letale",
            "Cannolo Capitano", "Granita Granaderiotto",
            "Risotto Razziatore",
        ),
        ussr_names=(
            "Spaghettino Spaghettoni", "Pesto Pestilenziale",
            "Mozzarella Misteriosa", "Tortellino Tornado",
            "Pollo Polletto",
        ),
    ),
    # Group 4 — five elites.
    RecruitmentGroup(
        number=4, size=5, cost=50, earliest_year=1966,
        us_names=(
            "Lasagna Comandante", "Carbonara Catastrofica",
            "Negroni Notturno", "Polpetta Predatrice",
            "Tiramisu Terrificante",
        ),
        ussr_names=(
            "Gelato Glaciale", "Vino Visionario",
            "Olive Oltretomba", "Salami Stratosferico",
            "Bresaola Boreale",
        ),
    ),
)


# Per-character portrait flavour: an emoji glyph + a colour swatch.
# Both 2D and 3D clients render this next to the character's name on
# rosters / portrait walls. Names not in this table fall back to a
# generic "?" glyph and a neutral grey swatch via character_portrait().
CHARACTER_PORTRAITS: dict[str, tuple[str, tuple[int, int, int]]] = {
    # USA team — Group 1
    "Bombardiro Crocodilo":   ("🐊", (90, 130, 70)),
    "Bombombini Gusini":      ("🦢", (200, 200, 220)),
    "Tung Tung Tung Sahur":   ("🪵", (140, 95, 50)),
    "Bobrito Bandito":        ("🦫", (120, 80, 50)),
    "Cappuccino Assassino":   ("☕", (130, 90, 60)),
    "Glorbo Fruttodrillo":    ("🍎", (200, 60, 60)),
    "Trippi Troppi":          ("🐈", (180, 130, 80)),
    # USSR team — Group 1
    "Tralalero Tralala":      ("🦈", (80, 130, 200)),
    "Lirili Larila":          ("🌵", (90, 160, 110)),
    "Brr Brr Patapim":        ("🌳", (60, 130, 80)),
    "Frigo Camelo":           ("🐪", (200, 180, 130)),
    "Boneca Ambalabu":        ("💀", (220, 220, 230)),
    "Chimpanzini Bananini":   ("🐵", (230, 200, 80)),
    "Ballerina Cappuccina":   ("🩰", (220, 150, 180)),
    # USA — Group 2
    "Espresso Esecutore":     ("☕", (90, 60, 40)),
    "Calzone Cannoniere":     ("🥪", (220, 180, 100)),
    "Pizzaiolo Maranello":    ("🍕", (220, 100, 60)),
    "Vespa Velocissima":      ("🛵", (180, 50, 50)),
    "Ferrari Furioso":        ("🏎",  (210, 30, 30)),
    # USSR — Group 2
    "Burbaloni Luliloli":     ("🥥", (160, 110, 70)),
    "Trulimero Trulichina":   ("🐟", (120, 170, 200)),
    "Crocodillo Bombardillo": ("🐊", (110, 150, 90)),
    "Patapim Patapum":        ("🌴", (80, 140, 90)),
    "Coccodrillo Tropicale":  ("🌺", (220, 110, 130)),
    # USA — Group 3
    "Mortadella Maresciallo": ("🥩", (190, 90, 100)),
    "Limoncello Letale":      ("🍋", (240, 220, 80)),
    "Cannolo Capitano":       ("🥧", (220, 200, 150)),
    "Granita Granaderiotto":  ("🍧", (180, 220, 240)),
    "Risotto Razziatore":     ("🍚", (230, 220, 200)),
    # USSR — Group 3
    "Spaghettino Spaghettoni": ("🍝", (220, 180, 90)),
    "Pesto Pestilenziale":    ("🌿", (90, 160, 70)),
    "Mozzarella Misteriosa":  ("🧀", (240, 230, 200)),
    "Tortellino Tornado":     ("🥟", (220, 200, 160)),
    "Pollo Polletto":         ("🐔", (220, 180, 90)),
    # USA — Group 4
    "Lasagna Comandante":     ("🥧", (200, 130, 90)),
    "Carbonara Catastrofica": ("🥓", (200, 110, 110)),
    "Negroni Notturno":       ("🍸", (200, 90, 90)),
    "Polpetta Predatrice":    ("🥩", (160, 90, 90)),
    "Tiramisu Terrificante":  ("🍰", (180, 140, 100)),
    # USSR — Group 4
    "Gelato Glaciale":        ("🍨", (200, 220, 240)),
    "Vino Visionario":        ("🍷", (140, 50, 80)),
    "Olive Oltretomba":       ("🫒", (140, 150, 90)),
    "Salami Stratosferico":   ("🥓", (170, 90, 90)),
    "Bresaola Boreale":       ("🥩", (180, 100, 100)),
}


def character_portrait(name: str) -> tuple[str, tuple[int, int, int]]:
    """Look up a character's glyph + RGB swatch. Unknown names fall
    back to a neutral '?' grey so a custom or backfilled astronaut
    still renders without crashing the UI."""
    return CHARACTER_PORTRAITS.get(name, ("?", (160, 160, 170)))


# Historical starting rosters, derived from Group 1 so there's one source
# of truth. Kept as a name for older call-sites that reference it.
HISTORICAL_ROSTERS: dict[str, tuple[str, ...]] = {
    Side.USA.value: RECRUITMENT_GROUPS[0].us_names,
    Side.USSR.value: RECRUITMENT_GROUPS[0].ussr_names,
}

# Per-side historical rocket names, mapped to our Light/Medium/Heavy classes.
# USA: Redstone (Mercury sub-orbital), Titan II (Gemini orbital), Saturn V (Apollo lunar).
# USSR: R-7 (Sputnik/Vostok), Proton (heavy LEO/lunar probes), N1 (lunar — historically never flew successfully).
HISTORICAL_ROCKET_NAMES: dict[str, dict[Rocket, str]] = {
    Side.USA.value: {
        Rocket.LIGHT:  "Redstone",
        Rocket.MEDIUM: "Titan II",
        Rocket.HEAVY:  "Saturn V",
    },
    Side.USSR.value: {
        Rocket.LIGHT:  "R-7",
        Rocket.MEDIUM: "Proton",
        Rocket.HEAVY:  "N1",
    },
}

# Per-side historical program names per tier.
# USA: Mercury (ONE), Gemini (TWO), Apollo (THREE).
# USSR: Vostok (ONE), Voskhod (TWO), Soyuz (THREE).
PROGRAM_NAMES: dict[str, dict[ProgramTier, str]] = {
    Side.USA.value: {
        ProgramTier.ONE:   "Mercury",
        ProgramTier.TWO:   "Gemini",
        ProgramTier.THREE: "Apollo",
    },
    Side.USSR.value: {
        ProgramTier.ONE:   "Vostok",
        ProgramTier.TWO:   "Voskhod",
        ProgramTier.THREE: "Soyuz",
    },
}


def rocket_display_name(rocket: Rocket, side: Side | None) -> str:
    """Return the historical per-side name if a side is known, else the class name."""
    if side is None:
        return rocket.value
    return HISTORICAL_ROCKET_NAMES.get(side.value, {}).get(rocket, rocket.value)


def program_name(tier: ProgramTier, side: Side | None) -> str:
    """Return the historical per-side program name if known, else a generic 'Tier N' label."""
    if side is None:
        return f"Tier {tier.value}"
    return PROGRAM_NAMES.get(side.value, {}).get(tier, f"Tier {tier.value}")
# Crew skill bonus to success: full crew averaging 100 in primary skill → +15%.
CREW_MAX_BONUS = 0.15

# Rocket reliability: merged R&D-progress and flight-safety rating (0-99%).
# Built by R&D rolls (stochastic), then nudged up by successful flights and
# down by failures. Directly affects mission success rate.
RELIABILITY_CAP             = 99   # you can never fully trust a rocket
RELIABILITY_FLOOR           = 20   # once built, can't drop below this after a failure
MIN_RELIABILITY_TO_LAUNCH   = 25   # below this, a rocket is considered "not ready"
RELIABILITY_GAIN_ON_SUCCESS = 5
RELIABILITY_LOSS_ON_FAIL    = 10   # manned failures only
UNMANNED_FAILURE_RD_GAIN    = 2    # a crashed unmanned probe still teaches you something
MANNED_FAILURE_BUDGET_CUT   = 30   # lost crew → public/political funding pullback

# Phase B — Vehicle-Assembly costs. A submitted launch reserves
# ASSEMBLY_COST_FRACTION of its launch_cost immediately; the remainder
# is paid the following turn when the vehicle actually flies. Scrubbing
# a scheduled launch refunds SCRUB_REFUND_FRACTION of the assembly
# portion (the rest has already been spent on hardware integration).
ASSEMBLY_COST_FRACTION   = 0.3
SCRUB_REFUND_FRACTION    = 0.5

# Phase C — crew training + hospital recovery.
# - Basic Training: a freshly-recruited astronaut needs BASIC_TRAINING_TURNS
#   seasons of orientation before they can be selected for a mission.
#   The starting roster is assumed pre-trained so they start at 0.
# - Advanced Training: pay ADVANCED_TRAINING_COST MB, wait
#   ADVANCED_TRAINING_TURNS seasons, astronaut gains
#   ADVANCED_TRAINING_SKILL_GAIN points in the chosen skill.
# - Hospital: after a manned-mission failure, each surviving crew member
#   has HOSPITAL_CHANCE_ON_FAIL probability of needing HOSPITAL_STAY_TURNS
#   seasons of recovery before flying again.
BASIC_TRAINING_TURNS         = 3
ADVANCED_TRAINING_TURNS      = 2
ADVANCED_TRAINING_COST       = 3
ADVANCED_TRAINING_SKILL_GAIN = 2
HOSPITAL_STAY_TURNS          = 2
HOSPITAL_CHANCE_ON_FAIL      = 0.4
# Cancelling a training block early refunds this fraction of the cost.
TRAINING_CANCEL_REFUND_FRACTION = 0.5

# Phase K — crew compatibility + mood.
# Each astronaut carries one of four personality tags (Compatibility A-D).
# Matching or adjacent tags (A-B, B-C, C-D, D-A) are worth +1 per pair;
# opposite tags (A-C, B-D) are -1. The crew's average pairwise score,
# scaled by CREW_COMPAT_MAX_BONUS, folds into the mission's effective
# success (bounded ±CREW_COMPAT_MAX_BONUS).
CREW_COMPAT_MAX_BONUS          = 0.05
# Mood is a 0-100 indicator updated by mission events and passive drift.
MOOD_DEFAULT                   = 70
MOOD_MAX                       = 100
MOOD_DRIFT_TARGET              = 60   # per-turn drift pulls toward this
MOOD_DRIFT_PER_TURN            = 2
MOOD_SUCCESS_BUMP              = 10
MOOD_FAILURE_DROP              = 10
MOOD_KIA_CREW_DROP             = 15   # extra hit for surviving crewmates
MOOD_RETIREMENT_THRESHOLD      = 15   # at or below, astronaut retires

# Phase H — Intelligence. Players can pay INTEL_COST once per season to
# receive a noisy snapshot of the opponent's state. Reliability comes
# back as a ±INTEL_RELIABILITY_NOISE band around the true value (clamped
# to 0-RELIABILITY_CAP). The rumored-mission field is correct with
# probability INTEL_RUMOR_ACCURATE — otherwise "" (intentional
# misinformation).
INTEL_COST                 = 10
INTEL_RELIABILITY_NOISE    = 15
INTEL_RUMOR_ACCURATE       = 0.8

# Phase M — Government Review. Fires once at every Winter→Spring
# transition (i.e. once per game-year). Each player's "review score"
# for the year just ended is:
#   prestige_gained_in_year
#     + REVIEW_SUCCESS_BONUS * successful_launches
#     - REVIEW_KIA_PENALTY   * astronauts_KIA
# A score below REVIEW_PASS_THRESHOLD adds a warning. Reach
# REVIEW_FIRE_AT_WARNINGS warnings and the player is dismissed —
# game ends with the opponent declared the winner.
REVIEW_PASS_THRESHOLD       = 3
REVIEW_SUCCESS_BONUS        = 2
REVIEW_KIA_PENALTY          = 3
REVIEW_FIRE_AT_WARNINGS     = 2

# Phase D — Lunar reconnaissance + LM (Lunar Module) points.
#
# Lunar recon tracks how thoroughly the moon has been surveyed before
# you attempt a manned landing. It starts at LUNAR_RECON_BASE (55%, the
# 'ground-based astronomy already knows this much' baseline in the
# original game) and climbs as unmanned + manned lunar missions come
# back — capped at LUNAR_RECON_CAP. Each point above the baseline adds
# LUNAR_RECON_PER_POINT to the manned lunar landing's effective success.
LUNAR_RECON_BASE                   = 55
LUNAR_RECON_CAP                    = 99
LUNAR_RECON_PER_POINT              = 0.004
RECON_FROM_LUNAR_PASS              = 5    # unmanned flyby success
RECON_FROM_LUNAR_ORBIT             = 5    # unmanned lunar orbit success
RECON_FROM_MANNED_LUNAR_ORBIT      = 5    # manned lunar orbit success
RECON_FROM_UNMANNED_LANDING_OK     = 15   # Surveyor-style success
RECON_FROM_UNMANNED_LANDING_FAIL   = 5    # even a crash teaches you something

# LM points: partial-credit system representing LM hardware validation.
# Three points are needed before the manned landing flies without a
# penalty; each missing point applies LM_POINTS_PENALTY_PER_MISSING.
LM_POINTS_REQUIRED                 = 3
LM_POINTS_PENALTY_PER_MISSING      = 0.03
LM_POINTS_FROM_MANNED_ORBITAL      = 1
LM_POINTS_FROM_MULTI_CREW          = 1
LM_POINTS_FROM_ORBITAL_EVA         = 1
LM_POINTS_FROM_UNMANNED_LANDING    = 1
LM_POINTS_FROM_MANNED_LUNAR_ORBIT  = 2
LM_POINTS_FROM_ORBITAL_DOCKING     = 1
LM_POINTS_FROM_LM_EARTH_TEST       = 1
LM_POINTS_FROM_LM_LUNAR_TEST       = 2

# Phase E — multiple launch pads. Each player has LAUNCH_PADS pads
# (default 3, labelled A/B/C). Every pad can hold one ScheduledLaunch at
# a time, so you can have up to three missions in the VAB queue. A
# catastrophic failure (manned death or docking ship-loss) damages the
# launching pad for PAD_REPAIR_TURNS seasons before it's usable again.
LAUNCH_PADS                        = 3
PAD_NAMES: tuple[str, ...]         = ("A", "B", "C")
PAD_REPAIR_TURNS                   = 2
# Reliability contributes ±10% to success around a neutral value of 50.
# effective = base + crew_bonus + (reliability - 50) * RELIABILITY_SWING_PER_POINT
RELIABILITY_SWING_PER_POINT = 0.002


@dataclass
class Astronaut:
    id: str
    name: str
    capsule: int = 0
    lm_pilot: int = 0
    eva: int = 0
    docking: int = 0
    endurance: int = 0
    status: str = AstronautStatus.ACTIVE.value  # stored as string for JSON safety
    # Phase C — training / recovery countdowns. An astronaut is flight-
    # ready iff status==active AND every one of these is zero.
    basic_training_remaining: int = 0
    advanced_training_skill: str = ""     # Skill.value while training, else ""
    advanced_training_remaining: int = 0
    hospital_remaining: int = 0
    # Phase K — personality tag + morale. Both default so legacy rosters
    # without them still construct cleanly.
    compatibility: str = Compatibility.A.value
    mood: int = MOOD_DEFAULT

    def skill(self, kind: Skill) -> int:
        return getattr(self, kind.value)

    def bump_skill(self, kind: Skill, amount: int) -> None:
        value = min(100, max(0, self.skill(kind) + amount))
        setattr(self, kind.value, value)

    @property
    def active(self) -> bool:
        return self.status == AstronautStatus.ACTIVE.value

    @property
    def flight_ready(self) -> bool:
        """True iff the astronaut can be assigned to a mission right now.
        Equivalent to active + no outstanding basic/advanced training
        and no current hospital stay."""
        return (
            self.active
            and self.basic_training_remaining == 0
            and self.advanced_training_remaining == 0
            and self.hospital_remaining == 0
        )

    @property
    def retired(self) -> bool:
        return self.status == AstronautStatus.RETIRED.value

    @property
    def busy_reason(self) -> str:
        """Human-readable reason this astronaut can't fly, or '' if ready."""
        if self.status == AstronautStatus.KIA.value:
            return "KIA"
        if self.status == AstronautStatus.RETIRED.value:
            return "retired"
        if not self.active:
            return "inactive"
        if self.basic_training_remaining > 0:
            return f"basic training ({self.basic_training_remaining})"
        if self.hospital_remaining > 0:
            return f"hospital ({self.hospital_remaining})"
        if self.advanced_training_remaining > 0:
            skill = self.advanced_training_skill or "skill"
            return f"training {skill} ({self.advanced_training_remaining})"
        return ""


@dataclass
class IntelReport:
    """Phase H — one intelligence snapshot taken on the opponent.

    Rocket/module estimates are stored as (low, high) bands rather than
    exact numbers so the UI can display them as "55-85%" style readouts
    that honestly convey the uncertainty. rumored_mission is the
    opponent's scheduled MissionId.value at the moment of capture, with
    probability INTEL_RUMOR_ACCURATE — otherwise empty to reflect
    intentional misinformation."""
    taken_year: int
    taken_season: str
    opponent_side: str                                   # Side.value
    rocket_estimates: dict[str, tuple[int, int]] = field(default_factory=dict)
    rumored_mission: str = ""
    rumored_mission_name: str = ""
    active_crew_count: int = 0


@dataclass
class Player:
    player_id: str
    username: str
    side: Side | None = None
    budget: int = STARTING_BUDGET
    prestige: int = 0
    ready: bool = False
    reliability: dict[str, int] = field(
        default_factory=lambda: {
            **{r.value: 0 for r in Rocket},
            **{m.value: 0 for m in Module},
        }
    )
    astronauts: list[Astronaut] = field(default_factory=list)
    mission_successes: dict[str, int] = field(default_factory=dict)
    architecture: str | None = None  # Architecture.value once chosen, else None
    turn_submitted: bool = False
    pending_rd_target: str | None = None   # Rocket.value, Module.value, or None
    pending_rd_spend: int = 0
    pending_launch: str | None = None      # MissionId.value or None
    pending_objectives: list[str] = field(default_factory=list)  # ObjectiveId.value list
    # Phase E — launch pads. Each pad is a parallel VAB slot: new submits
    # land in the first available pad and each pad resolves independently
    # the following turn. Catastrophic failures damage the launching pad
    # and take it offline for PAD_REPAIR_TURNS seasons.
    pads: list["LaunchPad"] = field(default_factory=lambda: _default_pads())
    # Phase D — cumulative lunar reconnaissance % and LM points.
    lunar_recon: int = LUNAR_RECON_BASE
    lm_points: int = 0
    # Phase J — pointer into RECRUITMENT_GROUPS. Group 1 is auto-hired at
    # start_game; this tracks which group is next for recruitment. Once it
    # exceeds len(RECRUITMENT_GROUPS) the player has exhausted all hires.
    next_recruitment_group: int = 2
    # Phase H — latest intelligence snapshot of the opponent (None until
    # the player actually requests one). intel_requested_on is "year-season"
    # of the most recent request so the server can enforce "one per season".
    latest_intel: "IntelReport | None" = None
    intel_requested_on: str = ""
    # Phase M — Government Review. Each warning is a sub-par year; reach
    # REVIEW_FIRE_AT_WARNINGS and the player is dismissed. last_review_year
    # is the most-recent year already reviewed so resolve_turn knows not
    # to double-review on a single transition.
    warnings: int = 0
    last_review_year: int = 0

    def rocket_reliability(self, rocket: Rocket) -> int:
        return self.reliability.get(rocket.value, 0)

    def rocket_built(self, rocket: Rocket) -> bool:
        return self.rocket_reliability(rocket) >= MIN_RELIABILITY_TO_LAUNCH

    def module_reliability(self, module: Module) -> int:
        return self.reliability.get(module.value, 0)

    def module_built(self, module: Module) -> bool:
        return self.module_reliability(module) >= MIN_RELIABILITY_TO_LAUNCH

    def hardware_reliability(self, name: str) -> int:
        return self.reliability.get(name, 0)

    # back-compat aliases kept short so the UI and resolver don't have to pick.
    def rd_progress(self, rocket: Rocket) -> int:
        return self.rocket_reliability(rocket)

    def safety(self, rocket: Rocket) -> int:
        return self.rocket_reliability(rocket)

    def active_astronauts(self) -> list[Astronaut]:
        return [a for a in self.astronauts if a.active]

    def flight_ready_astronauts(self) -> list[Astronaut]:
        """Alive crew with no training/hospital blocking them from flying.
        Use this (not active_astronauts) when picking a mission crew."""
        return [a for a in self.astronauts if a.flight_ready]

    def has_any_success_in(self, tier: ProgramTier) -> bool:
        """True if the player has at least one success in any mission of the given tier."""
        from baris.state import MISSIONS_BY_ID  # self-reference, resolved at call-time
        for mission_id_str, count in self.mission_successes.items():
            if count <= 0:
                continue
            try:
                mid = MissionId(mission_id_str)
            except ValueError:
                continue
            mission = MISSIONS_BY_ID.get(mid)
            if mission is not None and mission.tier == tier:
                return True
        return False

    def unlocked_tiers(self) -> set[ProgramTier]:
        """Tier 1 is always unlocked. Tier N unlocks once any Tier N-1 mission succeeded."""
        tiers: set[ProgramTier] = {ProgramTier.ONE}
        if self.has_any_success_in(ProgramTier.ONE):
            tiers.add(ProgramTier.TWO)
        if self.has_any_success_in(ProgramTier.TWO):
            tiers.add(ProgramTier.THREE)
        return tiers

    def is_tier_unlocked(self, tier: ProgramTier) -> bool:
        return tier in self.unlocked_tiers()

    # ------------------------------------------------------------------
    # Launch-pad helpers (Phase E)
    # ------------------------------------------------------------------
    def find_pad(self, pad_id: str) -> "LaunchPad | None":
        return next((p for p in self.pads if p.pad_id == pad_id), None)

    def available_pad(self) -> "LaunchPad | None":
        """First pad that can accept a new ScheduledLaunch, or None."""
        return next((p for p in self.pads if p.available), None)

    def any_pad_available(self) -> bool:
        return any(p.available for p in self.pads)

    def scheduled_launches(self) -> list["ScheduledLaunch"]:
        """All ScheduledLaunches currently on the manifest across all
        pads, in pad order. Convenience for UIs summarising queue state."""
        return [p.scheduled_launch for p in self.pads if p.scheduled_launch is not None]

    @property
    def scheduled_launch(self) -> "ScheduledLaunch | None":
        """Back-compat read-only accessor — returns the first scheduled
        launch across the pads, or None. Callers that need multi-pad
        awareness should iterate `self.pads` or `self.scheduled_launches()`."""
        for pad in self.pads:
            if pad.scheduled_launch is not None:
                return pad.scheduled_launch
        return None


@dataclass
class GameState:
    phase: Phase = Phase.LOBBY
    season: Season = Season.SPRING
    year: int = 1957
    players: list[Player] = field(default_factory=list)
    log: list[str] = field(default_factory=list)
    winner: Side | None = None
    first_completed: dict[str, str] = field(default_factory=dict)
    # first_completed maps MissionId.value -> Side.value of the first player to succeed.
    last_launches: list["LaunchReport"] = field(default_factory=list)
    # Populated by resolve_turn(); cleared at the start of each resolution.
    # Clients read this to animate the launch-sequence screens before returning
    # to the hub. Entries are ordered as the launches were resolved.
    # Phase I — seasonal news. current_news is the human-readable headline
    # for the active season; current_news_id is the machine-readable card id
    # so UIs can render icons / colour-code by event type if desired.
    current_news: str = ""
    current_news_id: str = ""
    # Phase L — Museum.
    # mission_history: every launch ever resolved this game, in launch
    # order. prestige_timeline: one snapshot per season so the museum
    # can plot a line chart.
    mission_history: list["MissionHistoryEntry"] = field(default_factory=list)
    prestige_timeline: list["PrestigeSnapshot"] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> GameState:
        players = [_player_from_dict(p) for p in d.get("players", [])]
        raw_launches = d.get("last_launches") or []
        last_launches = [_launch_report_from_dict(r) for r in raw_launches]
        raw_history = d.get("mission_history") or []
        raw_timeline = d.get("prestige_timeline") or []
        return cls(
            phase=Phase(d["phase"]),
            season=Season(d["season"]),
            year=d["year"],
            players=players,
            log=list(d.get("log", [])),
            winner=Side(d["winner"]) if d.get("winner") else None,
            first_completed=dict(d.get("first_completed", {})),
            last_launches=last_launches,
            current_news=d.get("current_news", ""),
            current_news_id=d.get("current_news_id", ""),
            mission_history=[_mission_history_from_dict(m) for m in raw_history],
            prestige_timeline=[_prestige_snapshot_from_dict(s) for s in raw_timeline],
        )

    def find_player(self, player_id: str) -> Player | None:
        return next((p for p in self.players if p.player_id == player_id), None)

    def other_player(self, player_id: str) -> Player | None:
        return next((p for p in self.players if p.player_id != player_id), None)


def _player_from_dict(d: dict[str, Any]) -> Player:
    data = dict(d)
    side = data.get("side")
    data["side"] = Side(side) if side else None
    raw_astronauts = data.get("astronauts") or []
    data["astronauts"] = [_astronaut_from_dict(a) for a in raw_astronauts]
    # Phase E migration. If the state dict carries a 'pads' list, rehydrate
    # it; otherwise construct defaults and fold any legacy single-slot
    # `scheduled_launch` into pad A.
    raw_pads = data.pop("pads", None)
    legacy_scheduled = data.pop("scheduled_launch", None)
    if raw_pads is not None:
        data["pads"] = [_launch_pad_from_dict(p) for p in raw_pads]
    else:
        pads = _default_pads()
        if legacy_scheduled is not None:
            pads[0].scheduled_launch = _scheduled_launch_from_dict(legacy_scheduled)
        data["pads"] = pads
    # Phase D — older state dicts didn't carry these yet. Default recon
    # to the LUNAR_RECON_BASE so mid-game saves keep making sense.
    data.setdefault("lunar_recon", LUNAR_RECON_BASE)
    data.setdefault("lm_points", 0)
    # Phase J — legacy saves predate recruitment groups. Assume they've
    # only hired group 1 (starting roster), so group 2 is next.
    data.setdefault("next_recruitment_group", 2)
    # Phase H — rehydrate the intel snapshot dict into the dataclass,
    # and backfill legacy saves that never knew about intel at all.
    raw_intel = data.pop("latest_intel", None)
    data["latest_intel"] = (
        _intel_report_from_dict(raw_intel) if raw_intel else None
    )
    data.setdefault("intel_requested_on", "")
    # Phase M — legacy saves predate Government Review.
    data.setdefault("warnings", 0)
    data.setdefault("last_review_year", 0)
    return Player(**data)


def _intel_report_from_dict(d: dict[str, Any]) -> IntelReport:
    data = dict(d)
    raw_est = data.get("rocket_estimates") or {}
    data["rocket_estimates"] = {
        k: tuple(v) if isinstance(v, (list, tuple)) else (v, v)
        for k, v in raw_est.items()
    }
    data.setdefault("rumored_mission", "")
    data.setdefault("rumored_mission_name", "")
    data.setdefault("active_crew_count", 0)
    return IntelReport(**data)


def _astronaut_from_dict(d: dict[str, Any]) -> Astronaut:
    """Tolerant parser: legacy state dicts stored a single 'command' skill;
    the 5-skill model splits that into lm_pilot + docking. Map the old
    value onto docking (closest analogue — orbital-ops commander) and
    default lm_pilot to 0 when it's missing. Also backfill Phase C
    training / hospital fields with zero for older saves."""
    data = dict(d)
    legacy_command = data.pop("command", None)
    if legacy_command is not None and "docking" not in data:
        data["docking"] = legacy_command
    data.setdefault("lm_pilot", 0)
    data.setdefault("docking", 0)
    data.setdefault("basic_training_remaining", 0)
    data.setdefault("advanced_training_skill", "")
    data.setdefault("advanced_training_remaining", 0)
    data.setdefault("hospital_remaining", 0)
    data.setdefault("compatibility", Compatibility.A.value)
    data.setdefault("mood", MOOD_DEFAULT)
    return Astronaut(**data)


@dataclass
class ObjectiveReport:
    """One opt-in objective's outcome within a LaunchReport."""
    objective_id: str       # ObjectiveId.value
    name: str
    performer: str = ""     # astronaut name who attempted it
    effective_success: float = 0.0
    success: bool = False
    prestige_delta: int = 0
    deaths: list[str] = field(default_factory=list)
    ship_lost: bool = False
    skipped: bool = False
    skip_reason: str = ""


@dataclass
class LaunchReport:
    """Everything the client needs to animate a single mission resolution:
    who, what, the pre-roll odds, the outcome, and all downstream effects
    (prestige, crew deaths, budget cut, objective-by-objective details)."""
    side: str               # Side.value, or "" if unassigned
    username: str
    mission_id: str         # MissionId.value
    mission_name: str
    rocket: str             # side-aware display name (e.g. "Saturn V")
    rocket_class: str       # Rocket.value (e.g. "Heavy")
    manned: bool = False
    crew: list[str] = field(default_factory=list)
    launch_cost: int = 0
    base_success: float = 0.0
    crew_bonus: float = 0.0
    reliability_bonus: float = 0.0
    effective_success: float = 0.0
    aborted: bool = False
    abort_reason: str = ""
    success: bool = False
    prestige_delta: int = 0   # total net prestige change from this launch
    first_claimed: bool = False
    reliability_before: int = 0
    reliability_after: int = 0
    deaths: list[str] = field(default_factory=list)
    budget_cut: int = 0
    ended_game: bool = False  # manned lunar landing success
    # Phase D — manned-lunar-landing only; 0 for everything else.
    compat_bonus: float = 0.0
    lunar_recon_bonus: float = 0.0
    lm_points_penalty: float = 0.0
    objectives: list[ObjectiveReport] = field(default_factory=list)


def _launch_report_from_dict(d: dict[str, Any]) -> LaunchReport:
    data = dict(d)
    raw_objs = data.get("objectives") or []
    data["objectives"] = [ObjectiveReport(**o) for o in raw_objs]
    return LaunchReport(**data)


# ----------------------------------------------------------------------
# Phase L — Museum: mission history + per-season prestige timeline
# ----------------------------------------------------------------------


@dataclass
class MissionHistoryEntry:
    """One permanent line in the in-game museum: what flew, when, for
    whom, with what crew, and how it ended. Appended during resolve_turn
    right after each LaunchReport is finalized; kept in launch order."""
    year: int
    season: str               # Season.value when the launch resolved
    side: str                 # Side.value of the launching player
    mission_id: str           # MissionId.value
    mission_name: str
    rocket: str               # side-aware display name
    manned: bool = False
    crew: list[str] = field(default_factory=list)
    success: bool = False
    prestige_delta: int = 0
    first_claimed: bool = False
    deaths: list[str] = field(default_factory=list)


@dataclass
class PrestigeSnapshot:
    """One (year, season) sample of both sides' prestige. Appended once
    per season advance so the museum can draw a timeline."""
    year: int
    season: str
    usa_prestige: int = 0
    ussr_prestige: int = 0


def _mission_history_from_dict(d: dict[str, Any]) -> MissionHistoryEntry:
    data = dict(d)
    data.setdefault("manned", False)
    data.setdefault("crew", [])
    data.setdefault("success", False)
    data.setdefault("prestige_delta", 0)
    data.setdefault("first_claimed", False)
    data.setdefault("deaths", [])
    return MissionHistoryEntry(**data)


def _prestige_snapshot_from_dict(d: dict[str, Any]) -> PrestigeSnapshot:
    data = dict(d)
    data.setdefault("usa_prestige", 0)
    data.setdefault("ussr_prestige", 0)
    return PrestigeSnapshot(**data)


@dataclass
class ScheduledLaunch:
    """A mission the player committed to last turn; it's in the VAB,
    partially paid for (assembly_cost already deducted), and will actually
    fly on the NEXT resolve. `architecture` and `objectives` are snapshots
    at schedule time — changing them after scheduling has no effect on the
    imminent flight."""
    mission_id: str          # MissionId.value
    rocket_class: str        # Rocket.value at schedule time (pre-arch override)
    launch_cost_total: int   # full cost this mission will need across both turns
    assembly_cost_paid: int  # portion already deducted at schedule time
    launch_cost_remaining: int  # portion still due at launch-resolve time
    objectives: list[str]    # ObjectiveId.values frozen at schedule time
    architecture: str | None = None
    scheduled_year: int = 0
    scheduled_season: str = ""


def _scheduled_launch_from_dict(d: dict[str, Any] | None) -> ScheduledLaunch | None:
    if d is None:
        return None
    data = dict(d)
    data.setdefault("objectives", [])
    return ScheduledLaunch(**data)


@dataclass
class LaunchPad:
    """One of the player's launch pads (A/B/C). Holds at most one
    ScheduledLaunch and carries a repair counter that ticks down each
    resolve after a catastrophic failure knocks the pad out."""
    pad_id: str
    scheduled_launch: "ScheduledLaunch | None" = None
    repair_turns_remaining: int = 0

    @property
    def damaged(self) -> bool:
        return self.repair_turns_remaining > 0

    @property
    def available(self) -> bool:
        """True iff the pad can accept a new ScheduledLaunch right now."""
        return self.scheduled_launch is None and not self.damaged


def _launch_pad_from_dict(d: dict[str, Any]) -> LaunchPad:
    data = dict(d)
    data["scheduled_launch"] = _scheduled_launch_from_dict(data.get("scheduled_launch"))
    data.setdefault("repair_turns_remaining", 0)
    return LaunchPad(**data)


def _default_pads() -> list[LaunchPad]:
    return [LaunchPad(pad_id=name) for name in PAD_NAMES]


SEASON_ORDER = [Season.SPRING, Season.SUMMER, Season.FALL, Season.WINTER]


def next_season(current: Season, year: int) -> tuple[Season, int]:
    idx = SEASON_ORDER.index(current)
    if idx == len(SEASON_ORDER) - 1:
        return SEASON_ORDER[0], year + 1
    return SEASON_ORDER[idx + 1], year
