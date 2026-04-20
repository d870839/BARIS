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


STARTING_BUDGET = 30
RD_COST_PER_POINT = 1
RD_TARGET = 100
PRESTIGE_TO_WIN = 10


@dataclass
class Player:
    player_id: str
    username: str
    side: Side | None = None
    budget: int = STARTING_BUDGET
    prestige: int = 0
    ready: bool = False
    rd_progress: int = 0
    rocket_built: bool = False
    turn_submitted: bool = False
    pending_rd_spend: int = 0
    pending_launch: bool = False


@dataclass
class GameState:
    phase: Phase = Phase.LOBBY
    season: Season = Season.SPRING
    year: int = 1957
    players: list[Player] = field(default_factory=list)
    log: list[str] = field(default_factory=list)
    winner: Side | None = None

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
        )

    def find_player(self, player_id: str) -> Player | None:
        return next((p for p in self.players if p.player_id == player_id), None)

    def other_player(self, player_id: str) -> Player | None:
        return next((p for p in self.players if p.player_id != player_id), None)


def _player_from_dict(d: dict[str, Any]) -> Player:
    data = dict(d)
    side = data.get("side")
    data["side"] = Side(side) if side else None
    return Player(**data)


SEASON_ORDER = [Season.SPRING, Season.SUMMER, Season.FALL, Season.WINTER]


def next_season(current: Season, year: int) -> tuple[Season, int]:
    idx = SEASON_ORDER.index(current)
    if idx == len(SEASON_ORDER) - 1:
        return SEASON_ORDER[0], year + 1
    return SEASON_ORDER[idx + 1], year
