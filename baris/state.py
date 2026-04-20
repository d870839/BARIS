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


class Skill(str, Enum):
    CAPSULE = "capsule"
    EVA = "eva"
    ENDURANCE = "endurance"
    COMMAND = "command"


class AstronautStatus(str, Enum):
    ACTIVE = "active"
    KIA = "kia"


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
            tier=ProgramTier.TWO, manned=True, crew_size=2, primary_skill=Skill.EVA),
    Mission(MissionId.LUNAR_PASS,           "Lunar flyby",          Rocket.MEDIUM,12, 0.60, 10, 3,  5,
            tier=ProgramTier.TWO),
    Mission(MissionId.LUNAR_ORBIT,          "Lunar orbit",          Rocket.HEAVY, 18, 0.50, 15, 4,  7,
            tier=ProgramTier.TWO),
    # Tier 3 — Apollo / Soyuz
    Mission(MissionId.LUNAR_LANDING,        "Lunar landing",        Rocket.HEAVY, 25, 0.35, 20, 5, 10,
            tier=ProgramTier.THREE),
    Mission(MissionId.MANNED_LUNAR_ORBIT,   "Manned lunar orbit",   Rocket.HEAVY, 25, 0.40, 20, 6,  9,
            tier=ProgramTier.THREE, manned=True, crew_size=2, primary_skill=Skill.COMMAND),
    Mission(MissionId.MANNED_LUNAR_LANDING, "Manned lunar landing", Rocket.HEAVY, 35, 0.25, 35, 8, 15,
            tier=ProgramTier.THREE, manned=True, crew_size=3, primary_skill=Skill.COMMAND),
)

MISSIONS_BY_ID: dict[MissionId, Mission] = {m.id: m for m in MISSIONS}

RD_TARGETS: dict[Rocket, int] = {
    Rocket.LIGHT: 60,
    Rocket.MEDIUM: 120,
    Rocket.HEAVY: 200,
}

STARTING_BUDGET = 30
SEASON_REFILL = 15
PRESTIGE_TO_WIN = 40
STARTING_ASTRONAUTS = 7
DEATH_CHANCE_ON_FAIL = 0.25
DEATH_PRESTIGE_PENALTY = 3

# Historical starting rosters (last names, in selection-group order).
# USA: Mercury Seven (selected 1959).
# USSR: first-group cosmonauts (1960) plus Tereshkova (first female cosmonaut, 1962).
HISTORICAL_ROSTERS: dict[str, tuple[str, ...]] = {
    Side.USA.value: (
        "Shepard", "Grissom", "Glenn", "Carpenter",
        "Schirra", "Cooper", "Slayton",
    ),
    Side.USSR.value: (
        "Gagarin", "Titov", "Tereshkova", "Komarov",
        "Leonov", "Nikolayev", "Popovich",
    ),
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

# Rocket safety: per-player reliability rating per rocket class.
# Affects mission success. Grows on success, drops on failure.
SAFETY_FLOOR = 20          # failed rockets can't drop below this
SAFETY_CAP = 95            # you can never fully trust a rocket
SAFETY_ON_RD_COMPLETE = 40 # fresh rockets start unreliable
SAFETY_GAIN_ON_SUCCESS = 5
SAFETY_LOSS_ON_FAIL = 10
# Safety contributes ±10% to success around the neutral value of 50.
# effective = base + crew_bonus + (safety - 50) * SAFETY_SWING_PER_POINT
SAFETY_SWING_PER_POINT = 0.002


@dataclass
class Astronaut:
    id: str
    name: str
    capsule: int = 0
    eva: int = 0
    endurance: int = 0
    command: int = 0
    status: str = AstronautStatus.ACTIVE.value  # stored as string for JSON safety

    def skill(self, kind: Skill) -> int:
        return getattr(self, kind.value)

    def bump_skill(self, kind: Skill, amount: int) -> None:
        value = min(100, max(0, self.skill(kind) + amount))
        setattr(self, kind.value, value)

    @property
    def active(self) -> bool:
        return self.status == AstronautStatus.ACTIVE.value


@dataclass
class Player:
    player_id: str
    username: str
    side: Side | None = None
    budget: int = STARTING_BUDGET
    prestige: int = 0
    ready: bool = False
    rockets: dict[str, int] = field(
        default_factory=lambda: {r.value: 0 for r in Rocket}
    )
    rocket_safety: dict[str, int] = field(
        default_factory=lambda: {r.value: 0 for r in Rocket}
    )
    astronauts: list[Astronaut] = field(default_factory=list)
    mission_successes: dict[str, int] = field(default_factory=dict)
    architecture: str | None = None  # Architecture.value once chosen, else None
    turn_submitted: bool = False
    pending_rd_rocket: str | None = None   # Rocket.value or None
    pending_rd_spend: int = 0
    pending_launch: str | None = None      # MissionId.value or None

    def rd_progress(self, rocket: Rocket) -> int:
        return self.rockets.get(rocket.value, 0)

    def rocket_built(self, rocket: Rocket) -> bool:
        return self.rd_progress(rocket) >= RD_TARGETS[rocket]

    def safety(self, rocket: Rocket) -> int:
        return self.rocket_safety.get(rocket.value, 0)

    def active_astronauts(self) -> list[Astronaut]:
        return [a for a in self.astronauts if a.active]

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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> GameState:
        players = [_player_from_dict(p) for p in d.get("players", [])]
        return cls(
            phase=Phase(d["phase"]),
            season=Season(d["season"]),
            year=d["year"],
            players=players,
            log=list(d.get("log", [])),
            winner=Side(d["winner"]) if d.get("winner") else None,
            first_completed=dict(d.get("first_completed", {})),
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
    data["astronauts"] = [Astronaut(**a) for a in raw_astronauts]
    return Player(**data)


SEASON_ORDER = [Season.SPRING, Season.SUMMER, Season.FALL, Season.WINTER]


def next_season(current: Season, year: int) -> tuple[Season, int]:
    idx = SEASON_ORDER.index(current)
    if idx == len(SEASON_ORDER) - 1:
        return SEASON_ORDER[0], year + 1
    return SEASON_ORDER[idx + 1], year
