from __future__ import annotations

from baris.resolver import (
    all_turns_in,
    available_missions,
    can_start,
    resolve_turn,
    start_game,
    submit_turn,
)
from baris.state import (
    GameState,
    MissionId,
    Phase,
    Player,
    RD_TARGETS,
    Rocket,
    Season,
    Side,
)


class _FixedRng:
    def __init__(self, value: float) -> None:
        self.value = value

    def random(self) -> float:
        return self.value


def _two_player_state() -> GameState:
    state = GameState()
    state.players = [
        Player(player_id="a", username="Alice", side=Side.USA, ready=True),
        Player(player_id="b", username="Bob", side=Side.USSR, ready=True),
    ]
    return state


# ----------------------------------------------------------------------
# lobby / start
# ----------------------------------------------------------------------


def test_can_start_requires_both_sides_and_ready() -> None:
    state = _two_player_state()
    assert can_start(state)

    state.players[0].ready = False
    assert not can_start(state)

    state.players[0].ready = True
    state.players[1].side = Side.USA
    assert not can_start(state)


# ----------------------------------------------------------------------
# R&D
# ----------------------------------------------------------------------


def test_rd_accumulates_on_chosen_rocket() -> None:
    state = _two_player_state()
    start_game(state)
    submit_turn(state.players[0], rd_rocket=Rocket.LIGHT, rd_spend=20, launch=None)
    submit_turn(state.players[1], rd_rocket=Rocket.MEDIUM, rd_spend=20, launch=None)
    assert all_turns_in(state)

    resolve_turn(state)

    assert state.players[0].rd_progress(Rocket.LIGHT) == 20
    assert state.players[0].rd_progress(Rocket.MEDIUM) == 0
    assert state.players[1].rd_progress(Rocket.MEDIUM) == 20
    assert state.season == Season.SUMMER


def test_rd_spend_clamped_to_budget() -> None:
    state = _two_player_state()
    start_game(state)
    me = state.players[0]
    me.budget = 5
    submit_turn(me, rd_rocket=Rocket.LIGHT, rd_spend=999, launch=None)
    assert me.pending_rd_spend == 5


def test_rocket_built_when_progress_reaches_target() -> None:
    state = _two_player_state()
    start_game(state)
    me = state.players[0]
    me.budget = 200
    submit_turn(me, rd_rocket=Rocket.LIGHT, rd_spend=RD_TARGETS[Rocket.LIGHT], launch=None)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state)
    assert me.rocket_built(Rocket.LIGHT)


# ----------------------------------------------------------------------
# Launches
# ----------------------------------------------------------------------


def test_launch_requires_built_rocket() -> None:
    state = _two_player_state()
    start_game(state)
    me = state.players[0]
    # tries to launch lunar landing without a Heavy rocket
    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.LUNAR_LANDING)
    # submit_turn drops the launch if prereqs unmet
    assert me.pending_launch is None


def test_suborbital_success_awards_prestige_and_first_bonus() -> None:
    state = _two_player_state()
    start_game(state)
    me = state.players[0]
    me.rockets[Rocket.LIGHT.value] = RD_TARGETS[Rocket.LIGHT]

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.SUBORBITAL)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=_FixedRng(0.0))  # forced success

    # suborbital: 3 prestige + 2 first-bonus
    assert me.prestige == 5
    assert state.first_completed[MissionId.SUBORBITAL.value] == Side.USA.value


def test_second_suborbital_does_not_regrant_first_bonus() -> None:
    state = _two_player_state()
    start_game(state)
    me = state.players[0]
    opp = state.players[1]
    me.rockets[Rocket.LIGHT.value] = RD_TARGETS[Rocket.LIGHT]
    opp.rockets[Rocket.LIGHT.value] = RD_TARGETS[Rocket.LIGHT]

    # both launch same mission same turn; USA first alphabetically (player order).
    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.SUBORBITAL)
    submit_turn(opp, rd_rocket=None, rd_spend=0, launch=MissionId.SUBORBITAL)
    resolve_turn(state, rng=_FixedRng(0.0))  # both succeed

    # USA goes first → claims the +2 first bonus. USSR gets base prestige only.
    assert me.prestige == 5
    assert opp.prestige == 3
    assert state.first_completed[MissionId.SUBORBITAL.value] == Side.USA.value


def test_launch_failure_costs_prestige() -> None:
    state = _two_player_state()
    start_game(state)
    me = state.players[0]
    me.rockets[Rocket.LIGHT.value] = RD_TARGETS[Rocket.LIGHT]
    me.prestige = 5

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.SUBORBITAL)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=_FixedRng(0.99))  # forced failure

    # suborbital: -1 prestige on fail
    assert me.prestige == 4
    assert state.phase == Phase.PLAYING


def test_lunar_landing_ends_game() -> None:
    state = _two_player_state()
    start_game(state)
    me = state.players[0]
    me.rockets[Rocket.HEAVY.value] = RD_TARGETS[Rocket.HEAVY]
    me.budget = 100

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.LUNAR_LANDING)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=_FixedRng(0.0))

    assert state.phase == Phase.ENDED
    assert state.winner == Side.USA


def test_prestige_cap_can_win() -> None:
    state = _two_player_state()
    start_game(state)
    me = state.players[0]
    me.prestige = 38
    me.rockets[Rocket.LIGHT.value] = RD_TARGETS[Rocket.LIGHT]

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.SUBORBITAL)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=_FixedRng(0.0))

    assert state.phase == Phase.ENDED
    assert state.winner == Side.USA


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def test_available_missions_filters_by_rocket_and_budget() -> None:
    me = Player(player_id="a", username="Alice", side=Side.USA)
    me.budget = 50
    me.rockets[Rocket.LIGHT.value] = RD_TARGETS[Rocket.LIGHT]

    avail = available_missions(me)
    avail_ids = {m.id for m in avail}
    # Light is built, so suborbital + satellite should be available.
    assert MissionId.SUBORBITAL in avail_ids
    assert MissionId.SATELLITE in avail_ids
    # Medium not built → orbital & flyby excluded.
    assert MissionId.ORBITAL not in avail_ids


# ----------------------------------------------------------------------
# Serialization
# ----------------------------------------------------------------------


def test_state_roundtrip_preserves_enum_and_rockets() -> None:
    state = _two_player_state()
    state.players[0].rockets[Rocket.LIGHT.value] = 30
    state.first_completed[MissionId.SUBORBITAL.value] = Side.USA.value
    restored = GameState.from_dict(state.to_dict())

    for p in restored.players:
        assert isinstance(p.side, Side)
    assert restored.players[0].rd_progress(Rocket.LIGHT) == 30
    assert restored.first_completed[MissionId.SUBORBITAL.value] == Side.USA.value
