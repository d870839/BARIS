from __future__ import annotations

import random

from baris.resolver import (
    all_turns_in,
    can_start,
    resolve_turn,
    start_game,
    submit_turn,
)
from baris.state import GameState, Phase, Player, Season, Side


def _two_player_state() -> GameState:
    state = GameState()
    state.players = [
        Player(player_id="a", username="Alice", side=Side.USA, ready=True),
        Player(player_id="b", username="Bob", side=Side.USSR, ready=True),
    ]
    return state


def test_can_start_requires_both_sides_and_ready() -> None:
    state = _two_player_state()
    assert can_start(state)

    state.players[0].ready = False
    assert not can_start(state)

    state.players[0].ready = True
    state.players[1].side = Side.USA
    assert not can_start(state)


def test_resolve_turn_applies_rd_and_advances_season() -> None:
    state = _two_player_state()
    start_game(state)
    assert state.phase == Phase.PLAYING
    assert state.season == Season.SPRING

    submit_turn(state.players[0], rd_spend=10, launch=False)
    submit_turn(state.players[1], rd_spend=20, launch=False)
    assert all_turns_in(state)

    resolve_turn(state, rng=random.Random(0))

    assert state.players[0].rd_progress == 10
    assert state.players[1].rd_progress == 20
    assert state.season == Season.SUMMER
    assert all(not p.turn_submitted for p in state.players)


def test_rd_spend_clamped_to_budget() -> None:
    state = _two_player_state()
    start_game(state)
    me = state.players[0]
    me.budget = 5

    submit_turn(me, rd_spend=999, launch=False)
    assert me.pending_rd_spend == 5


class _FixedRng:
    def __init__(self, value: float) -> None:
        self.value = value

    def random(self) -> float:
        return self.value


def test_launch_success_can_complete_game() -> None:
    state = _two_player_state()
    start_game(state)
    me = state.players[0]
    opp = state.players[1]
    me.rocket_built = True
    me.prestige = 8  # need 10 to win; success gives +3

    submit_turn(me, rd_spend=0, launch=True)
    submit_turn(opp, rd_spend=0, launch=False)
    resolve_turn(state, rng=_FixedRng(0.0))  # forced success

    assert me.prestige >= 10
    assert state.phase == Phase.ENDED
    assert state.winner == Side.USA


def test_launch_failure_costs_prestige() -> None:
    state = _two_player_state()
    start_game(state)
    me = state.players[0]
    opp = state.players[1]
    me.rocket_built = True
    me.prestige = 5

    submit_turn(me, rd_spend=0, launch=True)
    submit_turn(opp, rd_spend=0, launch=False)
    resolve_turn(state, rng=_FixedRng(0.99))  # forced failure

    assert me.prestige == 4
    assert state.phase == Phase.PLAYING


def test_state_roundtrip_dict() -> None:
    state = _two_player_state()
    state.log.append("hello")
    encoded = state.to_dict()
    restored = GameState.from_dict(encoded)

    assert restored.players[0].username == "Alice"
    assert restored.players[1].side == Side.USSR
    assert restored.log == ["hello"]
    assert restored.phase == Phase.LOBBY
