from __future__ import annotations

import random

from baris.resolver import (
    _crew_bonus,
    _select_crew,
    all_turns_in,
    available_missions,
    can_start,
    resolve_turn,
    start_game,
    submit_turn,
)
from baris.state import (
    Astronaut,
    AstronautStatus,
    CREW_MAX_BONUS,
    GameState,
    MISSIONS_BY_ID,
    MissionId,
    Phase,
    Player,
    RD_TARGETS,
    Rocket,
    SAFETY_CAP,
    SAFETY_FLOOR,
    SAFETY_GAIN_ON_SUCCESS,
    SAFETY_LOSS_ON_FAIL,
    SAFETY_ON_RD_COMPLETE,
    Season,
    Side,
    Skill,
    STARTING_ASTRONAUTS,
)


class _FixedRng:
    """Minimal stub: .random() returns a preset value, .randint/.choice use an inner Random."""

    def __init__(self, value: float, seed: int = 1) -> None:
        self.value = value
        self._r = random.Random(seed)

    def random(self) -> float:
        return self.value

    def randint(self, a: int, b: int) -> int:
        return self._r.randint(a, b)

    def choice(self, seq):
        return self._r.choice(seq)


def _two_player_state() -> GameState:
    state = GameState()
    state.players = [
        Player(player_id="a", username="Alice", side=Side.USA, ready=True),
        Player(player_id="b", username="Bob", side=Side.USSR, ready=True),
    ]
    return state


def _make_astronaut(name: str, **skills: int) -> Astronaut:
    return Astronaut(
        id=name,
        name=name,
        capsule=skills.get("capsule", 0),
        eva=skills.get("eva", 0),
        endurance=skills.get("endurance", 0),
        command=skills.get("command", 0),
    )


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


def test_start_game_generates_starting_roster() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(42))
    for p in state.players:
        assert len(p.astronauts) == STARTING_ASTRONAUTS
        for astro in p.astronauts:
            assert astro.status == AstronautStatus.ACTIVE.value
            assert 0 < astro.capsule <= 100  # within generator's 20-50 band
            assert astro.name.startswith(p.side.value)


# ----------------------------------------------------------------------
# R&D
# ----------------------------------------------------------------------


def test_rd_accumulates_on_chosen_rocket() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
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
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.budget = 5
    submit_turn(me, rd_rocket=Rocket.LIGHT, rd_spend=999, launch=None)
    assert me.pending_rd_spend == 5


# ----------------------------------------------------------------------
# Unmanned launches
# ----------------------------------------------------------------------


def test_launch_requires_built_rocket() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.LUNAR_LANDING)
    assert me.pending_launch is None


def test_suborbital_success_awards_first_bonus() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.rockets[Rocket.LIGHT.value] = RD_TARGETS[Rocket.LIGHT]

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.SUBORBITAL)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=_FixedRng(0.0))

    assert me.prestige == 5  # 3 base + 2 first
    assert state.first_completed[MissionId.SUBORBITAL.value] == Side.USA.value


def test_second_suborbital_does_not_regrant_first_bonus() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    opp = state.players[1]
    me.rockets[Rocket.LIGHT.value] = RD_TARGETS[Rocket.LIGHT]
    opp.rockets[Rocket.LIGHT.value] = RD_TARGETS[Rocket.LIGHT]

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.SUBORBITAL)
    submit_turn(opp, rd_rocket=None, rd_spend=0, launch=MissionId.SUBORBITAL)
    resolve_turn(state, rng=_FixedRng(0.0))

    assert me.prestige == 5
    assert opp.prestige == 3
    assert state.first_completed[MissionId.SUBORBITAL.value] == Side.USA.value


# ----------------------------------------------------------------------
# Manned launches
# ----------------------------------------------------------------------


def test_manned_mission_rejected_without_enough_crew() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.rockets[Rocket.HEAVY.value] = RD_TARGETS[Rocket.HEAVY]
    me.budget = 100
    # kill all but 2 astronauts — landing needs 3
    for a in me.astronauts[:3]:
        a.status = AstronautStatus.KIA.value
    assert len(me.active_astronauts()) == 2

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.MANNED_LUNAR_LANDING)
    assert me.pending_launch is None


def test_select_crew_picks_top_skilled_by_primary() -> None:
    me = Player(player_id="a", username="Alice", side=Side.USA)
    me.astronauts = [
        _make_astronaut("A", command=10),
        _make_astronaut("B", command=90),
        _make_astronaut("C", command=50),
        _make_astronaut("D", command=70),
    ]
    mission = MISSIONS_BY_ID[MissionId.MANNED_LUNAR_ORBIT]  # crew_size=2, primary=Command
    crew = _select_crew(me, mission)
    assert crew is not None
    assert [a.name for a in crew] == ["B", "D"]


def test_crew_bonus_scales_with_primary_skill() -> None:
    mission = MISSIONS_BY_ID[MissionId.MANNED_LUNAR_LANDING]
    crew_max = [_make_astronaut(f"X{i}", command=100) for i in range(mission.crew_size)]
    crew_zero = [_make_astronaut(f"Y{i}", command=0) for i in range(mission.crew_size)]
    crew_half = [_make_astronaut(f"Z{i}", command=50) for i in range(mission.crew_size)]

    assert _crew_bonus(crew_zero, mission) == 0.0
    assert abs(_crew_bonus(crew_max, mission) - CREW_MAX_BONUS) < 1e-9
    assert abs(_crew_bonus(crew_half, mission) - CREW_MAX_BONUS / 2) < 1e-9


def test_manned_landing_success_ends_game() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.rockets[Rocket.HEAVY.value] = RD_TARGETS[Rocket.HEAVY]
    me.budget = 100
    for a in me.astronauts:
        a.command = 100

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.MANNED_LUNAR_LANDING)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=_FixedRng(0.0))

    assert state.phase == Phase.ENDED
    assert state.winner == Side.USA


def test_unmanned_landing_only_awards_prestige() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.rockets[Rocket.HEAVY.value] = RD_TARGETS[Rocket.HEAVY]
    me.budget = 100

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.LUNAR_LANDING)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=_FixedRng(0.0))

    # unmanned landing: 20 + 10 first bonus = 30 (game does NOT end on unmanned)
    assert me.prestige == 30
    assert state.phase == Phase.PLAYING


def test_manned_failure_can_kill_crew() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.rockets[Rocket.MEDIUM.value] = RD_TARGETS[Rocket.MEDIUM]
    me.budget = 100
    me.prestige = 20
    for a in me.astronauts:
        a.capsule = 50

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.MANNED_ORBITAL)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    # failure (high roll), and the death roll beneath DEATH_CHANCE_ON_FAIL.
    # _FixedRng.random() always returns the same value — so we need one > success and < death_chance.
    # Trick: use a value > 0.85 (fails all missions) but the death check also uses .random()
    # which returns the same 0.99 → crew survives. So this test just verifies failure path
    # without death.
    resolve_turn(state, rng=_FixedRng(0.99))

    assert me.prestige == 16  # 20 - 4 (manned_orbital prestige_fail)
    # Crew all survive at roll 0.99 > 0.25.
    assert len(me.active_astronauts()) == STARTING_ASTRONAUTS


def test_manned_failure_with_low_death_roll_kills_crew() -> None:
    """Use a sequence-based RNG so success roll high, death roll low."""

    class _SeqRng:
        def __init__(self, values):
            self.values = list(values)
            self._r = random.Random(1)

        def random(self) -> float:
            return self.values.pop(0)

        def randint(self, a: int, b: int) -> int:
            return self._r.randint(a, b)

        def choice(self, seq):
            return self._r.choice(seq)

    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.rockets[Rocket.MEDIUM.value] = RD_TARGETS[Rocket.MEDIUM]
    me.budget = 100
    me.prestige = 20
    for a in me.astronauts:
        a.capsule = 50

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.MANNED_ORBITAL)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)

    # manned_orbital: crew_size=1. Sequence: success roll high (fail), death roll low (dies).
    resolve_turn(state, rng=_SeqRng([0.99, 0.01]))

    # 20 - 4 (fail) - 3 (KIA) = 13
    assert me.prestige == 13
    assert len(me.active_astronauts()) == STARTING_ASTRONAUTS - 1


# ----------------------------------------------------------------------
# Passive training
# ----------------------------------------------------------------------


def test_passive_training_raises_skills_each_turn() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(7))
    me = state.players[0]
    before = [(a.capsule, a.eva, a.endurance, a.command) for a in me.astronauts]

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=None)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=random.Random(7))

    after = [(a.capsule, a.eva, a.endurance, a.command) for a in me.astronauts]
    # every skill should have risen by at least 1 per astronaut
    for (c0, e0, n0, m0), (c1, e1, n1, m1) in zip(before, after):
        assert c1 >= c0 + 1
        assert e1 >= e0 + 1
        assert n1 >= n0 + 1
        assert m1 >= m0 + 1


# ----------------------------------------------------------------------
# Victory
# ----------------------------------------------------------------------


def test_prestige_cap_can_win() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.prestige = 38
    me.rockets[Rocket.LIGHT.value] = RD_TARGETS[Rocket.LIGHT]

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.SUBORBITAL)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=_FixedRng(0.0))

    assert state.phase == Phase.ENDED
    assert state.winner == Side.USA


# ----------------------------------------------------------------------
# Helpers / serialization
# ----------------------------------------------------------------------


def test_available_missions_respects_crew_requirement() -> None:
    me = Player(player_id="a", username="Alice", side=Side.USA)
    me.budget = 100
    me.rockets[Rocket.MEDIUM.value] = RD_TARGETS[Rocket.MEDIUM]
    # zero astronauts → manned_orbital not available
    avail = {m.id for m in available_missions(me)}
    assert MissionId.ORBITAL in avail
    assert MissionId.MANNED_ORBITAL not in avail

    me.astronauts = [_make_astronaut("X", capsule=50)]
    avail = {m.id for m in available_missions(me)}
    assert MissionId.MANNED_ORBITAL in avail


# ----------------------------------------------------------------------
# Rocket reliability / safety
# ----------------------------------------------------------------------


def test_rd_completion_seeds_initial_safety() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.budget = 200

    submit_turn(me, rd_rocket=Rocket.LIGHT, rd_spend=RD_TARGETS[Rocket.LIGHT], launch=None)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=_FixedRng(0.0))

    assert me.safety(Rocket.LIGHT) == SAFETY_ON_RD_COMPLETE
    # Medium/Heavy untouched.
    assert me.safety(Rocket.MEDIUM) == 0


def test_successful_launch_bumps_safety() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.rockets[Rocket.LIGHT.value] = RD_TARGETS[Rocket.LIGHT]
    me.rocket_safety[Rocket.LIGHT.value] = 50

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.SUBORBITAL)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=_FixedRng(0.0))

    assert me.safety(Rocket.LIGHT) == 50 + SAFETY_GAIN_ON_SUCCESS


def test_failed_launch_drops_safety_but_not_below_floor() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.rockets[Rocket.LIGHT.value] = RD_TARGETS[Rocket.LIGHT]
    me.rocket_safety[Rocket.LIGHT.value] = SAFETY_FLOOR + 3  # just above floor

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.SUBORBITAL)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=_FixedRng(0.99))  # forced failure

    # would be SAFETY_FLOOR+3 - 10 = below floor → clamped
    assert me.safety(Rocket.LIGHT) == SAFETY_FLOOR


def test_safety_cap_prevents_unbounded_growth() -> None:
    me = Player(player_id="a", username="Alice", side=Side.USA)
    me.rocket_safety[Rocket.LIGHT.value] = SAFETY_CAP - 1
    from baris.resolver import _bump_safety
    _bump_safety(me, Rocket.LIGHT, 50)
    assert me.safety(Rocket.LIGHT) == SAFETY_CAP


def test_high_safety_improves_effective_success() -> None:
    """Set safety very high and verify a mission succeeds on a roll that
    would fail at the base rate."""
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.rockets[Rocket.LIGHT.value] = RD_TARGETS[Rocket.LIGHT]
    me.rocket_safety[Rocket.LIGHT.value] = SAFETY_CAP  # 95 → +0.09 success bonus

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.SUBORBITAL)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    # base suborbital success 0.85; with safety +0.09 → 0.94. Roll 0.9 should succeed.
    resolve_turn(state, rng=_FixedRng(0.90))

    # base 3 + first bonus 2
    assert me.prestige == 5


def test_low_safety_worsens_effective_success() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.rockets[Rocket.LIGHT.value] = RD_TARGETS[Rocket.LIGHT]
    me.rocket_safety[Rocket.LIGHT.value] = SAFETY_FLOOR  # 20 → -0.06 success penalty
    me.prestige = 5

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.SUBORBITAL)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    # base 0.85 - 0.06 = 0.79. Roll 0.80 should fail.
    resolve_turn(state, rng=_FixedRng(0.80))

    # suborbital prestige_fail = 1
    assert me.prestige == 4


def test_state_roundtrip_preserves_rocket_safety() -> None:
    state = _two_player_state()
    state.players[0].rocket_safety[Rocket.HEAVY.value] = 67
    restored = GameState.from_dict(state.to_dict())
    assert restored.players[0].safety(Rocket.HEAVY) == 67


def test_state_roundtrip_preserves_astronauts() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    state.players[0].astronauts[0].status = AstronautStatus.KIA.value

    restored = GameState.from_dict(state.to_dict())
    assert isinstance(restored.players[0].astronauts[0], Astronaut)
    assert restored.players[0].astronauts[0].status == AstronautStatus.KIA.value
    assert len(restored.players[0].active_astronauts()) == STARTING_ASTRONAUTS - 1
