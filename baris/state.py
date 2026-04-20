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


class MissionId(str, Enum):
    SUBORBITAL = "suborbital"
    SATELLITE = "satellite"
    ORBITAL = "orbital"
    LUNAR_PASS = "lunar_pass"
    LUNAR_ORBIT = "lunar_orbit"
    LUNAR_LANDING = "lunar_landing"


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


# Ordered catalog — UI iterates this to build the mission list (indices map to keys 1-6).
MISSIONS: tuple[Mission, ...] = (
    Mission(MissionId.SUBORBITAL,    "Sub-orbital flight", Rocket.LIGHT,  3, 0.85,  3, 1, 2),
    Mission(MissionId.SATELLITE,     "Satellite launch",   Rocket.LIGHT,  5, 0.75,  5, 2, 3),
    Mission(MissionId.ORBITAL,       "Orbital flight",     Rocket.MEDIUM, 8, 0.70,  7, 2, 4),
    Mission(MissionId.LUNAR_PASS,    "Lunar flyby",        Rocket.MEDIUM,12, 0.60, 10, 3, 5),
    Mission(MissionId.LUNAR_ORBIT,   "Lunar orbit",        Rocket.HEAVY, 18, 0.50, 15, 4, 7),
    Mission(MissionId.LUNAR_LANDING, "Lunar landing",      Rocket.HEAVY, 25, 0.35, 25, 5, 10),
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
    turn_submitted: bool = False
    pending_rd_rocket: str | None = None   # Rocket.value or None
    pending_rd_spend: int = 0
    pending_launch: str | None = None      # MissionId.value or None

    def rd_progress(self, rocket: Rocket) -> int:
        return self.rockets.get(rocket.value, 0)

    def rocket_built(self, rocket: Rocket) -> bool:
        return self.rd_progress(rocket) >= RD_TARGETS[rocket]


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
    # rockets dict keys are rocket-name strings, keep as-is
    return Player(**data)


SEASON_ORDER = [Season.SPRING, Season.SUMMER, Season.FALL, Season.WINTER]


def next_season(current: Season, year: int) -> tuple[Season, int]:
    idx = SEASON_ORDER.index(current)
    if idx == len(SEASON_ORDER) - 1:
        return SEASON_ORDER[0], year + 1
    return SEASON_ORDER[idx + 1], year
