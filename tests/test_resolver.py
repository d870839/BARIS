from __future__ import annotations

import random

from baris.resolver import (
    _crew_bonus,
    _select_crew,
    all_turns_in,
    available_missions,
    can_start,
    choose_architecture,
    effective_base_success,
    effective_launch_cost,
    effective_rocket,
    meets_architecture_prereqs,
    resolve_turn,
    start_game,
    submit_turn,
    visible_missions,
    visible_to,
)
from baris.state import (
    ARCHITECTURE_COST_DELTA,
    ARCHITECTURE_SUCCESS_DELTA,
    Architecture,
    Astronaut,
    AstronautStatus,
    CREW_MAX_BONUS,
    GameState,
    HISTORICAL_ROSTERS,
    LaunchReport,
    ObjectiveId,
    ObjectiveReport,
    MIN_RELIABILITY_TO_LAUNCH,
    MISSIONS_BY_ID,
    MissionId,
    Module,
    ObjectiveId,
    Phase,
    Player,
    ProgramTier,
    RELIABILITY_CAP,
    RELIABILITY_FLOOR,
    RELIABILITY_GAIN_ON_SUCCESS,
    Rocket,
    Season,
    Side,
    Skill,
    STARTING_ASTRONAUTS,
    objectives_for,
    program_name,
    rocket_display_name,
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
    # Legacy tests that set command= get their value mapped to docking so
    # the old intent (good at docking/CM ops) is preserved.
    legacy_command = skills.pop("command", 0)
    return Astronaut(
        id=name,
        name=name,
        capsule=skills.get("capsule", 0),
        lm_pilot=skills.get("lm_pilot", 0),
        eva=skills.get("eva", 0),
        docking=skills.get("docking", legacy_command),
        endurance=skills.get("endurance", 0),
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
        roster_names = [a.name for a in p.astronauts]
        assert roster_names == list(HISTORICAL_ROSTERS[p.side.value])


def test_historical_roster_contents() -> None:
    """Protects the small historical fact set from accidental regressions."""
    usa = HISTORICAL_ROSTERS[Side.USA.value]
    ussr = HISTORICAL_ROSTERS[Side.USSR.value]
    # Mercury Seven.
    assert set(usa) == {"Shepard", "Grissom", "Glenn", "Carpenter",
                        "Schirra", "Cooper", "Slayton"}
    # Soviet first group + Tereshkova (first woman in space, 1963).
    assert "Tereshkova" in ussr
    assert "Gagarin" in ussr
    assert len(ussr) == 7


def test_fresh_player_sees_no_missions() -> None:
    """Brand new player has no rockets researched and no tier 2/3, so every
    mission is filtered out of the visible list."""
    p = Player(player_id="a", username="A", side=Side.USA)
    assert visible_missions(p) == []


def test_visibility_follows_rocket_research() -> None:
    p = Player(player_id="a", username="A", side=Side.USA)
    p.reliability[Rocket.LIGHT.value] = 70
    ids = {m.id for m in visible_missions(p)}
    # Tier 1 missions that use Light become visible.
    assert MissionId.SUBORBITAL in ids
    assert MissionId.SATELLITE in ids
    # Medium-rocket Tier 1 missions still hidden.
    assert MissionId.ORBITAL not in ids
    assert MissionId.MANNED_ORBITAL not in ids


def test_tier_lock_hides_missions_even_with_rocket_built() -> None:
    p = Player(player_id="a", username="A", side=Side.USA)
    # Fully loaded rockets, but no Tier 1 success → Tier 2 locked.
    for r in Rocket:
        p.reliability[r.value] = 70
    ids = {m.id for m in visible_missions(p)}
    assert MissionId.ORBITAL in ids  # Tier 1 — visible
    assert MissionId.LUNAR_PASS not in ids  # Tier 2 — hidden
    assert MissionId.LUNAR_LANDING not in ids  # Tier 3 — hidden


def test_manned_lunar_landing_visible_at_tier3_even_without_heavy() -> None:
    """Architecture choice decides the rocket need for MLL, so keep it
    visible once Tier 3 unlocks."""
    p = Player(player_id="a", username="A", side=Side.USA)
    p.mission_successes[MissionId.SUBORBITAL.value] = 1
    p.mission_successes[MissionId.MULTI_CREW_ORBITAL.value] = 1
    # No rockets at all.
    assert visible_to(p, MISSIONS_BY_ID[MissionId.MANNED_LUNAR_LANDING])
    # A different Tier 3 mission without a Heavy: still hidden.
    assert not visible_to(p, MISSIONS_BY_ID[MissionId.LUNAR_LANDING])
    assert not visible_to(p, MISSIONS_BY_ID[MissionId.MANNED_LUNAR_ORBIT])


def test_program_names_per_side() -> None:
    assert program_name(ProgramTier.ONE,   Side.USA)  == "Mercury"
    assert program_name(ProgramTier.TWO,   Side.USA)  == "Gemini"
    assert program_name(ProgramTier.THREE, Side.USA)  == "Apollo"
    assert program_name(ProgramTier.ONE,   Side.USSR) == "Vostok"
    assert program_name(ProgramTier.TWO,   Side.USSR) == "Voskhod"
    assert program_name(ProgramTier.THREE, Side.USSR) == "Soyuz"
    assert program_name(ProgramTier.ONE,   None)      == "Tier 1"


def test_tier_one_unlocked_by_default_others_locked() -> None:
    p = Player(player_id="a", username="x", side=Side.USA)
    assert p.is_tier_unlocked(ProgramTier.ONE)
    assert not p.is_tier_unlocked(ProgramTier.TWO)
    assert not p.is_tier_unlocked(ProgramTier.THREE)


def test_tier_two_unlocks_after_tier_one_success() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.reliability[Rocket.LIGHT.value] = 70

    assert not me.is_tier_unlocked(ProgramTier.TWO)
    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.SUBORBITAL)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=_FixedRng(0.0))

    assert me.is_tier_unlocked(ProgramTier.TWO)
    assert me.mission_successes[MissionId.SUBORBITAL.value] == 1


def test_tier_three_locked_without_tier_two_success() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    # Fake a Tier 1 success so Tier 2 is unlocked, but no Tier 2 success → Tier 3 still locked.
    me.mission_successes[MissionId.SUBORBITAL.value] = 1
    me.reliability[Rocket.HEAVY.value] = 70
    me.budget = 100

    assert me.is_tier_unlocked(ProgramTier.TWO)
    assert not me.is_tier_unlocked(ProgramTier.THREE)

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.MANNED_LUNAR_LANDING)
    # submit_turn should have refused the queue because Tier 3 is locked.
    assert me.pending_launch is None


def test_tier_three_unlocks_after_tier_two_success() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.mission_successes[MissionId.SUBORBITAL.value] = 1  # Tier 1 success, so Tier 2 unlocked
    me.reliability[Rocket.MEDIUM.value] = 70
    me.budget = 100
    for a in me.astronauts:
        a.endurance = 80

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.MULTI_CREW_ORBITAL)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=_FixedRng(0.0))

    assert me.is_tier_unlocked(ProgramTier.THREE)
    # Log should mention the Apollo unlock.
    assert any("Apollo" in line for line in state.log)


def test_available_missions_respects_tier_lock() -> None:
    me = Player(player_id="a", username="Alice", side=Side.USA)
    me.budget = 200
    me.reliability[Rocket.HEAVY.value] = 70
    # Even with a Heavy rocket built, Tier 3 missions should be locked until a Tier 2 success.
    avail = {m.id for m in available_missions(me)}
    assert MissionId.LUNAR_LANDING not in avail
    assert MissionId.MANNED_LUNAR_LANDING not in avail


def _tier3_unlocked_player(side: Side = Side.USA) -> Player:
    p = Player(player_id="a", username="A", side=side)
    p.budget = 500
    p.mission_successes[MissionId.SUBORBITAL.value] = 1
    p.mission_successes[MissionId.MULTI_CREW_ORBITAL.value] = 1
    p.reliability[Rocket.MEDIUM.value] = 70
    p.reliability[Rocket.HEAVY.value] = 70
    return p


def test_choose_architecture_rejected_before_tier_three() -> None:
    p = Player(player_id="a", username="A", side=Side.USA)
    assert not choose_architecture(p, Architecture.LOR)
    assert p.architecture is None


def test_choose_architecture_accepted_once_tier_three_unlocked() -> None:
    p = _tier3_unlocked_player()
    assert choose_architecture(p, Architecture.DA)
    assert p.architecture == Architecture.DA.value


def test_choose_architecture_is_one_way() -> None:
    p = _tier3_unlocked_player()
    assert choose_architecture(p, Architecture.LOR)
    assert not choose_architecture(p, Architecture.DA)  # second choice rejected
    assert p.architecture == Architecture.LOR.value


def test_eor_uses_medium_rocket_instead_of_heavy() -> None:
    p = _tier3_unlocked_player()
    choose_architecture(p, Architecture.EOR)
    m = MISSIONS_BY_ID[MissionId.MANNED_LUNAR_LANDING]
    assert effective_rocket(p, m) == Rocket.MEDIUM


def test_lor_keeps_heavy_rocket_requirement() -> None:
    p = _tier3_unlocked_player()
    choose_architecture(p, Architecture.LOR)
    m = MISSIONS_BY_ID[MissionId.MANNED_LUNAR_LANDING]
    assert effective_rocket(p, m) == Rocket.HEAVY


def test_architecture_modifies_cost_and_success() -> None:
    m = MISSIONS_BY_ID[MissionId.MANNED_LUNAR_LANDING]
    for arch in Architecture:
        p = _tier3_unlocked_player()
        choose_architecture(p, arch)
        assert effective_launch_cost(p, m) == m.launch_cost + ARCHITECTURE_COST_DELTA[arch]
        assert abs(effective_base_success(p, m) - (m.base_success + ARCHITECTURE_SUCCESS_DELTA[arch])) < 1e-9


def test_manned_landing_rejected_without_architecture() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.mission_successes[MissionId.SUBORBITAL.value] = 1
    me.mission_successes[MissionId.MULTI_CREW_ORBITAL.value] = 1
    me.reliability[Rocket.HEAVY.value] = 70
    me.budget = 200
    assert me.architecture is None

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.MANNED_LUNAR_LANDING)
    assert me.pending_launch is None


def test_lsr_requires_prior_unmanned_landing() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.mission_successes[MissionId.SUBORBITAL.value] = 1
    me.mission_successes[MissionId.MULTI_CREW_ORBITAL.value] = 1
    me.reliability[Rocket.HEAVY.value] = 70
    me.budget = 200
    choose_architecture(me, Architecture.LSR)

    # Without prior unmanned lunar landing: prereq fails.
    m = MISSIONS_BY_ID[MissionId.MANNED_LUNAR_LANDING]
    assert not meets_architecture_prereqs(me, m)

    me.mission_successes[MissionId.LUNAR_LANDING.value] = 1
    assert meets_architecture_prereqs(me, m)


def test_eor_lets_player_attempt_landing_with_only_medium() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.mission_successes[MissionId.SUBORBITAL.value] = 1
    me.mission_successes[MissionId.MULTI_CREW_ORBITAL.value] = 1
    me.reliability[Rocket.MEDIUM.value] = 70  # Heavy NOT built
    me.budget = 500
    for a in me.astronauts:
        a.lm_pilot = 100
    choose_architecture(me, Architecture.EOR)

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.MANNED_LUNAR_LANDING)
    assert me.pending_launch == MissionId.MANNED_LUNAR_LANDING.value

    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=_FixedRng(0.0))

    assert state.phase == Phase.ENDED
    assert state.winner == Side.USA


def test_rocket_display_name_is_per_side() -> None:
    assert rocket_display_name(Rocket.LIGHT,  Side.USA)  == "Redstone"
    assert rocket_display_name(Rocket.MEDIUM, Side.USA)  == "Titan II"
    assert rocket_display_name(Rocket.HEAVY,  Side.USA)  == "Saturn V"
    assert rocket_display_name(Rocket.LIGHT,  Side.USSR) == "R-7"
    assert rocket_display_name(Rocket.MEDIUM, Side.USSR) == "Proton"
    assert rocket_display_name(Rocket.HEAVY,  Side.USSR) == "N1"
    # With no side (lobby / unknown), falls back to class name.
    assert rocket_display_name(Rocket.LIGHT, None) == "Light"


# ----------------------------------------------------------------------
# R&D
# ----------------------------------------------------------------------


def test_rd_advances_only_the_chosen_rocket() -> None:
    """R&D is stochastic, so we can't assert an exact value — but we CAN
    assert that reliability moves up (or stays) only on the targeted rocket
    and stays at 0 on untouched rockets."""
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    submit_turn(state.players[0], rd_rocket=Rocket.LIGHT, rd_spend=30, launch=None)
    submit_turn(state.players[1], rd_rocket=Rocket.MEDIUM, rd_spend=30, launch=None)
    assert all_turns_in(state)

    resolve_turn(state, rng=random.Random(123))

    assert state.players[0].rocket_reliability(Rocket.LIGHT) > 0
    assert state.players[0].rocket_reliability(Rocket.MEDIUM) == 0
    assert state.players[1].rocket_reliability(Rocket.MEDIUM) > 0
    assert state.players[1].rocket_reliability(Rocket.LIGHT) == 0
    assert state.season == Season.SUMMER


def test_rd_heavy_is_slower_than_light_on_average() -> None:
    """Run many independent trials with the same spend to compare average
    reliability gains. Heavy should lag Light substantially (RD_SPEED diff)."""
    from baris.resolver import _apply_rd
    from baris.state import MISSIONS_BY_ID  # noqa: F401 (import for parity)

    def avg_gain(rocket: Rocket, trials: int = 200) -> float:
        total = 0
        for seed in range(trials):
            p = Player(player_id="a", username="A", side=Side.USA, budget=60)
            p.pending_rd_target = rocket.value
            p.pending_rd_spend = 60
            state = GameState(players=[p])
            _apply_rd(p, state, random.Random(seed))
            total += p.rocket_reliability(rocket)
        return total / trials

    light_avg = avg_gain(Rocket.LIGHT)
    heavy_avg = avg_gain(Rocket.HEAVY)
    assert light_avg > 5        # 60 MB on Light should average well above 5
    assert heavy_avg < light_avg  # Heavy is harder


def test_rd_spend_refunds_partial_batch_remainder() -> None:
    p = Player(player_id="a", username="A", side=Side.USA, budget=20)
    p.pending_rd_target = Rocket.LIGHT.value
    p.pending_rd_spend = 20  # 6 batches of 3 MB = 18 MB; 2 MB should be refunded
    state = GameState(players=[p])
    from baris.resolver import _apply_rd
    _apply_rd(p, state, random.Random(0))
    assert p.budget == 2  # 20 - 18 MB actually spent


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
    me.reliability[Rocket.LIGHT.value] = 70

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
    me.reliability[Rocket.LIGHT.value] = 70
    opp.reliability[Rocket.LIGHT.value] = 70

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
    me.reliability[Rocket.HEAVY.value] = 70
    me.budget = 100
    # Unlock Tier 3 for this test so the tier gate doesn't mask the crew check.
    me.mission_successes[MissionId.SUBORBITAL.value] = 1
    me.mission_successes[MissionId.MULTI_CREW_ORBITAL.value] = 1
    # kill all but 2 astronauts — landing needs 3
    for a in me.astronauts[:STARTING_ASTRONAUTS - 2]:
        a.status = AstronautStatus.KIA.value
    assert len(me.active_astronauts()) == 2

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.MANNED_LUNAR_LANDING)
    assert me.pending_launch is None


def test_select_crew_picks_top_skilled_by_primary() -> None:
    me = Player(player_id="a", username="Alice", side=Side.USA)
    me.astronauts = [
        _make_astronaut("A", capsule=10),
        _make_astronaut("B", capsule=90),
        _make_astronaut("C", capsule=50),
        _make_astronaut("D", capsule=70),
    ]
    mission = MISSIONS_BY_ID[MissionId.MANNED_LUNAR_ORBIT]  # crew_size=2, primary=Capsule
    crew = _select_crew(me, mission)
    assert crew is not None
    assert [a.name for a in crew] == ["B", "D"]


def test_crew_bonus_scales_with_primary_skill() -> None:
    mission = MISSIONS_BY_ID[MissionId.MANNED_LUNAR_LANDING]
    crew_max = [_make_astronaut(f"X{i}", lm_pilot=100) for i in range(mission.crew_size)]
    crew_zero = [_make_astronaut(f"Y{i}", lm_pilot=0) for i in range(mission.crew_size)]
    crew_half = [_make_astronaut(f"Z{i}", lm_pilot=50) for i in range(mission.crew_size)]

    assert _crew_bonus(crew_zero, mission) == 0.0
    assert abs(_crew_bonus(crew_max, mission) - CREW_MAX_BONUS) < 1e-9
    assert abs(_crew_bonus(crew_half, mission) - CREW_MAX_BONUS / 2) < 1e-9


def test_manned_landing_success_ends_game() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.reliability[Rocket.HEAVY.value] = 70
    me.budget = 100
    me.mission_successes[MissionId.SUBORBITAL.value] = 1
    me.mission_successes[MissionId.MULTI_CREW_ORBITAL.value] = 1
    choose_architecture(me, Architecture.LOR)
    for a in me.astronauts:
        a.lm_pilot = 100

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.MANNED_LUNAR_LANDING)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=_FixedRng(0.0))

    assert state.phase == Phase.ENDED
    assert state.winner == Side.USA


def test_unmanned_landing_only_awards_prestige() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.reliability[Rocket.HEAVY.value] = 70
    me.budget = 100
    me.mission_successes[MissionId.SUBORBITAL.value] = 1
    me.mission_successes[MissionId.MULTI_CREW_ORBITAL.value] = 1

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
    me.reliability[Rocket.MEDIUM.value] = 70
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
    me.reliability[Rocket.MEDIUM.value] = 70
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
    before = [
        (a.capsule, a.lm_pilot, a.eva, a.docking, a.endurance)
        for a in me.astronauts
    ]

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=None)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=random.Random(7))

    after = [
        (a.capsule, a.lm_pilot, a.eva, a.docking, a.endurance)
        for a in me.astronauts
    ]
    # every skill should have risen by at least 1 per astronaut
    for b, a in zip(before, after):
        for b_val, a_val in zip(b, a):
            assert a_val >= b_val + 1


# ----------------------------------------------------------------------
# Victory
# ----------------------------------------------------------------------


def test_prestige_cap_can_win() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.prestige = 38
    me.reliability[Rocket.LIGHT.value] = 70

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
    me.reliability[Rocket.MEDIUM.value] = 70
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


def test_successful_launch_bumps_reliability() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.reliability[Rocket.LIGHT.value] = 50

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.SUBORBITAL)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=_FixedRng(0.0))

    assert me.rocket_reliability(Rocket.LIGHT) == 50 + RELIABILITY_GAIN_ON_SUCCESS


def test_failed_unmanned_launch_still_gains_reliability() -> None:
    """A crashed probe still teaches the team — unmanned failures advance
    R&D by a small amount rather than dropping reliability."""
    from baris.state import UNMANNED_FAILURE_RD_GAIN

    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.reliability[Rocket.LIGHT.value] = 50

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.SUBORBITAL)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=_FixedRng(0.99))  # forced failure

    assert me.rocket_reliability(Rocket.LIGHT) == 50 + UNMANNED_FAILURE_RD_GAIN


def test_failed_manned_launch_drops_reliability_but_not_below_floor() -> None:
    """Manned failures still damage the rocket and floor at RELIABILITY_FLOOR."""
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.mission_successes[MissionId.SUBORBITAL.value] = 1  # unlock Tier 2 (unused here)
    me.reliability[Rocket.MEDIUM.value] = MIN_RELIABILITY_TO_LAUNCH + 3  # 28
    for a in me.astronauts:
        a.capsule = 40

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.MANNED_ORBITAL)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    # High success roll → failure; high death roll → no deaths (isolates reliability clamp).
    resolve_turn(state, rng=_FixedRng(0.99))

    assert me.rocket_reliability(Rocket.MEDIUM) == RELIABILITY_FLOOR


def test_failed_manned_launch_cuts_program_funding() -> None:
    """Manned failure pulls back funding by MANNED_FAILURE_BUDGET_CUT MB
    (on top of launch cost + season refill)."""
    from baris.state import MANNED_FAILURE_BUDGET_CUT

    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.reliability[Rocket.MEDIUM.value] = 50
    me.budget = 200
    mission = MISSIONS_BY_ID[MissionId.MANNED_ORBITAL]
    for a in me.astronauts:
        a.capsule = 40

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.MANNED_ORBITAL)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=_FixedRng(0.99))  # forced failure, no deaths

    from baris.state import SEASON_REFILL
    expected = 200 - mission.launch_cost - MANNED_FAILURE_BUDGET_CUT + SEASON_REFILL
    assert me.budget == expected


def test_failed_manned_launch_budget_cut_floors_at_zero() -> None:
    """If the budget can't absorb the full cut, it floors at zero instead of going negative."""
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.reliability[Rocket.MEDIUM.value] = 50
    # Just enough for the launch; no cushion for the funding cut.
    me.budget = MISSIONS_BY_ID[MissionId.MANNED_ORBITAL].launch_cost
    for a in me.astronauts:
        a.capsule = 40

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.MANNED_ORBITAL)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=_FixedRng(0.99))

    # Budget after launch cost (0) - clamped cut (0) + SEASON_REFILL.
    from baris.state import SEASON_REFILL
    assert me.budget == SEASON_REFILL


def test_reliability_cap_prevents_unbounded_growth() -> None:
    me = Player(player_id="a", username="Alice", side=Side.USA)
    me.reliability[Rocket.LIGHT.value] = RELIABILITY_CAP - 1
    from baris.resolver import _bump_reliability
    _bump_reliability(me, Rocket.LIGHT, 50)
    assert me.rocket_reliability(Rocket.LIGHT) == RELIABILITY_CAP


def test_high_reliability_improves_effective_success() -> None:
    """Set reliability very high and verify a mission succeeds on a roll that
    would fail at the base rate."""
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.reliability[Rocket.LIGHT.value] = RELIABILITY_CAP  # 99 → +0.098 success bonus

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.SUBORBITAL)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    # base suborbital success 0.85; with reliability +0.098 → 0.948. Roll 0.9 should succeed.
    resolve_turn(state, rng=_FixedRng(0.90))

    # base 3 + first bonus 2
    assert me.prestige == 5


def test_low_reliability_worsens_effective_success() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.reliability[Rocket.LIGHT.value] = MIN_RELIABILITY_TO_LAUNCH  # 25 → -0.05 penalty
    me.prestige = 5

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.SUBORBITAL)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    # base 0.85 - 0.06 = 0.79. Roll 0.80 should fail.
    resolve_turn(state, rng=_FixedRng(0.80))

    # suborbital prestige_fail = 1
    assert me.prestige == 4


# ----------------------------------------------------------------------
# Docking module R&D and mission objectives
# ----------------------------------------------------------------------


def test_docking_module_researched_same_way_as_rockets() -> None:
    """Spending on the docking module should drive up its reliability with
    the same stochastic roll mechanism used for rockets."""
    from baris.resolver import _apply_rd

    # Average across many trials to avoid flakes.
    total = 0
    trials = 200
    for seed in range(trials):
        p = Player(player_id="a", username="A", side=Side.USA, budget=60)
        p.pending_rd_target = Module.DOCKING.value
        p.pending_rd_spend = 60
        state = GameState(players=[p])
        _apply_rd(p, state, random.Random(seed))
        total += p.module_reliability(Module.DOCKING)
    avg = total / trials
    assert avg > 8  # Docking speed = 0.7, plenty of movement in 60 MB / 20 batches


def test_objectives_catalog_matches_missions() -> None:
    # MANNED_ORBITAL has both EVA and LONG_DURATION; MULTI_CREW has DOCKING + EVA;
    # MANNED_LUNAR_LANDING has MOONWALK + SAMPLE_RETURN.
    mo = {o.id for o in objectives_for(MissionId.MANNED_ORBITAL)}
    mco = {o.id for o in objectives_for(MissionId.MULTI_CREW_ORBITAL)}
    mll = {o.id for o in objectives_for(MissionId.MANNED_LUNAR_LANDING)}
    assert mo == {ObjectiveId.EVA, ObjectiveId.LONG_DURATION}
    assert mco == {ObjectiveId.DOCKING, ObjectiveId.EVA}
    assert mll == {ObjectiveId.MOONWALK, ObjectiveId.SAMPLE_RETURN}


def test_docking_objective_dropped_without_module() -> None:
    """Queuing the docking objective without the module built should be
    filtered out in submit_turn."""
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.mission_successes[MissionId.SUBORBITAL.value] = 1  # unlock Tier 2
    me.reliability[Rocket.MEDIUM.value] = 70
    me.budget = 200
    for a in me.astronauts:
        a.docking = 80

    submit_turn(
        me, rd_spend=0, launch=MissionId.MULTI_CREW_ORBITAL,
        objectives=[ObjectiveId.DOCKING],
    )
    assert me.pending_launch == MissionId.MULTI_CREW_ORBITAL.value
    # docking dropped because module isn't built
    assert me.pending_objectives == []


def test_docking_objective_accepted_when_module_built() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.mission_successes[MissionId.SUBORBITAL.value] = 1
    me.reliability[Rocket.MEDIUM.value] = 70
    me.reliability[Module.DOCKING.value] = 70
    me.budget = 200
    for a in me.astronauts:
        a.docking = 80

    submit_turn(
        me, rd_spend=0, launch=MissionId.MULTI_CREW_ORBITAL,
        objectives=[ObjectiveId.DOCKING],
    )
    assert me.pending_objectives == [ObjectiveId.DOCKING.value]


def test_objective_success_awards_bonus_prestige() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.reliability[Rocket.MEDIUM.value] = 70
    me.budget = 100
    for a in me.astronauts:
        a.capsule = 80  # primary skill for manned_orbital
        a.eva = 90      # drives EVA objective success

    submit_turn(
        me, rd_spend=0, launch=MissionId.MANNED_ORBITAL,
        objectives=[ObjectiveId.EVA],
    )
    submit_turn(state.players[1], rd_spend=0, launch=None)
    # Force both main mission and EVA roll to succeed (0.0 << any threshold).
    resolve_turn(state, rng=_FixedRng(0.0))

    # manned_orbital: 12 base + 6 first bonus + 4 EVA bonus = 22
    assert me.prestige == 22


def test_failed_eva_can_kill_astronaut() -> None:
    """Force the main mission to succeed and the EVA objective to fail,
    then the death roll to land below the 15% threshold."""

    class _SeqRng:
        def __init__(self, values):
            self.values = list(values)
            self._r = random.Random(1)

        def random(self) -> float:
            return self.values.pop(0)

        def randint(self, a, b):
            return self._r.randint(a, b)

        def choice(self, seq):
            return self._r.choice(seq)

    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.reliability[Rocket.MEDIUM.value] = 70
    me.budget = 100
    for a in me.astronauts:
        a.capsule = 80
        a.eva = 40  # low-ish so the EVA attempt can fail

    submit_turn(
        me, rd_spend=0, launch=MissionId.MANNED_ORBITAL,
        objectives=[ObjectiveId.EVA],
    )
    submit_turn(state.players[1], rd_spend=0, launch=None)
    # Sequence: main success (0.0), EVA objective fail (0.99), death roll low (0.05).
    resolve_turn(state, rng=_SeqRng([0.0, 0.99, 0.05]))

    # one crew member died
    assert len(me.active_astronauts()) == STARTING_ASTRONAUTS - 1


def test_failed_docking_can_destroy_ship() -> None:
    """Force docking objective to fail, then the ship-loss roll to succeed —
    the entire crew should die and the rocket reliability should drop 15."""

    class _SeqRng:
        def __init__(self, values):
            self.values = list(values)
            self._r = random.Random(2)

        def random(self) -> float:
            return self.values.pop(0)

        def randint(self, a, b):
            return self._r.randint(a, b)

        def choice(self, seq):
            return self._r.choice(seq)

    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.mission_successes[MissionId.SUBORBITAL.value] = 1
    me.reliability[Rocket.MEDIUM.value] = 70
    me.reliability[Module.DOCKING.value] = 70
    me.budget = 200
    for a in me.astronauts:
        a.docking = 30  # make docking objective likely to fail

    submit_turn(
        me, rd_spend=0, launch=MissionId.MULTI_CREW_ORBITAL,
        objectives=[ObjectiveId.DOCKING],
    )
    submit_turn(state.players[1], rd_spend=0, launch=None)
    # Sequence: main success (0.0), docking fail (0.99), ship-loss roll low (0.01).
    resolve_turn(state, rng=_SeqRng([0.0, 0.99, 0.01]))

    # crew of 2 both dead from ship loss
    assert len(me.active_astronauts()) == STARTING_ASTRONAUTS - 2
    # rocket reliability should have taken the extra -15 hit (on top of the
    # +5 from the main success bump). 70 + 5 - 15 = 60.
    assert me.rocket_reliability(Rocket.MEDIUM) == 60


def test_state_roundtrip_preserves_reliability() -> None:
    state = _two_player_state()
    state.players[0].reliability[Rocket.HEAVY.value] = 67
    restored = GameState.from_dict(state.to_dict())
    assert restored.players[0].rocket_reliability(Rocket.HEAVY) == 67


def test_state_roundtrip_preserves_astronauts() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    state.players[0].astronauts[0].status = AstronautStatus.KIA.value

    restored = GameState.from_dict(state.to_dict())
    assert isinstance(restored.players[0].astronauts[0], Astronaut)
    assert restored.players[0].astronauts[0].status == AstronautStatus.KIA.value
    assert len(restored.players[0].active_astronauts()) == STARTING_ASTRONAUTS - 1


# ----------------------------------------------------------------------
# LaunchReport — per-mission data the client uses to animate launch scenes
# ----------------------------------------------------------------------


def test_no_launch_produces_no_report() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    submit_turn(state.players[0], rd_rocket=None, rd_spend=0, launch=None)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=_FixedRng(0.0))
    assert state.last_launches == []


def test_successful_unmanned_launch_produces_report() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.reliability[Rocket.LIGHT.value] = 70

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.SUBORBITAL)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=_FixedRng(0.0))

    assert len(state.last_launches) == 1
    r = state.last_launches[0]
    assert r.side == Side.USA.value
    assert r.username == "Alice"
    assert r.mission_id == MissionId.SUBORBITAL.value
    assert r.success is True
    assert r.aborted is False
    assert r.manned is False
    assert r.crew == []
    assert r.first_claimed is True
    # 3 base + 2 first bonus
    assert r.prestige_delta == 5
    assert r.rocket == "Redstone"  # USA side display name
    assert r.rocket_class == Rocket.LIGHT.value
    # Reliability before the launch == 70; successful flight +5 → 75.
    assert r.reliability_before == 70
    assert r.reliability_after == 75


def test_failed_unmanned_launch_report() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.reliability[Rocket.LIGHT.value] = 70
    me.prestige = 10

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.SUBORBITAL)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=_FixedRng(0.99))  # forced failure

    r = state.last_launches[0]
    assert r.success is False
    assert r.first_claimed is False
    # suborbital prestige_fail = 1
    assert r.prestige_delta == -1
    # unmanned failure adds +2 reliability from post-flight analysis.
    assert r.reliability_after == r.reliability_before + 2


def test_failed_manned_launch_captures_deaths_and_budget_cut() -> None:
    """Feed a sequence RNG so the success roll fails and every crew-death roll trips."""

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
    me.reliability[Rocket.MEDIUM.value] = 70
    me.budget = 200
    me.prestige = 30
    for a in me.astronauts:
        a.capsule = 50

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.MANNED_ORBITAL)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    # success roll high (fail), death roll low (crew dies).
    resolve_turn(state, rng=_SeqRng([0.99, 0.01]))

    r = state.last_launches[0]
    assert r.success is False
    assert r.manned is True
    assert len(r.crew) == 1
    assert r.deaths == r.crew
    assert r.budget_cut == 30


def test_manned_lunar_landing_success_marks_ended_game() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.reliability[Rocket.HEAVY.value] = 70
    me.budget = 100
    me.mission_successes[MissionId.SUBORBITAL.value] = 1
    me.mission_successes[MissionId.MULTI_CREW_ORBITAL.value] = 1
    choose_architecture(me, Architecture.LOR)
    for a in me.astronauts:
        a.lm_pilot = 100

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.MANNED_LUNAR_LANDING)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=_FixedRng(0.0))

    r = state.last_launches[0]
    assert r.success is True
    assert r.ended_game is True


def test_objective_success_recorded_in_report() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.reliability[Rocket.MEDIUM.value] = 70
    me.budget = 100
    for a in me.astronauts:
        a.capsule = 80
        a.eva = 100  # guarantee EVA objective clears
        a.endurance = 80

    submit_turn(me, rd_rocket=None, rd_spend=0,
                launch=MissionId.MANNED_ORBITAL, objectives=[ObjectiveId.EVA])
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=_FixedRng(0.0))

    r = state.last_launches[0]
    assert r.success is True
    assert len(r.objectives) == 1
    obj = r.objectives[0]
    assert obj.objective_id == ObjectiveId.EVA.value
    assert obj.success is True
    assert obj.prestige_delta == 4  # MANNED_ORBITAL EVA bonus


def test_resolve_turn_clears_previous_last_launches() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.reliability[Rocket.LIGHT.value] = 70

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.SUBORBITAL)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=_FixedRng(0.0))
    assert len(state.last_launches) == 1

    # Second turn: nobody launches. last_launches should be cleared.
    submit_turn(me, rd_rocket=None, rd_spend=0, launch=None)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=_FixedRng(0.0))
    assert state.last_launches == []


def test_launch_report_roundtrip_through_state_dict() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.reliability[Rocket.LIGHT.value] = 70
    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.SUBORBITAL)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=_FixedRng(0.0))

    restored = GameState.from_dict(state.to_dict())
    assert len(restored.last_launches) == 1
    assert isinstance(restored.last_launches[0], LaunchReport)
    assert restored.last_launches[0].mission_id == MissionId.SUBORBITAL.value
    assert restored.last_launches[0].success is True
