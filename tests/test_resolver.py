from __future__ import annotations

import random

from baris.resolver import (
    _crew_bonus,
    _select_crew,
    all_turns_in,
    available_missions,
    can_start,
    cancel_training,
    choose_architecture,
    crew_compatibility_bonus,
    effective_base_success,
    effective_launch_cost,
    effective_lunar_modifier,
    effective_rocket,
    intel_available,
    meets_architecture_prereqs,
    next_recruitment_preview,
    recruit_next_group,
    request_intel,
    resolve_turn,
    scrub_scheduled,
    start_game,
    start_training,
    submit_turn,
    visible_missions,
    visible_to,
)
from baris.state import (
    ADVANCED_TRAINING_COST,
    ADVANCED_TRAINING_SKILL_GAIN,
    ADVANCED_TRAINING_TURNS,
    ARCHITECTURE_COST_DELTA,
    ARCHITECTURE_SUCCESS_DELTA,
    ASSEMBLY_COST_FRACTION,
    BASIC_TRAINING_TURNS,
    CREW_COMPAT_MAX_BONUS,
    Compatibility,
    HOSPITAL_STAY_TURNS,
    MOOD_DEFAULT,
    MOOD_FAILURE_DROP,
    MOOD_KIA_CREW_DROP,
    MOOD_MAX,
    MOOD_RETIREMENT_THRESHOLD,
    MOOD_SUCCESS_BUMP,
    LM_POINTS_PENALTY_PER_MISSING,
    LM_POINTS_REQUIRED,
    LUNAR_RECON_BASE,
    LUNAR_RECON_CAP,
    LUNAR_RECON_PER_POINT,
    RECON_FROM_LUNAR_PASS,
    RECON_FROM_UNMANNED_LANDING_FAIL,
    RECON_FROM_UNMANNED_LANDING_OK,
    TRAINING_CANCEL_REFUND_FRACTION,
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
    SCRUB_REFUND_FRACTION,
    ScheduledLaunch,
    Phase,
    Player,
    ProgramTier,
    RELIABILITY_CAP,
    INTEL_COST,
    INTEL_RELIABILITY_NOISE,
    IntelReport,
    MissionHistoryEntry,
    Phase,
    PrestigeSnapshot,
    REVIEW_FIRE_AT_WARNINGS,
    REVIEW_KIA_PENALTY,
    REVIEW_PASS_THRESHOLD,
    REVIEW_SUCCESS_BONUS,
    RECRUIT_SKILL_MAX,
    RECRUIT_SKILL_MIN,
    RECRUITMENT_GROUPS,
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


from contextlib import contextmanager


@contextmanager
def _no_news():
    """Suppress Phase I seasonal news rolls for the duration of the block.
    Used by tests that assert on mood / budget / reliability deltas where
    a random news card would otherwise mask or cancel the mechanic under
    test."""
    from baris import resolver as _r
    prev = _r._news_enabled
    _r._news_enabled = False
    try:
        yield
    finally:
        _r._news_enabled = prev


@contextmanager
def _no_chatter():
    """Suppress radio chatter rolls so tests with deterministic
    fixed-sequence RNGs don't have their values drained."""
    from baris import chatter as _c
    prev = _c._chatter_enabled
    _c._chatter_enabled = False
    try:
        yield
    finally:
        _c._chatter_enabled = prev


@contextmanager
def _no_flavor():
    """Convenience: suppress both news and chatter."""
    with _no_news(), _no_chatter():
        yield


def _fire_scheduled_launch(state: GameState, rng) -> None:
    """Phase B helper: after a player submits a launch and the turn resolves,
    the mission goes into scheduled_launch (assembly paid). Call this to
    submit empty turns + resolve again so the mission actually fires.
    Used by older single-turn-resolve tests."""
    for p in state.players:
        submit_turn(p, rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=rng)


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
    """Sanity-check the (now-divergent) starting rosters: 7 per side,
    every name has a portrait, and the two sides don't overlap."""
    from baris.state import CHARACTER_PORTRAITS, character_portrait
    usa = HISTORICAL_ROSTERS[Side.USA.value]
    ussr = HISTORICAL_ROSTERS[Side.USSR.value]
    assert len(usa) == 7
    assert len(ussr) == 7
    assert not (set(usa) & set(ussr))   # no shared names
    for name in (*usa, *ussr):
        assert name in CHARACTER_PORTRAITS, f"missing portrait for {name}"
        glyph, rgb = character_portrait(name)
        assert glyph and len(rgb) == 3


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
    _fire_scheduled_launch(state, _FixedRng(0.0))

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
    _fire_scheduled_launch(state, _FixedRng(0.0))

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
    me.reliability[Module.LUNAR_KICKER.value] = 70
    me.reliability[Module.EVA_SUIT.value] = 70
    me.budget = 500
    for a in me.astronauts:
        a.lm_pilot = 100
    choose_architecture(me, Architecture.EOR)

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.MANNED_LUNAR_LANDING)
    assert me.pending_launch == MissionId.MANNED_LUNAR_LANDING.value

    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=_FixedRng(0.0))
    _fire_scheduled_launch(state, _FixedRng(0.0))

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
    _fire_scheduled_launch(state, _FixedRng(0.0))

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
    _fire_scheduled_launch(state, _FixedRng(0.0))

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


def test_select_crew_picks_top_skilled_per_role() -> None:
    """Manned lunar orbit's roles are (CAPSULE, ENDURANCE), so the
    selector should take the best capsule pilot for slot 1 then the
    best endurance pilot from the remainder for slot 2."""
    me = Player(player_id="a", username="Alice", side=Side.USA)
    me.astronauts = [
        _make_astronaut("A", capsule=10, endurance=10),
        _make_astronaut("B", capsule=90, endurance=20),
        _make_astronaut("C", capsule=50, endurance=80),
        _make_astronaut("D", capsule=70, endurance=30),
    ]
    mission = MISSIONS_BY_ID[MissionId.MANNED_LUNAR_ORBIT]
    crew = _select_crew(me, mission)
    assert crew is not None
    assert [a.name for a in crew] == ["B", "C"]


def test_crew_bonus_uses_role_skill_per_seat() -> None:
    """Manned lunar landing roles are (CAPSULE, LM_PILOT, EVA), so the
    bonus averages each pilot's skill in their assigned role rather
    than collapsing on a single primary_skill."""
    mission = MISSIONS_BY_ID[MissionId.MANNED_LUNAR_LANDING]
    # Each pilot maxed in EVERY skill — bonus should hit the cap.
    crew_max = [
        _make_astronaut(
            f"X{i}", capsule=100, lm_pilot=100, eva=100, docking=100, endurance=100,
        )
        for i in range(mission.crew_size)
    ]
    crew_zero = [_make_astronaut(f"Y{i}") for i in range(mission.crew_size)]
    crew_half = [
        _make_astronaut(
            f"Z{i}", capsule=50, lm_pilot=50, eva=50, docking=50, endurance=50,
        )
        for i in range(mission.crew_size)
    ]
    assert _crew_bonus(crew_zero, mission) == 0.0
    assert abs(_crew_bonus(crew_max, mission) - CREW_MAX_BONUS) < 1e-9
    assert abs(_crew_bonus(crew_half, mission) - CREW_MAX_BONUS / 2) < 1e-9


def test_crew_bonus_falls_back_to_primary_when_no_roles() -> None:
    """Missions without crew_roles set keep the legacy behaviour."""
    from baris.state import Mission, ProgramTier
    legacy = Mission(
        id=MissionId.MANNED_ORBITAL,   # arbitrary; we override fields
        name="legacy", rocket=Rocket.MEDIUM, launch_cost=10,
        base_success=0.5, prestige_success=1, prestige_fail=1, first_bonus=0,
        tier=ProgramTier.ONE, manned=True, crew_size=2,
        primary_skill=Skill.CAPSULE,
        crew_roles=(),  # explicit empty
    )
    crew = [
        _make_astronaut("A", capsule=100, eva=0),
        _make_astronaut("B", capsule=100, eva=0),
    ]
    assert abs(_crew_bonus(crew, legacy) - CREW_MAX_BONUS) < 1e-9


def test_manned_landing_success_ends_game() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.reliability[Rocket.HEAVY.value] = 70
    me.reliability[Module.EVA_SUIT.value] = 70
    me.reliability[Module.LUNAR_KICKER.value] = 70
    me.budget = 100
    me.mission_successes[MissionId.SUBORBITAL.value] = 1
    me.mission_successes[MissionId.MULTI_CREW_ORBITAL.value] = 1
    choose_architecture(me, Architecture.LOR)
    for a in me.astronauts:
        a.lm_pilot = 100

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.MANNED_LUNAR_LANDING)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=_FixedRng(0.0))
    _fire_scheduled_launch(state, _FixedRng(0.0))

    assert state.phase == Phase.ENDED
    assert state.winner == Side.USA


def test_unmanned_landing_only_awards_prestige() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.reliability[Rocket.HEAVY.value] = 70
    me.reliability[Module.LUNAR_KICKER.value] = 70
    me.budget = 100
    me.mission_successes[MissionId.SUBORBITAL.value] = 1
    me.mission_successes[MissionId.MULTI_CREW_ORBITAL.value] = 1

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.LUNAR_LANDING)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=_FixedRng(0.0))
    _fire_scheduled_launch(state, _FixedRng(0.0))

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
    _fire_scheduled_launch(state, _FixedRng(0.99))

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
    _fire_scheduled_launch(state, _SeqRng([0.99, 0.01]))

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
    _fire_scheduled_launch(state, _FixedRng(0.0))

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
    _fire_scheduled_launch(state, _FixedRng(0.0))

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
    _fire_scheduled_launch(state, _FixedRng(0.99))

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
    _fire_scheduled_launch(state, _FixedRng(0.99))

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
    with _no_news():  # isolate from random news cards (e.g. budget windfall)
        resolve_turn(state, rng=_FixedRng(0.99))  # forced failure, no deaths
        _fire_scheduled_launch(state, _FixedRng(0.99))

    from baris.state import SEASON_REFILL
    # Two resolves under VAB scheduling → two SEASON_REFILLs.
    expected = (
        200 - mission.launch_cost - MANNED_FAILURE_BUDGET_CUT + 2 * SEASON_REFILL
    )
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
    with _no_news():
        resolve_turn(state, rng=_FixedRng(0.99))
        _fire_scheduled_launch(state, _FixedRng(0.99))

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
    _fire_scheduled_launch(state, _FixedRng(0.90))

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
    # Suborbital has 2 phases (LAUNCH + REENTRY). With low overall
    # success the per-phase chance is also low, but we want a clean
    # failure regardless — feed 0.99 so every phase roll trivially
    # fails the cap.
    with _no_news():
        resolve_turn(state, rng=_FixedRng(0.99))
        _fire_scheduled_launch(state, _FixedRng(0.99))

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
    me.reliability[Module.EVA_SUIT.value] = 70
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
    _fire_scheduled_launch(state, _FixedRng(0.0))

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
    me.reliability[Module.EVA_SUIT.value] = 70
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
    _fire_scheduled_launch(state, _SeqRng([0.0, 0.99, 0.05]))

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
    # MULTI_CREW_ORBITAL has 3 phases (LAUNCH, ORBIT_INSERTION,
    # REENTRY). Real Phase P rolls each one separately, so we feed
    # three 0.0s to pass them all, then 0.99 to fail the docking
    # objective, then 0.01 to trigger the ship-loss roll on the
    # failed objective. Tail padding covers any post-objective rolls.
    seq = [0.0, 0.0, 0.0, 0.99, 0.01, 0.99, 0.99, 0.99]
    with _no_news():
        resolve_turn(state, rng=_SeqRng(seq))
        _fire_scheduled_launch(state, _SeqRng(seq))

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
    _fire_scheduled_launch(state, _FixedRng(0.0))

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
    _fire_scheduled_launch(state, _FixedRng(0.99))

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
    _fire_scheduled_launch(state, _SeqRng([0.99, 0.01]))

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
    me.reliability[Module.EVA_SUIT.value] = 70
    me.reliability[Module.LUNAR_KICKER.value] = 70
    me.budget = 100
    me.mission_successes[MissionId.SUBORBITAL.value] = 1
    me.mission_successes[MissionId.MULTI_CREW_ORBITAL.value] = 1
    choose_architecture(me, Architecture.LOR)
    for a in me.astronauts:
        a.lm_pilot = 100

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.MANNED_LUNAR_LANDING)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=_FixedRng(0.0))
    _fire_scheduled_launch(state, _FixedRng(0.0))

    r = state.last_launches[0]
    assert r.success is True
    assert r.ended_game is True


def test_objective_success_recorded_in_report() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.reliability[Rocket.MEDIUM.value] = 70
    me.reliability[Module.EVA_SUIT.value] = 70
    me.budget = 100
    for a in me.astronauts:
        a.capsule = 80
        a.eva = 100  # guarantee EVA objective clears
        a.endurance = 80

    submit_turn(me, rd_rocket=None, rd_spend=0,
                launch=MissionId.MANNED_ORBITAL, objectives=[ObjectiveId.EVA])
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=_FixedRng(0.0))
    _fire_scheduled_launch(state, _FixedRng(0.0))

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
    _fire_scheduled_launch(state, _FixedRng(0.0))
    assert len(state.last_launches) == 1

    # Second turn: nobody launches. last_launches should be cleared.
    submit_turn(me, rd_rocket=None, rd_spend=0, launch=None)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=_FixedRng(0.0))
    _fire_scheduled_launch(state, _FixedRng(0.0))
    assert state.last_launches == []


def test_launch_report_roundtrip_through_state_dict() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.reliability[Rocket.LIGHT.value] = 70
    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.SUBORBITAL)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=_FixedRng(0.0))
    _fire_scheduled_launch(state, _FixedRng(0.0))

    restored = GameState.from_dict(state.to_dict())
    assert len(restored.last_launches) == 1
    assert isinstance(restored.last_launches[0], LaunchReport)
    assert restored.last_launches[0].mission_id == MissionId.SUBORBITAL.value
    assert restored.last_launches[0].success is True


# ----------------------------------------------------------------------
# Phase B — Vehicle Assembly Building (multi-turn scheduling)
# ----------------------------------------------------------------------


def test_submit_schedules_but_does_not_resolve_this_turn() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.reliability[Rocket.LIGHT.value] = 70

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.SUBORBITAL)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=_FixedRng(0.0))

    # Nothing flew; the mission is on the manifest waiting for next turn.
    assert state.last_launches == []
    assert me.scheduled_launch is not None
    assert me.scheduled_launch.mission_id == MissionId.SUBORBITAL.value
    # Assembly cost was 30% of launch_cost=3 → int(0.9) = 0, so budget
    # stays intact for this cheap mission. Check a pricier mission too.


def test_assembly_cost_is_reserved_on_schedule() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.reliability[Rocket.HEAVY.value] = 70
    me.reliability[Module.LUNAR_KICKER.value] = 70
    me.mission_successes[MissionId.SUBORBITAL.value] = 1
    me.mission_successes[MissionId.MULTI_CREW_ORBITAL.value] = 1
    me.budget = 200
    budget_before = me.budget

    lunar = MISSIONS_BY_ID[MissionId.LUNAR_LANDING]   # 25 MB total, Heavy
    expected_assembly = int(lunar.launch_cost * ASSEMBLY_COST_FRACTION)

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.LUNAR_LANDING)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=_FixedRng(0.0))

    # SEASON_REFILL lands at end of resolve, so budget has moved by
    # (-assembly + SEASON_REFILL).
    from baris.state import SEASON_REFILL
    assert me.budget == budget_before - expected_assembly + SEASON_REFILL
    assert me.scheduled_launch.assembly_cost_paid == expected_assembly
    assert (
        me.scheduled_launch.launch_cost_remaining
        == lunar.launch_cost - expected_assembly
    )


def test_scheduled_launch_fires_next_turn() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.reliability[Rocket.LIGHT.value] = 70

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.SUBORBITAL)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=_FixedRng(0.0))
    assert me.scheduled_launch is not None

    # Next turn: empty submits → the scheduled mission actually fires.
    submit_turn(me, rd_rocket=None, rd_spend=0, launch=None)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=_FixedRng(0.0))

    assert me.scheduled_launch is None
    assert len(state.last_launches) == 1
    r = state.last_launches[0]
    assert r.mission_id == MissionId.SUBORBITAL.value
    assert r.success is True


def test_launch_queue_is_blocked_when_all_pads_occupied() -> None:
    """With every pad holding a ScheduledLaunch, submit_turn drops any
    further launch queue (no pad available to assemble into). With at
    least one pad free, a new queue still goes through."""
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.reliability[Rocket.LIGHT.value] = 70
    me.budget = 100
    # Occupy all three pads manually.
    from baris.state import ScheduledLaunch
    for pad in me.pads:
        pad.scheduled_launch = ScheduledLaunch(
            mission_id=MissionId.SUBORBITAL.value,
            rocket_class=Rocket.LIGHT.value,
            launch_cost_total=3, assembly_cost_paid=0,
            launch_cost_remaining=3, objectives=[],
        )

    # All pads booked → next submit should reject the new launch queue.
    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.SATELLITE)
    assert me.pending_launch is None

    # Free up one pad → the queue should go through again.
    me.pads[1].scheduled_launch = None
    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.SATELLITE)
    assert me.pending_launch == MissionId.SATELLITE.value


def test_scrub_scheduled_refunds_half_of_assembly_and_clears_slot() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.reliability[Rocket.HEAVY.value] = 70
    me.reliability[Module.LUNAR_KICKER.value] = 70
    me.mission_successes[MissionId.SUBORBITAL.value] = 1
    me.mission_successes[MissionId.MULTI_CREW_ORBITAL.value] = 1
    me.budget = 200

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.LUNAR_LANDING)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=_FixedRng(0.0))

    assert me.scheduled_launch is not None
    assembly = me.scheduled_launch.assembly_cost_paid
    budget_pre_scrub = me.budget

    assert scrub_scheduled(me) is True
    assert me.scheduled_launch is None
    assert me.budget == budget_pre_scrub + int(assembly * SCRUB_REFUND_FRACTION)


def test_scrub_with_nothing_scheduled_is_noop() -> None:
    me = Player(player_id="a", username="Alice", side=Side.USA)
    me.budget = 50
    assert scrub_scheduled(me) is False
    assert me.budget == 50


def test_insufficient_budget_blocks_assembly() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.reliability[Rocket.HEAVY.value] = 70
    me.mission_successes[MissionId.SUBORBITAL.value] = 1
    me.mission_successes[MissionId.MULTI_CREW_ORBITAL.value] = 1
    # Lunar landing launch_cost = 25, assembly = 7 MB.
    me.budget = 6  # not enough to even assemble.

    # submit_turn's own affordability check will actually reject this
    # too, since it compares budget against assembly_cost + rd_spend.
    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.LUNAR_LANDING)
    assert me.pending_launch is None
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=_FixedRng(0.0))

    assert me.scheduled_launch is None
    assert state.last_launches == []


def test_scheduled_launch_roundtrips_through_state_dict() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.reliability[Rocket.LIGHT.value] = 70

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.SUBORBITAL)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=_FixedRng(0.0))
    assert me.scheduled_launch is not None

    restored = GameState.from_dict(state.to_dict())
    r_me = restored.find_player("a")
    assert r_me.scheduled_launch is not None
    assert isinstance(r_me.scheduled_launch, ScheduledLaunch)
    assert r_me.scheduled_launch.mission_id == MissionId.SUBORBITAL.value
    assert r_me.scheduled_launch.assembly_cost_paid == me.scheduled_launch.assembly_cost_paid


# ----------------------------------------------------------------------
# Phase C — crew training + hospital recovery
# ----------------------------------------------------------------------


def test_astronaut_in_basic_training_is_not_flight_ready() -> None:
    a = Astronaut(id="a", name="A")
    assert a.flight_ready is True
    a.basic_training_remaining = 2
    assert a.flight_ready is False
    assert "basic training" in a.busy_reason


def test_astronaut_in_hospital_is_not_flight_ready() -> None:
    a = Astronaut(id="a", name="A")
    a.hospital_remaining = 1
    assert a.flight_ready is False
    assert "hospital" in a.busy_reason


def test_kia_astronaut_is_not_flight_ready() -> None:
    a = Astronaut(id="a", name="A", status=AstronautStatus.KIA.value)
    assert a.flight_ready is False
    assert a.busy_reason == "KIA"


def test_start_training_deducts_cost_and_sets_counter() -> None:
    me = Player(player_id="a", username="Alice", side=Side.USA, budget=50)
    me.astronauts = [Astronaut(id="x", name="X", capsule=40)]
    assert start_training(me, "x", Skill.CAPSULE)
    assert me.budget == 50 - ADVANCED_TRAINING_COST
    assert me.astronauts[0].advanced_training_remaining == ADVANCED_TRAINING_TURNS
    assert me.astronauts[0].advanced_training_skill == Skill.CAPSULE.value
    # Flight-blocked while training.
    assert me.astronauts[0].flight_ready is False


def test_start_training_rejects_if_already_training() -> None:
    me = Player(player_id="a", username="Alice", side=Side.USA, budget=50)
    a = Astronaut(
        id="x", name="X",
        advanced_training_remaining=1, advanced_training_skill=Skill.EVA.value,
    )
    me.astronauts = [a]
    assert not start_training(me, "x", Skill.CAPSULE)
    assert me.budget == 50  # not charged


def test_start_training_rejects_when_broke() -> None:
    me = Player(player_id="a", username="Alice", side=Side.USA, budget=1)
    me.astronauts = [Astronaut(id="x", name="X")]
    assert not start_training(me, "x", Skill.CAPSULE)
    assert me.astronauts[0].advanced_training_remaining == 0


def test_cancel_training_refunds_half_and_clears_slot() -> None:
    me = Player(player_id="a", username="Alice", side=Side.USA, budget=50)
    me.astronauts = [Astronaut(id="x", name="X")]
    start_training(me, "x", Skill.EVA)
    budget_after_start = me.budget
    assert cancel_training(me, "x")
    expected_refund = int(ADVANCED_TRAINING_COST * TRAINING_CANCEL_REFUND_FRACTION)
    assert me.budget == budget_after_start + expected_refund
    assert me.astronauts[0].advanced_training_remaining == 0
    assert me.astronauts[0].advanced_training_skill == ""


def test_advanced_training_completes_and_bumps_skill() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.budget = 100
    target = me.astronauts[0]
    target.capsule = 20
    assert start_training(me, target.id, Skill.CAPSULE)
    # Two turns must pass for the block to complete.
    for _ in range(ADVANCED_TRAINING_TURNS):
        submit_turn(me, rd_rocket=None, rd_spend=0, launch=None)
        submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
        resolve_turn(state, rng=random.Random(0))
    assert target.advanced_training_remaining == 0
    assert target.advanced_training_skill == ""
    # Skill bumped by training (plus passive bumps, so >=).
    assert target.capsule >= 20 + ADVANCED_TRAINING_SKILL_GAIN


def test_hospital_countdown_ticks_down_each_turn() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.astronauts[0].hospital_remaining = 2

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=None)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=random.Random(0))
    assert me.astronauts[0].hospital_remaining == 1

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=None)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=random.Random(0))
    assert me.astronauts[0].hospital_remaining == 0
    assert me.astronauts[0].flight_ready is True


def test_select_crew_skips_trainees() -> None:
    me = Player(player_id="a", username="Alice", side=Side.USA)
    me.astronauts = [
        _make_astronaut("Hi", capsule=90),
        _make_astronaut("Lo", capsule=30),
    ]
    # Star astronaut is in basic training → must fall back to the backup.
    me.astronauts[0].basic_training_remaining = 2
    mission = MISSIONS_BY_ID[MissionId.MANNED_ORBITAL]
    crew = _select_crew(me, mission)
    assert crew is not None
    assert [a.name for a in crew] == ["Lo"]


def test_manned_failure_can_send_survivor_to_hospital() -> None:
    """Fixed RNG where the success/death/hospital rolls all trip the
    hospital threshold but miss the death threshold."""

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
    me.budget = 200
    for a in me.astronauts:
        a.capsule = 50

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.MANNED_ORBITAL)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    # Success roll (0.99 → fail), death roll (0.99 → survive),
    # hospital roll (0.01 → yes) for the single crew member.
    resolve_turn(state, rng=_SeqRng([0.99]))
    _fire_scheduled_launch(state, _SeqRng([0.99, 0.99, 0.01]))

    # Nobody died, but the pilot is in the hospital.
    assert len(me.active_astronauts()) == STARTING_ASTRONAUTS
    hospitalised = [a for a in me.astronauts if a.hospital_remaining > 0]
    assert len(hospitalised) == 1
    assert hospitalised[0].hospital_remaining == HOSPITAL_STAY_TURNS


def test_training_state_roundtrips_through_dict() -> None:
    me = Player(player_id="a", username="Alice", side=Side.USA)
    me.astronauts = [
        Astronaut(
            id="x", name="X", capsule=30,
            basic_training_remaining=2,
            advanced_training_skill=Skill.EVA.value,
            advanced_training_remaining=1,
            hospital_remaining=3,
        ),
    ]
    state = GameState(players=[me])
    restored = GameState.from_dict(state.to_dict())
    r_a = restored.players[0].astronauts[0]
    assert r_a.basic_training_remaining == 2
    assert r_a.advanced_training_skill == Skill.EVA.value
    assert r_a.advanced_training_remaining == 1
    assert r_a.hospital_remaining == 3
    assert r_a.flight_ready is False


def test_legacy_astronaut_dict_without_training_fields_still_loads() -> None:
    # Old save: no training / hospital keys.
    raw = {
        "id": "x", "name": "X",
        "capsule": 10, "eva": 5, "endurance": 5,
        "command": 8,   # legacy single-skill 'command'
        "status": "active",
    }
    a = _astronaut_from_dict(raw) if False else None  # placeholder so the import exists
    from baris.state import _astronaut_from_dict
    a = _astronaut_from_dict(raw)
    assert a.basic_training_remaining == 0
    assert a.advanced_training_remaining == 0
    assert a.advanced_training_skill == ""
    assert a.hospital_remaining == 0
    assert a.flight_ready is True
    # Legacy 'command' maps onto 'docking'.
    assert a.docking == 8


# ----------------------------------------------------------------------
# Phase D — lunar reconnaissance + LM points
# ----------------------------------------------------------------------


def test_starting_player_has_baseline_recon_and_no_lm_points() -> None:
    p = Player(player_id="a", username="A", side=Side.USA)
    assert p.lunar_recon == LUNAR_RECON_BASE
    assert p.lm_points == 0


def test_successful_lunar_flyby_bumps_recon() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.mission_successes[MissionId.SUBORBITAL.value] = 1  # unlock Tier 2
    me.reliability[Rocket.MEDIUM.value] = 70
    me.reliability[Module.LUNAR_KICKER.value] = 70
    me.budget = 200

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.LUNAR_PASS)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=_FixedRng(0.0))
    _fire_scheduled_launch(state, _FixedRng(0.0))

    assert me.lunar_recon == LUNAR_RECON_BASE + RECON_FROM_LUNAR_PASS


def test_successful_unmanned_landing_bumps_recon_and_lm() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.reliability[Rocket.HEAVY.value] = 70
    me.reliability[Module.LUNAR_KICKER.value] = 70
    me.budget = 200
    me.mission_successes[MissionId.SUBORBITAL.value] = 1
    me.mission_successes[MissionId.MULTI_CREW_ORBITAL.value] = 1

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.LUNAR_LANDING)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=_FixedRng(0.0))
    _fire_scheduled_launch(state, _FixedRng(0.0))

    assert me.lunar_recon == LUNAR_RECON_BASE + RECON_FROM_UNMANNED_LANDING_OK
    assert me.lm_points == 1


def test_failed_unmanned_landing_still_bumps_recon() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.reliability[Rocket.HEAVY.value] = 70
    me.reliability[Module.LUNAR_KICKER.value] = 70
    me.budget = 200
    me.mission_successes[MissionId.SUBORBITAL.value] = 1
    me.mission_successes[MissionId.MULTI_CREW_ORBITAL.value] = 1

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.LUNAR_LANDING)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=_FixedRng(0.99))
    _fire_scheduled_launch(state, _FixedRng(0.99))

    # Failed landing → smaller recon bump, no LM points.
    assert me.lunar_recon == LUNAR_RECON_BASE + RECON_FROM_UNMANNED_LANDING_FAIL
    assert me.lm_points == 0


def test_manned_orbital_success_grants_one_lm_point() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.reliability[Rocket.MEDIUM.value] = 70
    me.budget = 200
    for a in me.astronauts:
        a.capsule = 60

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.MANNED_ORBITAL)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=_FixedRng(0.0))
    _fire_scheduled_launch(state, _FixedRng(0.0))

    assert me.lm_points == 1


def test_effective_lunar_modifier_zero_for_non_lunar_landing_mission() -> None:
    me = Player(player_id="a", username="A", side=Side.USA)
    me.lunar_recon = LUNAR_RECON_CAP  # max recon
    me.lm_points = 10                 # way over required
    m = MISSIONS_BY_ID[MissionId.SUBORBITAL]
    assert effective_lunar_modifier(me, m) == (0.0, 0.0)


def test_effective_lunar_modifier_applies_recon_bonus_and_lm_penalty() -> None:
    me = Player(player_id="a", username="A", side=Side.USA)
    me.lunar_recon = LUNAR_RECON_BASE + 20   # 20% above baseline
    me.lm_points = 1                         # 2 points short of required
    m = MISSIONS_BY_ID[MissionId.MANNED_LUNAR_LANDING]
    recon_bonus, lm_penalty = effective_lunar_modifier(me, m)
    assert abs(recon_bonus - 20 * LUNAR_RECON_PER_POINT) < 1e-9
    missing = LM_POINTS_REQUIRED - 1
    assert abs(lm_penalty - missing * LM_POINTS_PENALTY_PER_MISSING) < 1e-9


def test_manned_landing_report_carries_recon_and_lm_modifiers() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.reliability[Rocket.HEAVY.value] = 70
    me.reliability[Module.EVA_SUIT.value] = 70
    me.reliability[Module.LUNAR_KICKER.value] = 70
    me.budget = 100
    me.mission_successes[MissionId.SUBORBITAL.value] = 1
    me.mission_successes[MissionId.MULTI_CREW_ORBITAL.value] = 1
    me.lunar_recon = LUNAR_RECON_BASE + 10
    me.lm_points = LM_POINTS_REQUIRED  # no penalty
    choose_architecture(me, Architecture.LOR)
    for a in me.astronauts:
        a.lm_pilot = 100

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.MANNED_LUNAR_LANDING)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=_FixedRng(0.0))
    _fire_scheduled_launch(state, _FixedRng(0.0))

    assert len(state.last_launches) == 1
    r = state.last_launches[0]
    assert abs(r.lunar_recon_bonus - 10 * LUNAR_RECON_PER_POINT) < 1e-9
    assert r.lm_points_penalty == 0.0


def test_recon_caps_at_LUNAR_RECON_CAP() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.lunar_recon = LUNAR_RECON_CAP - 1   # near the cap
    me.mission_successes[MissionId.SUBORBITAL.value] = 1
    me.reliability[Rocket.MEDIUM.value] = 70
    me.reliability[Module.LUNAR_KICKER.value] = 70
    me.budget = 200

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.LUNAR_PASS)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=_FixedRng(0.0))
    _fire_scheduled_launch(state, _FixedRng(0.0))

    assert me.lunar_recon == LUNAR_RECON_CAP


# ----------------------------------------------------------------------
# Phase E — multiple launch pads
# ----------------------------------------------------------------------


def test_default_player_has_three_idle_pads() -> None:
    p = Player(player_id="a", username="A", side=Side.USA)
    assert [pad.pad_id for pad in p.pads] == ["A", "B", "C"]
    assert all(pad.available for pad in p.pads)
    assert p.any_pad_available() is True
    assert p.scheduled_launches() == []
    # Back-compat accessor still works.
    assert p.scheduled_launch is None


def test_submit_schedules_into_first_available_pad() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.reliability[Rocket.LIGHT.value] = 70

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.SUBORBITAL)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=_FixedRng(0.0))

    # First pad (A) gets the assembly; B/C stay idle.
    assert me.pads[0].scheduled_launch is not None
    assert me.pads[0].scheduled_launch.mission_id == MissionId.SUBORBITAL.value
    assert me.pads[1].scheduled_launch is None
    assert me.pads[2].scheduled_launch is None


def test_two_pads_can_hold_parallel_schedules_and_both_fire() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.reliability[Rocket.LIGHT.value] = 70
    me.budget = 200

    # Turn 1: submit SUBORBITAL → lands on pad A.
    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.SUBORBITAL)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=_FixedRng(0.0))
    assert me.pads[0].scheduled_launch is not None

    # Turn 2: submit SATELLITE while pad A's SUBORBITAL fires this same
    # resolve. Order within a resolve is: fire-all-pads → promote-pending,
    # so pad A's SUBORBITAL flies, clears the slot, and then SATELLITE is
    # promoted into that same (now-empty) pad A. Pads B and C stay idle.
    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.SATELLITE)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=_FixedRng(0.0))
    # One report from this resolve (pad A firing SUBORBITAL).
    assert len(state.last_launches) == 1
    assert state.last_launches[0].mission_id == MissionId.SUBORBITAL.value
    # SATELLITE is now sitting on pad A for next turn's fire.
    assert me.pads[0].scheduled_launch is not None
    assert me.pads[0].scheduled_launch.mission_id == MissionId.SATELLITE.value
    assert me.pads[1].scheduled_launch is None


def test_both_pads_resolved_in_one_turn_produce_two_reports() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.reliability[Rocket.LIGHT.value] = 70
    me.budget = 400
    # Manually seed two scheduled launches on pads A and B.
    from baris.state import ScheduledLaunch
    for pad_idx, mid in ((0, MissionId.SUBORBITAL), (1, MissionId.SATELLITE)):
        mission = MISSIONS_BY_ID[mid]
        me.pads[pad_idx].scheduled_launch = ScheduledLaunch(
            mission_id=mid.value,
            rocket_class=Rocket.LIGHT.value,
            launch_cost_total=mission.launch_cost,
            assembly_cost_paid=int(mission.launch_cost * ASSEMBLY_COST_FRACTION),
            launch_cost_remaining=mission.launch_cost - int(mission.launch_cost * ASSEMBLY_COST_FRACTION),
            objectives=[],
        )

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=None)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=_FixedRng(0.0))

    assert len(state.last_launches) == 2
    fired = {r.mission_id for r in state.last_launches}
    assert fired == {MissionId.SUBORBITAL.value, MissionId.SATELLITE.value}
    assert me.pads[0].scheduled_launch is None
    assert me.pads[1].scheduled_launch is None


def test_scrub_scheduled_targets_specific_pad_by_id() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.reliability[Rocket.LIGHT.value] = 70
    me.budget = 100
    # Seed scheduled launches on pads A and B so we can prove scrub
    # picks the right one.
    from baris.state import ScheduledLaunch
    for pad in me.pads[:2]:
        pad.scheduled_launch = ScheduledLaunch(
            mission_id=MissionId.SUBORBITAL.value,
            rocket_class=Rocket.LIGHT.value,
            launch_cost_total=3, assembly_cost_paid=1,
            launch_cost_remaining=2, objectives=[],
        )
    assert scrub_scheduled(me, pad_id="B")
    assert me.pads[0].scheduled_launch is not None   # A still booked
    assert me.pads[1].scheduled_launch is None       # B cleared


def test_catastrophic_failure_damages_launching_pad() -> None:
    """A manned failure that kills a crew member puts the pad into
    repair for PAD_REPAIR_TURNS seasons."""
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.reliability[Rocket.MEDIUM.value] = 70
    me.budget = 200
    for a in me.astronauts:
        a.capsule = 50

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.MANNED_ORBITAL)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    # Force failure (0.99) + force death (0.01) + skip hospital (0.99).
    resolve_turn(state, rng=_FixedRng(0.99))
    _fire_scheduled_launch(
        state, _SeqRngTrain([0.99, 0.01, 0.99]),
    )
    pad_a = me.pads[0]
    assert pad_a.scheduled_launch is None
    assert pad_a.damaged is True
    from baris.state import PAD_REPAIR_TURNS
    assert pad_a.repair_turns_remaining == PAD_REPAIR_TURNS


def test_pad_repair_ticks_down_and_pad_becomes_available() -> None:
    from baris.state import PAD_REPAIR_TURNS
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.pads[0].repair_turns_remaining = PAD_REPAIR_TURNS

    for _ in range(PAD_REPAIR_TURNS):
        submit_turn(me, rd_rocket=None, rd_spend=0, launch=None)
        submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
        resolve_turn(state, rng=_FixedRng(0.0))

    assert me.pads[0].repair_turns_remaining == 0
    assert me.pads[0].available is True


def test_legacy_scheduled_launch_in_dict_migrates_into_pad_A() -> None:
    from baris.state import _player_from_dict
    raw_player = {
        "player_id": "a", "username": "Alice",
        "side": "USA",
        "budget": 30, "prestige": 0, "ready": False,
        "reliability": {}, "astronauts": [],
        "mission_successes": {}, "architecture": None,
        "turn_submitted": False,
        "pending_rd_target": None, "pending_rd_spend": 0,
        "pending_launch": None, "pending_objectives": [],
        # Legacy shape — single-slot scheduled_launch, no pads key.
        "scheduled_launch": {
            "mission_id": MissionId.SUBORBITAL.value,
            "rocket_class": Rocket.LIGHT.value,
            "launch_cost_total": 3, "assembly_cost_paid": 1,
            "launch_cost_remaining": 2, "objectives": [],
        },
    }
    p = _player_from_dict(raw_player)
    assert p.pads[0].scheduled_launch is not None
    assert p.pads[0].scheduled_launch.mission_id == MissionId.SUBORBITAL.value
    assert p.pads[1].scheduled_launch is None
    assert p.pads[2].scheduled_launch is None


class _SeqRngTrain:
    """Sequence RNG used by the pad-damage test above. The standalone
    _SeqRng inside other tests is local-scope; duplicate it here."""
    def __init__(self, values):
        self.values = list(values)
        self._r = random.Random(1)
    def random(self) -> float:
        return self.values.pop(0)
    def randint(self, a, b):
        return self._r.randint(a, b)
    def choice(self, seq):
        return self._r.choice(seq)


# ----------------------------------------------------------------------
# Phase F — hardware-module prereqs (Lunar Kicker / EVA Suit)
# ----------------------------------------------------------------------


def test_lunar_mission_without_kicker_is_rejected_at_submit() -> None:
    from baris.resolver import missing_modules
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.mission_successes[MissionId.SUBORBITAL.value] = 1  # unlock Tier 2
    me.reliability[Rocket.MEDIUM.value] = 70              # flyby uses Medium
    # No kicker built → submit_turn should reject the queue.
    assert missing_modules(me, MISSIONS_BY_ID[MissionId.LUNAR_PASS]) == [Module.LUNAR_KICKER]

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.LUNAR_PASS)
    assert me.pending_launch is None


def test_lunar_mission_with_kicker_built_is_accepted() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.mission_successes[MissionId.SUBORBITAL.value] = 1
    me.reliability[Rocket.MEDIUM.value] = 70
    me.reliability[Module.LUNAR_KICKER.value] = 70

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.LUNAR_PASS)
    assert me.pending_launch == MissionId.LUNAR_PASS.value


def test_manned_lunar_landing_needs_both_kicker_and_eva_suit() -> None:
    from baris.resolver import missing_modules
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.mission_successes[MissionId.SUBORBITAL.value] = 1
    me.mission_successes[MissionId.MULTI_CREW_ORBITAL.value] = 1
    me.reliability[Rocket.HEAVY.value] = 70
    choose_architecture(me, Architecture.LOR)
    mll = MISSIONS_BY_ID[MissionId.MANNED_LUNAR_LANDING]

    # No modules → both missing.
    assert set(missing_modules(me, mll)) == {Module.LUNAR_KICKER, Module.EVA_SUIT}

    # Only kicker → EVA Suit still missing; still rejected.
    me.reliability[Module.LUNAR_KICKER.value] = 70
    assert missing_modules(me, mll) == [Module.EVA_SUIT]
    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.MANNED_LUNAR_LANDING)
    assert me.pending_launch is None

    # Both built → accepted.
    me.reliability[Module.EVA_SUIT.value] = 70
    assert missing_modules(me, mll) == []
    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.MANNED_LUNAR_LANDING)
    assert me.pending_launch == MissionId.MANNED_LUNAR_LANDING.value


def test_orbital_eva_mission_needs_eva_suit() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.mission_successes[MissionId.SUBORBITAL.value] = 1
    me.reliability[Rocket.MEDIUM.value] = 70
    # No EVA suit → rejected.
    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.ORBITAL_EVA)
    assert me.pending_launch is None

    me.reliability[Module.EVA_SUIT.value] = 70
    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.ORBITAL_EVA)
    assert me.pending_launch == MissionId.ORBITAL_EVA.value


def test_eva_objective_still_filters_on_eva_suit() -> None:
    """Phase F made the EVA objective require EVA_SUIT. Queuing it without
    the suit built should drop the objective at submit time even though
    the base mission (MANNED_ORBITAL) doesn't need the suit."""
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.reliability[Rocket.MEDIUM.value] = 70
    me.budget = 100
    for a in me.astronauts:
        a.capsule = 50

    # EVA Suit NOT built → EVA objective should be dropped.
    submit_turn(
        me, rd_rocket=None, rd_spend=0,
        launch=MissionId.MANNED_ORBITAL,
        objectives=[ObjectiveId.EVA],
    )
    assert me.pending_launch == MissionId.MANNED_ORBITAL.value
    assert me.pending_objectives == []

    # Build the suit → EVA objective sticks.
    me.reliability[Module.EVA_SUIT.value] = 70
    # Re-submit next turn (clear old pending first via a dummy resolve).
    me.pending_objectives = []
    submit_turn(
        me, rd_rocket=None, rd_spend=0,
        launch=MissionId.MANNED_ORBITAL,
        objectives=[ObjectiveId.EVA],
    )
    assert me.pending_objectives == [ObjectiveId.EVA.value]


# ----------------------------------------------------------------------
# Phase G — expanded mission catalog (flybys, LM tests, orbital docking)
# ----------------------------------------------------------------------


def test_venus_flyby_grants_prestige_without_lunar_recon() -> None:
    """Interplanetary probes don't feed the Moon-specific recon counter."""
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.mission_successes[MissionId.SUBORBITAL.value] = 1  # unlock Tier 2
    me.reliability[Rocket.MEDIUM.value] = 70
    me.reliability[Module.LUNAR_KICKER.value] = 70
    me.budget = 200
    recon_before = me.lunar_recon
    lm_before = me.lm_points

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.VENUS_FLYBY)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=_FixedRng(0.0))
    _fire_scheduled_launch(state, _FixedRng(0.0))

    r = state.last_launches[0]
    assert r.success is True
    # Prestige bumped, lunar recon and LM points untouched.
    assert me.prestige > 0
    assert me.lunar_recon == recon_before
    assert me.lm_points == lm_before


def test_lm_earth_test_grants_one_lm_point() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    # LM_EARTH_TEST is Tier 3 → unlock both prior tiers' prereqs.
    me.mission_successes[MissionId.SUBORBITAL.value] = 1
    me.mission_successes[MissionId.MULTI_CREW_ORBITAL.value] = 1
    me.reliability[Rocket.MEDIUM.value] = 70
    me.budget = 200

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.LM_EARTH_TEST)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=_FixedRng(0.0))
    _fire_scheduled_launch(state, _FixedRng(0.0))

    assert state.last_launches[0].success is True
    assert me.lm_points == 1


def test_lm_lunar_test_grants_two_lm_points_and_recon() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.mission_successes[MissionId.SUBORBITAL.value] = 1
    me.mission_successes[MissionId.MULTI_CREW_ORBITAL.value] = 1
    me.reliability[Rocket.HEAVY.value] = 70
    me.reliability[Module.LUNAR_KICKER.value] = 70
    me.budget = 200
    recon_before = me.lunar_recon

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.LM_LUNAR_TEST)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=_FixedRng(0.0))
    _fire_scheduled_launch(state, _FixedRng(0.0))

    assert state.last_launches[0].success is True
    assert me.lm_points == 2
    assert me.lunar_recon > recon_before  # lunar orbit → recon bump


def test_orbital_docking_mission_needs_docking_module() -> None:
    from baris.resolver import missing_modules
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.mission_successes[MissionId.SUBORBITAL.value] = 1  # unlock Tier 2
    me.reliability[Rocket.MEDIUM.value] = 70
    me.budget = 200

    # No docking module → rejected.
    assert missing_modules(me, MISSIONS_BY_ID[MissionId.ORBITAL_DOCKING]) == [Module.DOCKING]
    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.ORBITAL_DOCKING)
    assert me.pending_launch is None

    # Build it → accepted, and a successful resolve awards an LM point.
    me.reliability[Module.DOCKING.value] = 70
    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.ORBITAL_DOCKING)
    assert me.pending_launch == MissionId.ORBITAL_DOCKING.value
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=_FixedRng(0.0))
    _fire_scheduled_launch(state, _FixedRng(0.0))
    assert state.last_launches[0].success is True
    assert me.lm_points == 1


def test_catalog_expanded_to_expected_size() -> None:
    """Quick guard that the Phase G additions didn't accidentally go
    missing — total missions should be 19 (11 pre-G + 8 new)."""
    assert len(MISSIONS_BY_ID) == 19
    # And every new id is present and has the right rough shape.
    for new in (
        MissionId.VENUS_FLYBY, MissionId.MARS_FLYBY, MissionId.MERCURY_FLYBY,
        MissionId.JUPITER_FLYBY, MissionId.SATURN_FLYBY,
        MissionId.ORBITAL_DOCKING, MissionId.LM_EARTH_TEST, MissionId.LM_LUNAR_TEST,
    ):
        m = MISSIONS_BY_ID[new]
        assert m.name
        assert m.launch_cost > 0


# ----------------------------------------------------------------------
# Phase K — crew compatibility + mood + retirement
# ----------------------------------------------------------------------


def test_starting_roster_seeds_compatibility_and_default_mood() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(7))
    me = state.players[0]
    for astro in me.astronauts:
        assert astro.compatibility in {c.value for c in Compatibility}
        assert astro.mood == MOOD_DEFAULT


def test_crew_compatibility_bonus_same_type_all_matching() -> None:
    crew = [_make_astronaut(f"X{i}") for i in range(3)]
    for a in crew:
        a.compatibility = Compatibility.A.value
    assert abs(crew_compatibility_bonus(crew) - CREW_COMPAT_MAX_BONUS) < 1e-9


def test_crew_compatibility_bonus_opposite_pair_penalises() -> None:
    a = _make_astronaut("A")
    a.compatibility = Compatibility.A.value
    b = _make_astronaut("B")
    b.compatibility = Compatibility.C.value   # opposite of A
    assert abs(crew_compatibility_bonus([a, b]) - (-CREW_COMPAT_MAX_BONUS)) < 1e-9


def test_solo_or_empty_crew_compatibility_bonus_is_zero() -> None:
    assert crew_compatibility_bonus([]) == 0.0
    a = _make_astronaut("A")
    a.compatibility = Compatibility.B.value
    assert crew_compatibility_bonus([a]) == 0.0


def test_mission_success_bumps_crew_mood_up() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.reliability[Rocket.MEDIUM.value] = 70
    me.budget = 200
    for a in me.astronauts:
        a.capsule = 80
        a.mood = 70

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.MANNED_ORBITAL)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=_FixedRng(0.0))
    _fire_scheduled_launch(state, _FixedRng(0.0))

    # Exactly one astronaut flew; their mood should be +MOOD_SUCCESS_BUMP
    # (minus the single MOOD_DRIFT_PER_TURN toward MOOD_DRIFT_TARGET=60 that
    # runs each resolve).
    flown = [a for a in me.astronauts if a.mood != 70]
    assert len(flown) >= 1
    assert max(a.mood for a in me.astronauts) >= 70 + MOOD_SUCCESS_BUMP - 4


def test_mission_failure_drops_crew_mood() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.reliability[Rocket.MEDIUM.value] = 70
    me.budget = 200
    for a in me.astronauts:
        a.capsule = 50
        a.mood = 70

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.MANNED_ORBITAL)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    # Force failure, no death, no hospital — isolates the morale hit.
    with _no_news():
        resolve_turn(state, rng=_FixedRng(0.99))
        _fire_scheduled_launch(state, _FixedRng(0.99))

    # At least one astronaut's mood dropped by roughly MOOD_FAILURE_DROP
    # (mood drift also runs, so accept a small tolerance).
    lowest = min(a.mood for a in me.astronauts)
    assert lowest <= 70 - MOOD_FAILURE_DROP + 2


def test_crew_kia_drops_survivor_mood_extra() -> None:
    """A 2-crew mission where one dies: the survivor eats both the
    failure drop AND a KIA-per-dead penalty."""

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
    me.budget = 200
    me.mission_successes[MissionId.SUBORBITAL.value] = 1
    for a in me.astronauts:
        a.endurance = 80
        a.mood = 80

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.MULTI_CREW_ORBITAL)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    # Success roll high (fail), first death roll low (kill crew[0]), second
    # death roll high (spare crew[1]), hospital rolls high (no hospital).
    with _no_news():
        resolve_turn(state, rng=_FixedRng(0.0))
        _fire_scheduled_launch(state, _SeqRng([0.99, 0.01, 0.99, 0.99, 0.99]))

    kia_count = sum(1 for a in me.astronauts if a.status == "kia")
    assert kia_count == 1
    survivors = [a for a in me.astronauts if a.status == "active"]
    # Mood floor from the failure: the actual flying crew hit.
    # Expected drop = failure drop + 1 * KIA drop. Drift may claw back a bit.
    min_mood = min(a.mood for a in survivors)
    expected_after = 80 - MOOD_FAILURE_DROP - MOOD_KIA_CREW_DROP
    assert min_mood <= expected_after + 2


def test_astronaut_below_threshold_retires_on_tick() -> None:
    """Mood drift runs before the retirement check, so an astronaut
    whose mood is drifting back up from a single low-mood turn won't
    retire. Set morale low enough that even after a full drift step
    they're still at or below the retirement threshold."""
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    # Start well below threshold so drift (+MOOD_DRIFT_PER_TURN) doesn't
    # lift them past MOOD_RETIREMENT_THRESHOLD this turn.
    me.astronauts[0].mood = max(0, MOOD_RETIREMENT_THRESHOLD - 5)

    submit_turn(me, rd_rocket=None, rd_spend=0, launch=None)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    resolve_turn(state, rng=_FixedRng(0.0))

    assert me.astronauts[0].status == "retired"
    assert me.astronauts[0].flight_ready is False


def test_compatibility_and_mood_roundtrip_through_state_dict() -> None:
    me = Player(player_id="a", username="Alice", side=Side.USA)
    me.astronauts = [Astronaut(
        id="x", name="X",
        compatibility=Compatibility.D.value,
        mood=44,
    )]
    state = GameState(players=[me])
    restored = GameState.from_dict(state.to_dict())
    ra = restored.players[0].astronauts[0]
    assert ra.compatibility == Compatibility.D.value
    assert ra.mood == 44


def test_legacy_astronaut_dict_backfills_compat_and_mood() -> None:
    from baris.state import _astronaut_from_dict
    raw = {
        "id": "x", "name": "X",
        "capsule": 10, "lm_pilot": 0, "eva": 0, "docking": 0, "endurance": 0,
        "status": "active",
    }
    a = _astronaut_from_dict(raw)
    assert a.compatibility == Compatibility.A.value
    assert a.mood == MOOD_DEFAULT


# ----------------------------------------------------------------------
# Phase J — recruitment groups
# ----------------------------------------------------------------------


def test_start_game_auto_hires_group_one() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    for p in state.players:
        assert len(p.astronauts) == RECRUITMENT_GROUPS[0].size
        # Group 1 is already hired, so the pointer points at group 2.
        assert p.next_recruitment_group == 2


def test_recruit_next_group_hires_second_group() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    p = state.players[0]
    group = RECRUITMENT_GROUPS[1]
    state.year = group.earliest_year
    p.budget = group.cost + 10
    before = len(p.astronauts)
    assert recruit_next_group(p, state, rng=random.Random(2))
    assert len(p.astronauts) == before + group.size
    assert p.next_recruitment_group == 3
    assert p.budget == 10  # cost deducted


def test_recruit_next_group_rejected_before_earliest_year() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    p = state.players[0]
    group = RECRUITMENT_GROUPS[1]
    state.year = group.earliest_year - 1
    p.budget = group.cost + 100
    before = len(p.astronauts)
    assert not recruit_next_group(p, state, rng=random.Random(2))
    assert len(p.astronauts) == before
    assert p.next_recruitment_group == 2


def test_recruit_next_group_rejected_without_budget() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    p = state.players[0]
    group = RECRUITMENT_GROUPS[1]
    state.year = group.earliest_year
    p.budget = group.cost - 1
    before = len(p.astronauts)
    assert not recruit_next_group(p, state, rng=random.Random(2))
    assert len(p.astronauts) == before


def test_recruit_next_group_rejected_when_all_hired() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    p = state.players[0]
    p.next_recruitment_group = len(RECRUITMENT_GROUPS) + 1
    state.year = 1999
    p.budget = 1000
    before = len(p.astronauts)
    assert not recruit_next_group(p, state, rng=random.Random(2))
    assert len(p.astronauts) == before


def test_new_recruits_start_in_basic_training() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    p = state.players[0]
    group = RECRUITMENT_GROUPS[1]
    state.year = group.earliest_year
    p.budget = group.cost
    before = len(p.astronauts)
    recruit_next_group(p, state, rng=random.Random(2))
    new_hires = p.astronauts[before:]
    assert len(new_hires) == group.size
    for a in new_hires:
        assert a.basic_training_remaining == BASIC_TRAINING_TURNS
        assert not a.flight_ready
        assert RECRUIT_SKILL_MIN <= a.capsule <= RECRUIT_SKILL_MAX


def test_next_recruitment_preview_states() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    p = state.players[0]
    group = RECRUITMENT_GROUPS[1]
    # too early
    state.year = group.earliest_year - 2
    p.budget = group.cost + 50
    g, ok, reason = next_recruitment_preview(p, state)
    assert g is group and not ok and str(group.earliest_year) in reason
    # affordable
    state.year = group.earliest_year
    g, ok, reason = next_recruitment_preview(p, state)
    assert g is group and ok
    # broke
    p.budget = group.cost - 1
    g, ok, reason = next_recruitment_preview(p, state)
    assert g is group and not ok and "MB" in reason
    # exhausted
    p.next_recruitment_group = len(RECRUITMENT_GROUPS) + 1
    g, ok, _ = next_recruitment_preview(p, state)
    assert g is None and not ok


def test_recruit_group_dict_roundtrip() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    p = state.players[0]
    p.next_recruitment_group = 3
    restored = GameState.from_dict(state.to_dict())
    assert restored.players[0].next_recruitment_group == 3


def test_legacy_player_dict_backfills_recruitment_pointer() -> None:
    from baris.state import _player_from_dict
    raw = {
        "player_id": "x", "username": "X",
        "side": Side.USA.value, "budget": 30, "prestige": 0,
        "ready": True, "astronauts": [],
        "mission_successes": {}, "architecture": None,
        "turn_submitted": False,
    }
    p = _player_from_dict(raw)
    assert p.next_recruitment_group == 2


# ----------------------------------------------------------------------
# Phase I — seasonal news
# ----------------------------------------------------------------------


def _start_for_news() -> GameState:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    return state


def _submit_empty_turns(state: GameState) -> None:
    for p in state.players:
        submit_turn(p, rd_rocket=None, rd_spend=0, launch=None)


def test_resolve_turn_records_a_news_headline() -> None:
    state = _start_for_news()
    _submit_empty_turns(state)
    resolve_turn(state, rng=random.Random(7))
    assert state.current_news        # non-empty
    assert state.current_news_id     # machine id populated
    assert any(line.startswith("NEWS:") for line in state.log)


def test_budget_windfall_bumps_both_players() -> None:
    from baris.resolver import _news_budget_windfall, NEWS_BUDGET_WINDFALL_DELTA
    state = _start_for_news()
    before = [p.budget for p in state.players]
    headline = _news_budget_windfall(state, random.Random(0))
    assert headline
    for i, p in enumerate(state.players):
        assert p.budget == before[i] + NEWS_BUDGET_WINDFALL_DELTA


def test_budget_cut_floors_at_zero() -> None:
    from baris.resolver import _news_budget_cut
    state = _start_for_news()
    for p in state.players:
        p.budget = 1
    _news_budget_cut(state, random.Random(0))
    for p in state.players:
        assert p.budget == 0


def test_press_tour_targets_leader() -> None:
    from baris.resolver import _news_press_tour, NEWS_PRESS_TOUR_PRESTIGE
    state = _start_for_news()
    state.players[0].prestige = 10
    state.players[1].prestige = 3
    before = state.players[0].prestige
    _news_press_tour(state, random.Random(0))
    assert state.players[0].prestige == before + NEWS_PRESS_TOUR_PRESTIGE
    # Trailing player untouched.
    assert state.players[1].prestige == 3


def test_defector_targets_trailing() -> None:
    from baris.resolver import _news_defector, NEWS_DEFECTOR_PRESTIGE
    state = _start_for_news()
    state.players[0].prestige = 10
    state.players[1].prestige = 3
    before = state.players[1].prestige
    _news_defector(state, random.Random(0))
    assert state.players[1].prestige == before + NEWS_DEFECTOR_PRESTIGE
    assert state.players[0].prestige == 10


def test_defector_declines_on_exact_tie() -> None:
    from baris.resolver import _news_defector
    state = _start_for_news()
    # Same prestige, same successes → no underdog to target.
    state.players[0].prestige = state.players[1].prestige = 5
    assert _news_defector(state, random.Random(0)) == ""


def test_reliability_breakthrough_requires_built_rocket() -> None:
    from baris.resolver import _news_reliability_breakthrough
    state = _start_for_news()
    # Nobody has anything built — event should decline.
    assert _news_reliability_breakthrough(state, random.Random(0)) == ""


def test_reliability_breakthrough_bumps_some_side() -> None:
    from baris.resolver import (
        _news_reliability_breakthrough, NEWS_RELIABILITY_DELTA,
    )
    state = _start_for_news()
    state.players[0].reliability[Rocket.MEDIUM.value] = 50
    total_before = sum(
        p.rocket_reliability(r)
        for p in state.players for r in Rocket
    )
    headline = _news_reliability_breakthrough(state, random.Random(0))
    assert headline
    total_after = sum(
        p.rocket_reliability(r)
        for p in state.players for r in Rocket
    )
    assert total_after == total_before + NEWS_RELIABILITY_DELTA


def test_crew_morale_boost_lifts_active_mood() -> None:
    from baris.resolver import _news_crew_morale_boost, NEWS_MOOD_BOOST
    state = _start_for_news()
    for p in state.players:
        for a in p.astronauts:
            a.mood = 50
    _news_crew_morale_boost(state, random.Random(0))
    # At least one side was boosted; check any mood moved up.
    lifted = [a.mood for p in state.players for a in p.astronauts if a.mood > 50]
    assert lifted
    assert max(lifted) == 50 + NEWS_MOOD_BOOST


def test_news_dict_roundtrip() -> None:
    state = _start_for_news()
    state.current_news = "Test headline"
    state.current_news_id = "test_id"
    restored = GameState.from_dict(state.to_dict())
    assert restored.current_news == "Test headline"
    assert restored.current_news_id == "test_id"


def test_legacy_state_dict_backfills_news_fields() -> None:
    state = _start_for_news()
    raw = state.to_dict()
    raw.pop("current_news", None)
    raw.pop("current_news_id", None)
    restored = GameState.from_dict(raw)
    assert restored.current_news == ""
    assert restored.current_news_id == ""


# ----------------------------------------------------------------------
# Phase H — intelligence
# ----------------------------------------------------------------------


def _start_for_intel() -> tuple[GameState, object, object]:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    return state, state.players[0], state.players[1]


def test_request_intel_succeeds_and_charges_cost() -> None:
    state, me, opp = _start_for_intel()
    me.budget = 50
    opp.reliability[Rocket.MEDIUM.value] = 60
    assert request_intel(me, state, rng=random.Random(0))
    assert me.budget == 50 - INTEL_COST
    assert me.latest_intel is not None
    assert me.latest_intel.opponent_side == Side.USSR.value


def test_request_intel_rejected_without_budget() -> None:
    state, me, _ = _start_for_intel()
    me.budget = INTEL_COST - 1
    assert not request_intel(me, state)
    assert me.latest_intel is None


def test_request_intel_rejected_twice_in_same_season() -> None:
    state, me, _ = _start_for_intel()
    me.budget = 100
    assert request_intel(me, state, rng=random.Random(0))
    assert not request_intel(me, state, rng=random.Random(0))
    # Budget only charged once.
    assert me.budget == 100 - INTEL_COST


def test_intel_reliability_bands_bracket_truth() -> None:
    state, me, opp = _start_for_intel()
    me.budget = 50
    opp.reliability[Rocket.HEAVY.value] = 70
    request_intel(me, state, rng=random.Random(0))
    low, high = me.latest_intel.rocket_estimates[Rocket.HEAVY.value]
    assert low <= 70 <= high
    assert high - low <= 2 * INTEL_RELIABILITY_NOISE


def test_intel_rumor_truthful_when_roll_low() -> None:
    from baris.state import MissionId, ScheduledLaunch
    state, me, opp = _start_for_intel()
    me.budget = 50
    opp.pads[0].scheduled_launch = ScheduledLaunch(
        mission_id=MissionId.SUBORBITAL.value,
        rocket_class=Rocket.LIGHT.value,
        launch_cost_total=10,
        assembly_cost_paid=3,
        launch_cost_remaining=7,
        objectives=[],
        scheduled_year=state.year,
        scheduled_season=state.season.value,
    )
    # INTEL_RUMOR_ACCURATE = 0.8; rng.random()=0.0 ≤ 0.8 → truthful.
    request_intel(me, state, rng=_FixedRng(0.0))
    assert me.latest_intel.rumored_mission == MissionId.SUBORBITAL.value
    assert me.latest_intel.rumored_mission_name


def test_intel_rumor_misinformation_when_roll_high() -> None:
    from baris.state import MissionId, ScheduledLaunch
    state, me, opp = _start_for_intel()
    me.budget = 50
    opp.pads[0].scheduled_launch = ScheduledLaunch(
        mission_id=MissionId.SUBORBITAL.value,
        rocket_class=Rocket.LIGHT.value,
        launch_cost_total=10,
        assembly_cost_paid=3,
        launch_cost_remaining=7,
        objectives=[],
        scheduled_year=state.year,
        scheduled_season=state.season.value,
    )
    # rng.random()=0.99 > 0.8 → empty rumor (intentional misinformation).
    request_intel(me, state, rng=_FixedRng(0.99))
    assert me.latest_intel.rumored_mission == ""


def test_intel_available_returns_clear_reasons() -> None:
    state, me, _ = _start_for_intel()
    me.budget = 0
    ok, reason = intel_available(me, state)
    assert not ok and "MB" in reason
    me.budget = 100
    me.intel_requested_on = f"{state.year}-{state.season.value}"
    ok, reason = intel_available(me, state)
    assert not ok and "season" in reason
    me.intel_requested_on = ""
    ok, _ = intel_available(me, state)
    assert ok


def test_intel_report_dict_roundtrip() -> None:
    state, me, opp = _start_for_intel()
    me.budget = 50
    request_intel(me, state, rng=random.Random(0))
    restored = GameState.from_dict(state.to_dict())
    r = restored.players[0].latest_intel
    assert isinstance(r, IntelReport)
    assert r.opponent_side == me.latest_intel.opponent_side
    assert r.rocket_estimates == me.latest_intel.rocket_estimates


def test_legacy_player_dict_backfills_intel_fields() -> None:
    from baris.state import _player_from_dict
    raw = {
        "player_id": "x", "username": "X",
        "side": Side.USA.value, "budget": 30, "prestige": 0,
        "ready": True, "astronauts": [],
        "mission_successes": {}, "architecture": None,
        "turn_submitted": False,
    }
    p = _player_from_dict(raw)
    assert p.latest_intel is None
    assert p.intel_requested_on == ""


# ----------------------------------------------------------------------
# Phase L — Museum: mission history + prestige timeline
# ----------------------------------------------------------------------


def test_start_game_seeds_prestige_timeline_at_zero() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    assert len(state.prestige_timeline) == 1
    snap = state.prestige_timeline[0]
    assert snap.year == state.year
    assert snap.usa_prestige == 0
    assert snap.ussr_prestige == 0
    # No missions have flown yet.
    assert state.mission_history == []


def test_season_advance_appends_prestige_snapshot() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    # Submit two empty turns to advance one season.
    for p in state.players:
        submit_turn(p, rd_rocket=None, rd_spend=0, launch=None)
    with _no_news():
        resolve_turn(state, rng=random.Random(5))
    # Seeded snapshot (t=0) + post-advance snapshot = 2 entries.
    assert len(state.prestige_timeline) == 2
    last = state.prestige_timeline[-1]
    assert (last.year, last.season) == (state.year, state.season.value)


def test_successful_launch_appends_mission_history() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.reliability[Rocket.LIGHT.value] = 80
    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.SUBORBITAL)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    with _no_news():
        resolve_turn(state, rng=_FixedRng(0.99))
        _fire_scheduled_launch(state, _FixedRng(0.0))
    entries = [e for e in state.mission_history
               if e.side == Side.USA.value
               and e.mission_id == MissionId.SUBORBITAL.value]
    assert len(entries) == 1
    e = entries[0]
    assert e.success is True
    assert e.manned is False
    assert e.first_claimed  # first-ever suborbital
    assert e.prestige_delta > 0


def test_failed_launch_also_appends_history() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.reliability[Rocket.LIGHT.value] = 30  # above MIN_RELIABILITY_TO_LAUNCH
    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.SUBORBITAL)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    with _no_news():
        resolve_turn(state, rng=_FixedRng(0.99))
        _fire_scheduled_launch(state, _FixedRng(0.99))
    entries = [e for e in state.mission_history
               if e.mission_id == MissionId.SUBORBITAL.value]
    assert len(entries) == 1
    assert entries[0].success is False


def test_aborted_launch_not_recorded_in_history() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    # Reliability below MIN_RELIABILITY_TO_LAUNCH triggers abort path.
    me.reliability[Rocket.LIGHT.value] = 10
    submit_turn(me, rd_rocket=None, rd_spend=0, launch=MissionId.SUBORBITAL)
    submit_turn(state.players[1], rd_rocket=None, rd_spend=0, launch=None)
    before = len(state.mission_history)
    with _no_news():
        resolve_turn(state, rng=_FixedRng(0.99))
        _fire_scheduled_launch(state, _FixedRng(0.99))
    assert len(state.mission_history) == before


def test_museum_dict_roundtrip() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    state.mission_history.append(MissionHistoryEntry(
        year=1958, season="Fall", side=Side.USA.value,
        mission_id=MissionId.SUBORBITAL.value,
        mission_name="Sub-orbital flight",
        rocket="Redstone",
        success=True, prestige_delta=5, first_claimed=True,
    ))
    state.prestige_timeline.append(PrestigeSnapshot(
        year=1958, season="Fall", usa_prestige=5, ussr_prestige=0,
    ))
    restored = GameState.from_dict(state.to_dict())
    assert len(restored.mission_history) == 1
    r = restored.mission_history[0]
    assert r.mission_name == "Sub-orbital flight"
    assert r.success is True
    assert r.first_claimed is True
    assert len(restored.prestige_timeline) >= 2
    assert restored.prestige_timeline[-1].usa_prestige == 5


def test_legacy_state_dict_backfills_museum_fields() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    raw = state.to_dict()
    raw.pop("mission_history", None)
    raw.pop("prestige_timeline", None)
    restored = GameState.from_dict(raw)
    assert restored.mission_history == []
    assert restored.prestige_timeline == []


# ----------------------------------------------------------------------
# Phase M — Government Review
# ----------------------------------------------------------------------


def _seed_year_start_prestige(
    state: GameState, year: int, usa_prestige: int = 0, ussr_prestige: int = 0,
) -> None:
    """Helper: drop a Spring snapshot so the review knows the year-start
    prestige for the year about to be reviewed."""
    state.prestige_timeline.append(PrestigeSnapshot(
        year=year, season="Spring",
        usa_prestige=usa_prestige, ussr_prestige=ussr_prestige,
    ))


def _record_flight(
    state: GameState, year: int, side_value: str,
    success: bool = True, deaths: int = 0,
) -> None:
    state.mission_history.append(MissionHistoryEntry(
        year=year, season="Summer", side=side_value,
        mission_id="suborbital", mission_name="Test flight",
        rocket="Redstone", manned=False, success=success,
        prestige_delta=0, deaths=["X"] * deaths,
    ))


def test_review_passes_a_solid_year() -> None:
    from baris.resolver import _run_government_review
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    _seed_year_start_prestige(state, year=1957)
    p = state.players[0]
    p.prestige = 6           # +6 delta from start
    _record_flight(state, 1957, p.side.value, success=True)
    _record_flight(state, 1957, p.side.value, success=True)
    _run_government_review(state, ended_year=1957)
    assert p.warnings == 0
    assert state.phase == Phase.PLAYING


def test_review_warns_on_underperformance() -> None:
    from baris.resolver import _run_government_review
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    _seed_year_start_prestige(state, year=1957)
    p = state.players[0]
    # No flights, no prestige → score 0, below threshold of 3.
    _run_government_review(state, ended_year=1957)
    assert p.warnings == 1
    assert state.phase == Phase.PLAYING


def test_review_fires_player_after_two_warnings() -> None:
    from baris.resolver import _run_government_review
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    p = state.players[0]
    opp = state.players[1]
    _seed_year_start_prestige(state, year=1957)
    _seed_year_start_prestige(state, year=1958)
    # Year 1: bad → warning 1. Year 2: bad → warning 2 → fired.
    _run_government_review(state, ended_year=1957)
    _run_government_review(state, ended_year=1958)
    assert p.warnings >= REVIEW_FIRE_AT_WARNINGS
    assert state.phase == Phase.ENDED
    assert state.winner == opp.side


def test_review_kia_penalty_drags_score_down() -> None:
    from baris.resolver import _run_government_review
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    _seed_year_start_prestige(state, year=1957)
    p = state.players[0]
    p.prestige = 4   # would otherwise pass
    _record_flight(state, 1957, p.side.value, success=False, deaths=2)
    # score = 4 + 0 - 3*2 = -2 → below threshold.
    _run_government_review(state, ended_year=1957)
    assert p.warnings == 1


def test_review_idempotent_on_same_year() -> None:
    from baris.resolver import _run_government_review
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    _seed_year_start_prestige(state, year=1957)
    p = state.players[0]
    # Bad year: review once → 1 warning.
    _run_government_review(state, ended_year=1957)
    _run_government_review(state, ended_year=1957)
    assert p.warnings == 1     # second call short-circuits


def test_review_runs_at_year_advance() -> None:
    """Drive through four resolve_turns to roll Spring → Spring and
    confirm the year-end review fires automatically."""
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.prestige = 0  # no progress all year
    with _no_news():
        for _ in range(4):  # Spring → Summer → Fall → Winter → Spring
            for p in state.players:
                submit_turn(p, rd_rocket=None, rd_spend=0, launch=None)
            resolve_turn(state, rng=random.Random(0))
    # We should be in the new year, and at least one review entry
    # should be in the log.
    assert state.year > 1957
    assert any("REVIEW 1957" in line for line in state.log)
    # Both players had a zero-progress year → both should have a warning.
    assert me.warnings == 1
    assert state.players[1].warnings == 1


def test_review_warnings_dict_roundtrip() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    p = state.players[0]
    p.warnings = 1
    p.last_review_year = 1958
    restored = GameState.from_dict(state.to_dict())
    rp = restored.players[0]
    assert rp.warnings == 1
    assert rp.last_review_year == 1958


def test_legacy_player_dict_backfills_review_fields() -> None:
    from baris.state import _player_from_dict
    raw = {
        "player_id": "x", "username": "X",
        "side": Side.USA.value, "budget": 30, "prestige": 0,
        "ready": True, "astronauts": [],
        "mission_successes": {}, "architecture": None,
        "turn_submitted": False,
    }
    p = _player_from_dict(raw)
    assert p.warnings == 0
    assert p.last_review_year == 0


# ----------------------------------------------------------------------
# Phase N — Memorial Wall
# ----------------------------------------------------------------------


def test_memorial_roll_empty_when_no_deaths() -> None:
    from baris.resolver import memorial_roll
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    assert memorial_roll(state) == []


def test_memorial_roll_flattens_deaths_in_chronological_order() -> None:
    from baris.resolver import memorial_roll
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    state.mission_history.append(MissionHistoryEntry(
        year=1959, season="Summer", side=Side.USA.value,
        mission_id="x", mission_name="Mercury 4",
        rocket="Redstone", manned=True, success=False,
        deaths=["Glenn"],
    ))
    state.mission_history.append(MissionHistoryEntry(
        year=1962, season="Fall", side=Side.USSR.value,
        mission_id="y", mission_name="Voskhod 2",
        rocket="R-7", manned=True, success=False,
        deaths=["Komarov", "Volkov"],
    ))
    roll = memorial_roll(state)
    # Three names total, in append order (chronological).
    assert [r[0] for r in roll] == ["Glenn", "Komarov", "Volkov"]
    assert roll[0] == ("Glenn", "Mercury 4", 1959, "Summer", Side.USA.value)
    assert roll[1][1] == "Voskhod 2"
    assert roll[2][1] == "Voskhod 2"


def test_memorial_roll_handles_multiple_deaths_per_flight() -> None:
    from baris.resolver import memorial_roll
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    state.mission_history.append(MissionHistoryEntry(
        year=1967, season="Winter", side=Side.USA.value,
        mission_id="z", mission_name="Apollo 1",
        rocket="Saturn V", manned=True, success=False,
        deaths=["Grissom", "White", "Chaffee"],
    ))
    roll = memorial_roll(state)
    assert len(roll) == 3
    assert all(entry[1] == "Apollo 1" for entry in roll)


# ----------------------------------------------------------------------
# DIRTY TRICKS — sabotage MVP
# ----------------------------------------------------------------------


def _state_with_built_rockets(state: GameState, ussr_built: bool = True) -> None:
    """Helper: give USSR (or USA) a launchable Medium rocket so
    reliability-targeting cards have something to bite into."""
    target = (state.players[1] if ussr_built else state.players[0])
    target.reliability[Rocket.MEDIUM.value] = 70


def _schedule_a_pad(state: GameState, side_idx: int = 1) -> None:
    """Helper: drop a fake ScheduledLaunch onto pad A of one of the
    players so catapult / weatherman cards have a target."""
    from baris.state import ScheduledLaunch
    p = state.players[side_idx]
    p.pads[0].scheduled_launch = ScheduledLaunch(
        mission_id="suborbital", rocket_class=Rocket.LIGHT.value,
        launch_cost_total=10, assembly_cost_paid=3,
        launch_cost_remaining=7, objectives=[],
        scheduled_year=state.year, scheduled_season=state.season.value,
    )


def test_sabotage_catapult_damages_scheduled_pad() -> None:
    from baris.resolver import execute_sabotage
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.budget = 50
    _schedule_a_pad(state)
    assert execute_sabotage(me, state, "catapult", rng=random.Random(0))
    opp_pad = state.players[1].pads[0]
    assert opp_pad.damaged
    assert opp_pad.repair_turns_remaining > 0
    assert me.budget == 50 - 15           # cost paid
    assert me.sabotage_used_on            # season slot consumed


def test_sabotage_catapult_refunds_when_no_target() -> None:
    from baris.resolver import execute_sabotage
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.budget = 50
    # Opponent has no scheduled pads → catapult finds nothing.
    assert not execute_sabotage(me, state, "catapult", rng=random.Random(0))
    assert me.budget == 50                # cost refunded
    assert me.sabotage_used_on == ""      # season slot freed


def test_sabotage_weatherman_delays_scheduled_launch_one_season() -> None:
    from baris.resolver import execute_sabotage
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.budget = 50
    _schedule_a_pad(state)
    sched = state.players[1].pads[0].scheduled_launch
    assert sched is not None
    before_season, before_year = sched.scheduled_season, sched.scheduled_year
    assert execute_sabotage(me, state, "weatherman", rng=random.Random(0))
    after_season, after_year = sched.scheduled_season, sched.scheduled_year
    # Either the season changed or the year incremented (Winter→Spring).
    assert (after_season != before_season) or (after_year != before_year)


def test_sabotage_mole_drops_opponent_reliability() -> None:
    from baris.resolver import execute_sabotage
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    opp = state.players[1]
    me.budget = 50
    _state_with_built_rockets(state, ussr_built=True)
    before = opp.rocket_reliability(Rocket.MEDIUM)
    assert execute_sabotage(me, state, "mole", rng=random.Random(0))
    assert opp.rocket_reliability(Rocket.MEDIUM) == before - 5


def test_sabotage_blueprints_steals_reliability() -> None:
    from baris.resolver import execute_sabotage
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    opp = state.players[1]
    me.budget = 50
    _state_with_built_rockets(state, ussr_built=True)
    opp_before = opp.rocket_reliability(Rocket.MEDIUM)
    me_before = me.rocket_reliability(Rocket.MEDIUM)
    assert execute_sabotage(me, state, "blueprints", rng=random.Random(0))
    assert opp.rocket_reliability(Rocket.MEDIUM) == opp_before - 5
    assert me.rocket_reliability(Rocket.MEDIUM) == me_before + 5


def test_sabotage_one_per_season() -> None:
    from baris.resolver import execute_sabotage
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.budget = 100
    _state_with_built_rockets(state, ussr_built=True)
    assert execute_sabotage(me, state, "mole", rng=random.Random(0))
    # Second sabotage same season — refused.
    assert not execute_sabotage(me, state, "mole", rng=random.Random(0))


def test_sabotage_rejected_without_budget() -> None:
    from baris.resolver import execute_sabotage
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.budget = 5  # below any card cost
    _state_with_built_rockets(state, ussr_built=True)
    assert not execute_sabotage(me, state, "mole", rng=random.Random(0))


def test_legacy_player_dict_backfills_sabotage_used_on() -> None:
    from baris.state import _player_from_dict
    raw = {
        "player_id": "x", "username": "X",
        "side": Side.USA.value, "budget": 30, "prestige": 0,
        "ready": True, "astronauts": [],
        "mission_successes": {}, "architecture": None,
        "turn_submitted": False,
    }
    p = _player_from_dict(raw)
    assert p.sabotage_used_on == ""


# ----------------------------------------------------------------------
# Phase O — manual crew assignment
# ----------------------------------------------------------------------


def _setup_manned_launch(state: GameState) -> tuple:
    """Helper: bring USA to a state where it can submit a manned
    multi-crew orbital this turn. Returns (me, opp, mission)."""
    me = state.players[0]
    opp = state.players[1]
    me.reliability[Rocket.MEDIUM.value] = 70
    me.budget = 200
    # MULTI_CREW_ORBITAL is Tier 2; need a Tier-1 success on record
    # to unlock the tier.
    me.mission_successes[MissionId.SUBORBITAL.value] = 1
    return me, opp, MissionId.MULTI_CREW_ORBITAL


def test_manual_crew_chosen_pilots_actually_fly() -> None:
    """Hand-pick a crew that's NOT the top-skilled and confirm the
    resolver flies them — i.e. the chosen astronauts get the +mood
    bump on a successful launch."""
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me, _, mid = _setup_manned_launch(state)
    # Make two astronauts top-skilled in the mission's primary skill;
    # we'll pick two mid-skilled ones instead.
    from baris.state import MISSIONS_BY_ID
    skill_attr = MISSIONS_BY_ID[mid].primary_skill.value
    for a in me.astronauts:
        setattr(a, skill_attr, 30)
    setattr(me.astronauts[0], skill_attr, 95)
    setattr(me.astronauts[1], skill_attr, 95)   # auto-pick would take these
    chosen = me.astronauts[2:4]                  # pick two mid-skilled
    chosen_ids = [a.id for a in chosen]
    submit_turn(me, launch=mid, crew=chosen_ids)
    submit_turn(state.players[1], launch=None)
    with _no_news():
        resolve_turn(state, rng=_FixedRng(0.0))           # promote
        _fire_scheduled_launch(state, _FixedRng(0.0))     # fire

    # Chosen crew got the success-bump; auto-top didn't fly. Mood drift
    # nudges everyone toward 60 each season, so check the gap rather
    # than absolute values: a flier ends up clearly above a non-flier.
    auto_top = [me.astronauts[0], me.astronauts[1]]
    for chosen_astro in chosen:
        for non_flyer in auto_top:
            assert chosen_astro.mood > non_flyer.mood, (
                f"{chosen_astro.name} (mood {chosen_astro.mood}) didn't fly; "
                f"{non_flyer.name} (mood {non_flyer.mood}) did"
            )


def test_manual_crew_falls_back_to_auto_if_invalid() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me, _, mid = _setup_manned_launch(state)
    # Wrong-sized crew — MULTI_CREW_ORBITAL needs 2, we send only 1.
    # Should fall back to auto-pick rather than reject the launch.
    submit_turn(me, launch=mid, crew=[me.astronauts[0].id])
    assert me.pending_launch == mid.value      # launch still queued
    assert me.pending_crew == []                # but with no manual override


def test_manual_crew_rejected_if_member_not_flight_ready() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me, _, mid = _setup_manned_launch(state)
    me.astronauts[0].basic_training_remaining = 2  # disqualifies them
    submit_turn(
        me, launch=mid,
        crew=[me.astronauts[0].id, me.astronauts[1].id],
    )
    assert me.pending_crew == []                # full pick rejected → auto


def test_manual_crew_promoted_onto_scheduled_launch() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me, _, mid = _setup_manned_launch(state)
    crew_ids = [a.id for a in me.astronauts[3:5]]
    submit_turn(me, launch=mid, crew=crew_ids)
    submit_turn(state.players[1], launch=None)
    with _no_news():
        resolve_turn(state, rng=_FixedRng(0.99))
    sched = me.pads[0].scheduled_launch
    assert sched is not None
    assert sched.crew == crew_ids
    # And submit_turn cleared pending_crew once promoted.
    assert me.pending_crew == []


def test_resolver_falls_back_when_chosen_crew_dies_before_launch() -> None:
    """Sabotage / etc. could KIA an astronaut between schedule and
    resolve. The resolver should fall back to auto top-skilled."""
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me, _, mid = _setup_manned_launch(state)
    crew_ids = [a.id for a in me.astronauts[3:5]]
    submit_turn(me, launch=mid, crew=crew_ids)
    submit_turn(state.players[1], launch=None)
    with _no_news():
        resolve_turn(state, rng=_FixedRng(0.99))
    # Knock out the chosen crew between schedule and fire.
    me.astronauts[3].status = AstronautStatus.KIA.value
    with _no_news():
        _fire_scheduled_launch(state, _FixedRng(0.0))
    # Mission should still have flown (auto-picked replacement crew).
    assert any(
        m.year == state.year - 0
        and m.mission_id == mid.value
        for m in state.mission_history
    )


def test_scheduled_launch_dict_roundtrip_preserves_crew() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me, _, mid = _setup_manned_launch(state)
    crew_ids = [a.id for a in me.astronauts[3:5]]
    submit_turn(me, launch=mid, crew=crew_ids)
    submit_turn(state.players[1], launch=None)
    with _no_news():
        resolve_turn(state, rng=_FixedRng(0.99))
    restored = GameState.from_dict(state.to_dict())
    sched = restored.players[0].pads[0].scheduled_launch
    assert sched is not None
    assert sched.crew == crew_ids


def test_legacy_scheduled_launch_dict_backfills_crew() -> None:
    from baris.state import _scheduled_launch_from_dict
    raw = {
        "mission_id": "suborbital",
        "rocket_class": "Light",
        "launch_cost_total": 10,
        "assembly_cost_paid": 3,
        "launch_cost_remaining": 7,
        "objectives": [],
    }
    sl = _scheduled_launch_from_dict(raw)
    assert sl is not None
    assert sl.crew == []


def test_legacy_player_dict_backfills_pending_crew() -> None:
    from baris.state import _player_from_dict
    raw = {
        "player_id": "x", "username": "X",
        "side": Side.USA.value, "budget": 30, "prestige": 0,
        "ready": True, "astronauts": [],
        "mission_successes": {}, "architecture": None,
        "turn_submitted": False,
    }
    p = _player_from_dict(raw)
    assert p.pending_crew == []


# ----------------------------------------------------------------------
# Phase P — step-by-step mission resolution (named failure phases)
# ----------------------------------------------------------------------


def test_every_mission_has_phases_declared() -> None:
    """Sanity-check the catalog: every mission ships with a non-empty
    phases tuple so failure labelling is consistent."""
    for m in MISSIONS_BY_ID.values():
        assert m.phases, f"{m.id.value} missing phases"


def test_successful_launch_has_empty_failed_phase() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.reliability[Rocket.LIGHT.value] = 80
    submit_turn(me, launch=MissionId.SUBORBITAL)
    submit_turn(state.players[1], launch=None)
    with _no_news():
        resolve_turn(state, rng=_FixedRng(0.99))
        _fire_scheduled_launch(state, _FixedRng(0.0))
    report = next(
        r for r in state.last_launches
        if r.mission_id == MissionId.SUBORBITAL.value
    )
    assert report.success
    assert report.failed_phase == ""


def test_failed_launch_records_named_phase() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.reliability[Rocket.LIGHT.value] = 30
    submit_turn(me, launch=MissionId.SUBORBITAL)
    submit_turn(state.players[1], launch=None)
    with _no_news():
        resolve_turn(state, rng=_FixedRng(0.99))
        _fire_scheduled_launch(state, _FixedRng(0.99))
    report = next(
        r for r in state.last_launches
        if r.mission_id == MissionId.SUBORBITAL.value
    )
    assert not report.success
    assert report.failed_phase
    expected_values = {p.value for p in MISSIONS_BY_ID[MissionId.SUBORBITAL].phases}
    assert report.failed_phase in expected_values


def test_lunar_landing_failed_phase_drawn_from_full_timeline() -> None:
    """Manned lunar landing has 9 phases. With real Phase P each phase
    rolls separately and the FIRST failure short-circuits, so failures
    cluster on earlier phases — but with varied per-call RNGs we
    should still hit several distinct phases across many seeds."""
    seen: set[str] = set()
    expected_pool = {
        p.value for p in MISSIONS_BY_ID[MissionId.MANNED_LUNAR_LANDING].phases
    }
    for seed in range(1, 200):
        state = _two_player_state()
        start_game(state, rng=random.Random(seed))
        me = state.players[0]
        me.reliability[Rocket.HEAVY.value] = 40
        me.reliability[Module.LUNAR_KICKER.value] = 60
        me.reliability[Module.EVA_SUIT.value] = 60
        me.budget = 500
        me.architecture = Architecture.DA.value
        me.mission_successes[MissionId.SUBORBITAL.value] = 1
        me.mission_successes[MissionId.MULTI_CREW_ORBITAL.value] = 1
        submit_turn(me, launch=MissionId.MANNED_LUNAR_LANDING)
        submit_turn(state.players[1], launch=None)
        # Use a real Random per seed so each phase roll gets a fresh
        # value (rather than _FixedRng which returns the same number
        # every call and would always fail at the first phase).
        with _no_news():
            resolve_turn(state, rng=random.Random(seed))
            _fire_scheduled_launch(state, random.Random(seed * 7 + 11))
        report = next(
            (r for r in state.last_launches
             if r.mission_id == MissionId.MANNED_LUNAR_LANDING.value),
            None,
        )
        if report is not None and report.failed_phase:
            seen.add(report.failed_phase)
        if len(seen) >= 4:
            break
    assert len(seen) >= 4, f"only saw {seen}"


def test_launch_report_dict_roundtrip_preserves_failed_phase() -> None:
    from baris.state import LaunchReport, _launch_report_from_dict, MissionPhase
    r = LaunchReport(
        side=Side.USA.value, username="X",
        mission_id=MissionId.SUBORBITAL.value,
        mission_name="Sub-orbital flight",
        rocket="Redstone", rocket_class=Rocket.LIGHT.value,
        success=False, failed_phase=MissionPhase.REENTRY.value,
    )
    raw = {**r.__dict__}
    raw["objectives"] = [o.__dict__ for o in r.objectives]
    restored = _launch_report_from_dict(raw)
    assert restored.failed_phase == MissionPhase.REENTRY.value


def test_legacy_launch_report_dict_backfills_failed_phase() -> None:
    from baris.state import _launch_report_from_dict
    raw = {
        "side": "USA", "username": "X",
        "mission_id": "suborbital", "mission_name": "Sub-orbital",
        "rocket": "Redstone", "rocket_class": "Light",
        "success": False,
    }
    r = _launch_report_from_dict(raw)
    assert r.failed_phase == ""


# ----------------------------------------------------------------------
# Phase Q — per-component R&D
# ----------------------------------------------------------------------


def test_player_default_reliability_seeds_phase_q_components() -> None:
    """A fresh Player has CAPSULE / PROBE / LM at the seeded baseline."""
    from baris.state import COMPONENT_STARTING_RELIABILITY
    p = Player(player_id="x", username="X", side=Side.USA)
    assert p.module_reliability(Module.CAPSULE) == COMPONENT_STARTING_RELIABILITY[
        Module.CAPSULE.value]
    assert p.module_reliability(Module.PROBE) == COMPONENT_STARTING_RELIABILITY[
        Module.PROBE.value]
    assert p.module_reliability(Module.LM) == COMPONENT_STARTING_RELIABILITY[
        Module.LM.value]


def test_applicable_components_per_mission_class() -> None:
    from baris.resolver import applicable_components
    sub = MISSIONS_BY_ID[MissionId.SUBORBITAL]
    sat = MISSIONS_BY_ID[MissionId.SATELLITE]
    manned_orbital = MISSIONS_BY_ID[MissionId.MANNED_ORBITAL]
    landing = MISSIONS_BY_ID[MissionId.MANNED_LUNAR_LANDING]
    assert applicable_components(sub) == ()
    assert applicable_components(sat) == (Module.PROBE,)
    assert applicable_components(manned_orbital) == (Module.CAPSULE,)
    assert set(applicable_components(landing)) == {Module.CAPSULE, Module.LM}


def test_component_bonus_zero_when_at_neutral_50() -> None:
    from baris.resolver import component_reliability_bonus
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.reliability[Module.CAPSULE.value] = 50
    me.reliability[Module.PROBE.value] = 50
    me.reliability[Module.LM.value] = 50
    for m in MISSIONS_BY_ID.values():
        assert component_reliability_bonus(me, m) == 0.0


def test_component_bonus_positive_when_above_neutral() -> None:
    from baris.resolver import component_reliability_bonus
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.reliability[Module.CAPSULE.value] = 80
    bonus = component_reliability_bonus(me, MISSIONS_BY_ID[MissionId.MANNED_ORBITAL])
    assert bonus > 0


def test_component_bonus_penalises_unresearched_lm() -> None:
    """A landing mission with unresearched LM (=10) takes a real hit."""
    from baris.resolver import component_reliability_bonus
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    bonus = component_reliability_bonus(
        me, MISSIONS_BY_ID[MissionId.MANNED_LUNAR_LANDING],
    )
    assert bonus < 0


def test_legacy_player_dict_backfills_phase_q_components() -> None:
    """Pre-Phase-Q saves' reliability dict has no CAPSULE/PROBE/LM
    entries; loader fills them in at the COMPONENT_STARTING_RELIABILITY
    baseline rather than crashing later when a launch reads them."""
    from baris.state import COMPONENT_STARTING_RELIABILITY, _player_from_dict
    raw = {
        "player_id": "x", "username": "X",
        "side": Side.USA.value, "budget": 30, "prestige": 0,
        "ready": True, "astronauts": [],
        "reliability": {  # only the legacy three modules
            Rocket.LIGHT.value: 0,
            Rocket.MEDIUM.value: 0,
            Rocket.HEAVY.value: 0,
            Module.DOCKING.value: 0,
            Module.LUNAR_KICKER.value: 0,
            Module.EVA_SUIT.value: 0,
        },
        "mission_successes": {}, "architecture": None,
        "turn_submitted": False,
    }
    p = _player_from_dict(raw)
    assert p.module_reliability(Module.CAPSULE) == \
        COMPONENT_STARTING_RELIABILITY[Module.CAPSULE.value]
    assert p.module_reliability(Module.PROBE) == \
        COMPONENT_STARTING_RELIABILITY[Module.PROBE.value]
    assert p.module_reliability(Module.LM) == \
        COMPONENT_STARTING_RELIABILITY[Module.LM.value]


def test_legacy_launch_report_dict_backfills_component_bonus() -> None:
    from baris.state import _launch_report_from_dict
    raw = {
        "side": "USA", "username": "X",
        "mission_id": "suborbital", "mission_name": "Sub-orbital",
        "rocket": "Redstone", "rocket_class": "Light",
    }
    r = _launch_report_from_dict(raw)
    assert r.component_bonus == 0.0


# ----------------------------------------------------------------------
# Phase R — stand tests
# ----------------------------------------------------------------------


def test_stand_test_bumps_reliability_and_charges_cost() -> None:
    from baris.resolver import request_stand_test
    from baris.state import STAND_TEST_COST, STAND_TEST_GAIN
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.budget = 50
    me.reliability[Rocket.LIGHT.value] = 40
    assert request_stand_test(me, state, Rocket.LIGHT.value)
    assert me.reliability[Rocket.LIGHT.value] == 40 + STAND_TEST_GAIN
    assert me.budget == 50 - STAND_TEST_COST


def test_stand_test_rejected_without_budget() -> None:
    from baris.resolver import request_stand_test
    from baris.state import STAND_TEST_COST
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.budget = STAND_TEST_COST - 1
    me.reliability[Rocket.LIGHT.value] = 30
    assert not request_stand_test(me, state, Rocket.LIGHT.value)
    assert me.reliability[Rocket.LIGHT.value] == 30


def test_stand_test_throttled_to_one_per_target_per_season() -> None:
    from baris.resolver import request_stand_test
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.budget = 100
    assert request_stand_test(me, state, Rocket.LIGHT.value)
    # Same target, same season — refused.
    assert not request_stand_test(me, state, Rocket.LIGHT.value)
    # Different target, same season — allowed.
    assert request_stand_test(me, state, Module.DOCKING.value)


def test_stand_test_clamped_at_reliability_cap() -> None:
    from baris.resolver import request_stand_test
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.budget = 100
    me.reliability[Rocket.HEAVY.value] = RELIABILITY_FLOOR  # use a constant
    me.reliability[Rocket.HEAVY.value] = 95  # close to the cap (99)
    assert request_stand_test(me, state, Rocket.HEAVY.value)
    from baris.state import RELIABILITY_CAP
    assert me.reliability[Rocket.HEAVY.value] == RELIABILITY_CAP


def test_stand_test_rejected_for_unknown_target() -> None:
    from baris.resolver import request_stand_test
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.budget = 100
    assert not request_stand_test(me, state, "Nonsense Component")


def test_legacy_player_dict_backfills_stand_tests_used() -> None:
    from baris.state import _player_from_dict
    raw = {
        "player_id": "x", "username": "X",
        "side": Side.USA.value, "budget": 30, "prestige": 0,
        "ready": True, "astronauts": [],
        "mission_successes": {}, "architecture": None,
        "turn_submitted": False,
    }
    p = _player_from_dict(raw)
    assert p.stand_tests_used == {}


# ----------------------------------------------------------------------
# Radio chatter — divergence flavour
# ----------------------------------------------------------------------


@contextmanager
def _enable_chatter():
    from baris import chatter
    prev = chatter._chatter_enabled
    chatter._chatter_enabled = True
    try:
        yield
    finally:
        chatter._chatter_enabled = prev


def test_chatter_react_appends_radio_line_to_log() -> None:
    from baris.chatter import chatter_react
    with _enable_chatter():
        log: list[str] = []
        chatter_react(
            log, "launch_success", random.Random(0),
            chance=1.0,  # force the line
            character="Bombardiro Crocodilo", rocket="Saturn V",
        )
    assert log and log[0].startswith("📻 ")


def test_chatter_react_silent_on_unknown_event() -> None:
    from baris.chatter import chatter_react
    with _enable_chatter():
        log: list[str] = []
        chatter_react(log, "no_such_event", random.Random(0), chance=1.0)
    assert log == []


def test_chatter_react_falls_back_when_format_kwargs_missing() -> None:
    """If a template references {character} but the caller didn't pass
    one, we should NOT leak the raw '{character}' string into the log."""
    from baris import chatter
    from baris.chatter import chatter_react
    with _enable_chatter():
        # Replace the launch_success pool with a single placeholder-only
        # template + a no-placeholder fallback.
        prev_pool = chatter.CHATTER_BANK.get("launch_success", ())
        chatter.CHATTER_BANK["launch_success"] = (
            "{character} radios in.",
            "Mission complete.",
        )
        try:
            log: list[str] = []
            # No `character=` kwarg → first template would KeyError;
            # we expect the fallback line to fire instead.
            for _ in range(20):
                chatter_react(log, "launch_success", random.Random(0), chance=1.0)
        finally:
            chatter.CHATTER_BANK["launch_success"] = prev_pool
    for line in log:
        assert "{character}" not in line


def test_chatter_react_respects_global_disable() -> None:
    from baris import chatter
    from baris.chatter import chatter_react
    # Default state in tests is disabled (via conftest fixture).
    log: list[str] = []
    chatter_react(
        log, "launch_success", random.Random(0),
        chance=1.0, character="X", rocket="Y",
    )
    assert log == []
    # Re-enabling fires the line.
    with _enable_chatter():
        chatter_react(
            log, "launch_success", random.Random(0),
            chance=1.0, character="X", rocket="Y",
        )
    assert log and log[0].startswith("📻 ")


# ----------------------------------------------------------------------
# Phase S — calendar deadline + historical milestones
# ----------------------------------------------------------------------


def _advance_one_season(state: GameState) -> None:
    for p in state.players:
        submit_turn(p, rd_rocket=None, rd_spend=0, launch=None)
    with _no_news():
        resolve_turn(state, rng=random.Random(1))


def test_calendar_deadline_ends_game_after_end_year() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    opp = state.players[1]
    me.prestige = 25
    opp.prestige = 12
    state.end_year = state.year     # immediate next-year rollover ends it
    # Roll Spring → Summer → Fall → Winter → Spring (next year).
    for _ in range(4):
        if state.phase != Phase.PLAYING:
            break
        _advance_one_season(state)
    assert state.phase == Phase.ENDED
    assert state.winner == me.side


def test_calendar_deadline_tiebreaks_on_total_successes() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    opp = state.players[1]
    me.prestige = 10
    opp.prestige = 10
    me.mission_successes[MissionId.SUBORBITAL.value] = 1   # me has more
    state.end_year = state.year
    for _ in range(4):
        if state.phase != Phase.PLAYING:
            break
        _advance_one_season(state)
    assert state.winner == me.side


def test_historical_milestone_fires_once_per_game() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    # Sputnik is keyed to (1957, "Fall"). The game starts at Spring
    # 1957 — advance two seasons to land on Fall.
    _advance_one_season(state)   # Spring → Summer
    _advance_one_season(state)   # Summer → Fall
    sputnik_lines = [l for l in state.log if "1957" in l and "satellite" in l.lower()]
    assert sputnik_lines, "expected Sputnik milestone after Spring → Summer → Fall"
    assert "sputnik_1957" in state.milestones_fired


def test_legacy_state_dict_backfills_phase_s_fields() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    raw = state.to_dict()
    raw.pop("end_year", None)
    raw.pop("milestones_fired", None)
    restored = GameState.from_dict(raw)
    from baris.state import DEFAULT_END_YEAR
    assert restored.end_year == DEFAULT_END_YEAR
    assert restored.milestones_fired == []


# ----------------------------------------------------------------------
# Phase T — astronaut rest after a flight
# ----------------------------------------------------------------------


def test_successful_manned_launch_marks_crew_for_rest() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.reliability[Rocket.MEDIUM.value] = 80
    me.budget = 200
    submit_turn(me, launch=MissionId.MANNED_ORBITAL)
    submit_turn(state.players[1], launch=None)
    with _no_news():
        resolve_turn(state, rng=_FixedRng(0.0))
        _fire_scheduled_launch(state, _FixedRng(0.0))
    flown = [a for a in me.astronauts if a.rest_remaining > 0]
    assert flown, "expected at least one crew member to be marked for rest"
    from baris.state import REST_AFTER_FLIGHT
    # Counter ticks down once per resolve, so the survivor has
    # REST_AFTER_FLIGHT - 1 left after the resolve that set it.
    for a in flown:
        assert a.rest_remaining <= REST_AFTER_FLIGHT


def test_resting_astronaut_is_not_flight_ready() -> None:
    a = Astronaut(id="x", name="X")
    a.rest_remaining = 1
    assert not a.flight_ready
    assert "resting" in a.busy_reason


def test_failed_manned_launch_rests_survivors_longer() -> None:
    """Failure path: surviving crew get REST_AFTER_FAILURE >
    REST_AFTER_FLIGHT, so they're sidelined longer than after a clean
    mission."""
    from baris.state import REST_AFTER_FAILURE, REST_AFTER_FLIGHT
    assert REST_AFTER_FAILURE > REST_AFTER_FLIGHT
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.reliability[Rocket.MEDIUM.value] = 70
    me.budget = 200
    for a in me.astronauts:
        a.capsule = 50
    submit_turn(me, launch=MissionId.MANNED_ORBITAL)
    submit_turn(state.players[1], launch=None)
    with _no_news():
        resolve_turn(state, rng=_FixedRng(0.99))    # forced failure
        _fire_scheduled_launch(state, _FixedRng(0.99))
    survivors = [a for a in me.astronauts if a.active]
    rested = [a for a in survivors if a.rest_remaining > 0]
    assert rested, "failed-mission survivors should still be marked for rest"


def test_rest_counter_ticks_down_each_turn() -> None:
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.astronauts[0].rest_remaining = 2
    _advance_one_season(state)
    assert me.astronauts[0].rest_remaining == 1
    _advance_one_season(state)
    assert me.astronauts[0].rest_remaining == 0


def test_legacy_astronaut_dict_backfills_rest_remaining() -> None:
    from baris.state import _astronaut_from_dict
    raw = {
        "id": "x", "name": "X",
        "capsule": 0, "lm_pilot": 0, "eva": 0, "docking": 0, "endurance": 0,
        "status": "active",
    }
    a = _astronaut_from_dict(raw)
    assert a.rest_remaining == 0


# ----------------------------------------------------------------------
# Phase U — server save / load
# ----------------------------------------------------------------------


def test_server_room_round_trips_state_through_disk(tmp_path) -> None:
    """Mutate state on a Room, save to disk, hydrate a fresh Room from
    the same path, and confirm key fields survive the round-trip."""
    from baris.server.main import Room
    save_path = tmp_path / "autosave.json"
    src = Room(save_path=save_path)
    src.state = _two_player_state()
    start_game(src.state, rng=random.Random(1))
    me = src.state.players[0]
    me.budget = 999
    me.prestige = 17
    src.state.year = 1962
    src.save_to_disk()
    assert save_path.exists()
    dst = Room(save_path=save_path)
    assert dst.load_from_disk()
    assert dst.state.year == 1962
    rp = dst.state.players[0]
    assert rp.budget == 999
    assert rp.prestige == 17
    assert len(rp.astronauts) == len(me.astronauts)


def test_server_room_load_returns_false_when_save_missing(tmp_path) -> None:
    from baris.server.main import Room
    save_path = tmp_path / "missing.json"
    room = Room(save_path=save_path)
    assert not room.load_from_disk()
    # State is the default empty GameState, not a partial garbage hydrate.
    assert room.state.players == []


def test_server_room_load_returns_false_on_corrupt_save(tmp_path) -> None:
    from baris.server.main import Room
    save_path = tmp_path / "corrupt.json"
    save_path.write_text("not even close to JSON")
    room = Room(save_path=save_path)
    assert not room.load_from_disk()
    assert room.state.players == []


def test_server_room_save_creates_parent_dir(tmp_path) -> None:
    from baris.server.main import Room
    save_path = tmp_path / "nested" / "subdir" / "autosave.json"
    room = Room(save_path=save_path)
    room.state = _two_player_state()
    room.save_to_disk()
    assert save_path.exists()


def test_server_room_save_disabled_when_path_is_none() -> None:
    from baris.server.main import Room
    room = Room(save_path=None)
    # Should be a quiet no-op rather than a crash.
    room.save_to_disk()
    assert not room.load_from_disk()


# ----------------------------------------------------------------------
# Crew roles within missions
# ----------------------------------------------------------------------


def test_manned_landing_declares_three_roles_in_pilot_skill_order() -> None:
    """Sanity check: our flagship Apollo-style mission should ask for
    CAPSULE, LM_PILOT, EVA in that order."""
    mission = MISSIONS_BY_ID[MissionId.MANNED_LUNAR_LANDING]
    assert mission.crew_roles == (Skill.CAPSULE, Skill.LM_PILOT, Skill.EVA)


def test_role_based_pick_assigns_specialists_to_their_seats() -> None:
    """Player has three pilots, each maxed in a different skill. The
    selector should put each in their right seat."""
    me = Player(player_id="a", username="Alice", side=Side.USA)
    me.astronauts = [
        _make_astronaut("CMP",  capsule=100, lm_pilot=10,  eva=10),
        _make_astronaut("LMP",  capsule=10,  lm_pilot=100, eva=10),
        _make_astronaut("EVA",  capsule=10,  lm_pilot=10,  eva=100),
    ]
    mission = MISSIONS_BY_ID[MissionId.MANNED_LUNAR_LANDING]
    crew = _select_crew(me, mission)
    assert crew is not None
    assert [a.name for a in crew] == ["CMP", "LMP", "EVA"]


def test_real_phase_p_pinpoints_the_first_failed_phase() -> None:
    """Sequenced RNG: pass phases 1+2, fail phase 3. The report should
    name the third phase (TLI for unmanned lunar orbit) as the failure
    point — proves the per-phase loop short-circuits at the right step
    rather than picking a random phase to label."""
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
    me.reliability[Rocket.HEAVY.value] = 80
    me.reliability[Module.LUNAR_KICKER.value] = 80
    me.budget = 200
    me.mission_successes[MissionId.SUBORBITAL.value] = 1
    submit_turn(me, launch=MissionId.LUNAR_ORBIT)   # phases: LAUNCH, TLI, LOI
    submit_turn(state.players[1], launch=None)
    with _no_news():
        resolve_turn(state, rng=_SeqRng([0.99]))    # promote, no rolls used
        # Pass LAUNCH, pass TLI, fail LOI. Tail padding handles any
        # downstream consequence rolls.
        _fire_scheduled_launch(
            state, _SeqRng([0.0, 0.0, 0.99, 0.99, 0.99, 0.99]),
        )
    report = next(
        r for r in state.last_launches
        if r.mission_id == MissionId.LUNAR_ORBIT.value
    )
    assert not report.success
    from baris.state import MissionPhase
    assert report.failed_phase == MissionPhase.LOI.value


def test_real_phase_p_all_phases_pass_means_success() -> None:
    """Feed a stream of zeros so every phase roll trivially passes;
    the mission should succeed regardless of how many phases it has."""
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.reliability[Rocket.LIGHT.value] = 80
    submit_turn(me, launch=MissionId.SUBORBITAL)
    submit_turn(state.players[1], launch=None)
    with _no_news():
        resolve_turn(state, rng=_FixedRng(0.0))
        _fire_scheduled_launch(state, _FixedRng(0.0))
    report = next(
        r for r in state.last_launches
        if r.mission_id == MissionId.SUBORBITAL.value
    )
    assert report.success
    assert report.failed_phase == ""


def test_post_mission_skill_bump_uses_each_seats_role() -> None:
    """A successful manned-lunar-landing should bump CMP's capsule,
    LMP's lm_pilot, and EVA's eva — not all three in a single skill."""
    state = _two_player_state()
    start_game(state, rng=random.Random(1))
    me = state.players[0]
    me.reliability[Rocket.HEAVY.value] = 90
    me.reliability[Module.LUNAR_KICKER.value] = 80
    me.reliability[Module.EVA_SUIT.value] = 80
    me.reliability[Module.LM.value] = 80
    me.budget = 500
    me.architecture = Architecture.DA.value
    me.mission_successes[MissionId.SUBORBITAL.value] = 1
    me.mission_successes[MissionId.MULTI_CREW_ORBITAL.value] = 1
    # Reset roster to three known pilots so role-pick is deterministic.
    me.astronauts = [
        _make_astronaut("CMP", capsule=80, lm_pilot=10, eva=10, endurance=50),
        _make_astronaut("LMP", capsule=10, lm_pilot=80, eva=10, endurance=50),
        _make_astronaut("EVA", capsule=10, lm_pilot=10, eva=80, endurance=50),
    ]
    pre = {a.name: (a.capsule, a.lm_pilot, a.eva) for a in me.astronauts}
    submit_turn(me, launch=MissionId.MANNED_LUNAR_LANDING)
    submit_turn(state.players[1], launch=None)
    with _no_news():
        resolve_turn(state, rng=_FixedRng(0.0))
        _fire_scheduled_launch(state, _FixedRng(0.0))
    by_name = {a.name: a for a in me.astronauts}
    # Passive seasonal training (+1/skill, +3 random) muddies absolute
    # deltas, so compare each pilot's role-skill growth to their
    # non-role-skill growth: the role seat should grow strictly more.
    def deltas(name):
        a = by_name[name]
        c, l, e = pre[name]
        return (a.capsule - c, a.lm_pilot - l, a.eva - e)
    cmp_dc, cmp_dl, cmp_de = deltas("CMP")
    lmp_dc, lmp_dl, lmp_de = deltas("LMP")
    eva_dc, eva_dl, eva_de = deltas("EVA")
    assert cmp_dc > cmp_dl and cmp_dc > cmp_de, "CMP capsule didn't outgrow its other skills"
    assert lmp_dl > lmp_dc and lmp_dl > lmp_de, "LMP lm_pilot didn't outgrow its other skills"
    assert eva_de > eva_dc and eva_de > eva_dl, "EVA eva didn't outgrow its other skills"
