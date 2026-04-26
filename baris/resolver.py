from __future__ import annotations

import random
import uuid
from typing import Any

from baris.chatter import chatter_react
from baris.state import (
    ADVANCED_TRAINING_COST,
    ADVANCED_TRAINING_SKILL_GAIN,
    ADVANCED_TRAINING_TURNS,
    ARCHITECTURE_COST_DELTA,
    ARCHITECTURE_SUCCESS_DELTA,
    ASSEMBLY_COST_FRACTION,
    LM_POINTS_FROM_LM_EARTH_TEST,
    LM_POINTS_FROM_LM_LUNAR_TEST,
    LM_POINTS_FROM_MANNED_LUNAR_ORBIT,
    LM_POINTS_FROM_MANNED_ORBITAL,
    LM_POINTS_FROM_MULTI_CREW,
    LM_POINTS_FROM_ORBITAL_DOCKING,
    LM_POINTS_FROM_ORBITAL_EVA,
    LM_POINTS_FROM_UNMANNED_LANDING,
    LM_POINTS_PENALTY_PER_MISSING,
    LM_POINTS_REQUIRED,
    LUNAR_RECON_BASE,
    LUNAR_RECON_CAP,
    LUNAR_RECON_PER_POINT,
    RECON_FROM_LUNAR_ORBIT,
    RECON_FROM_LUNAR_PASS,
    RECON_FROM_MANNED_LUNAR_ORBIT,
    RECON_FROM_UNMANNED_LANDING_FAIL,
    RECON_FROM_UNMANNED_LANDING_OK,
    Architecture,
    Astronaut,
    AstronautStatus,
    BASIC_TRAINING_TURNS,
    CREW_COMPAT_MAX_BONUS,
    CREW_MAX_BONUS,
    Compatibility,
    MOOD_DEFAULT,
    MOOD_DRIFT_PER_TURN,
    MOOD_DRIFT_TARGET,
    MOOD_FAILURE_DROP,
    MOOD_KIA_CREW_DROP,
    MOOD_MAX,
    MOOD_RETIREMENT_THRESHOLD,
    MOOD_SUCCESS_BUMP,
    DEATH_CHANCE_ON_FAIL,
    DEATH_PRESTIGE_PENALTY,
    GameState,
    HOSPITAL_CHANCE_ON_FAIL,
    HOSPITAL_STAY_TURNS,
    INTEL_COST,
    INTEL_RELIABILITY_NOISE,
    INTEL_RUMOR_ACCURATE,
    IntelReport,
    LaunchReport,
    MissionHistoryEntry,
    PrestigeSnapshot,
    REST_AFTER_FAILURE,
    REST_AFTER_FLIGHT,
    REVIEW_FIRE_AT_WARNINGS,
    REVIEW_KIA_PENALTY,
    REVIEW_PASS_THRESHOLD,
    REVIEW_SUCCESS_BONUS,
    SABOTAGE_CARDS,
    SABOTAGE_RELIABILITY_HIT,
    SABOTAGE_RELIABILITY_STEAL_GAIN,
    SabotageCard,
    STAND_TEST_COST,
    STAND_TEST_GAIN,
    get_sabotage_card,
    MIN_RELIABILITY_TO_LAUNCH,
    MISSION_OBJECTIVES,
    MISSIONS_BY_ID,
    Mission,
    MissionId,
    MissionObjective,
    Module,
    ObjectiveId,
    ObjectiveReport,
    Phase,
    PRESTIGE_TO_WIN,
    Player,
    ProgramTier,
    RD_BATCH_COST,
    RD_SPEED,
    LaunchPad,
    PAD_REPAIR_TURNS,
    SCRUB_REFUND_FRACTION,
    ScheduledLaunch,
    TRAINING_CANCEL_REFUND_FRACTION,
    objectives_for,
    RELIABILITY_CAP,
    RELIABILITY_FLOOR,
    RELIABILITY_GAIN_ON_SUCCESS,
    RELIABILITY_LOSS_ON_FAIL,
    RELIABILITY_SWING_PER_POINT,
    UNMANNED_FAILURE_RD_GAIN,
    MANNED_FAILURE_BUDGET_CUT,
    RECRUIT_SKILL_MAX,
    RECRUIT_SKILL_MIN,
    RECRUITMENT_GROUPS,
    RecruitmentGroup,
    Rocket,
    SEASON_REFILL,
    STARTING_ASTRONAUTS,
    Season,
    Side,
    Skill,
    next_season,
    rocket_display_name,
)


def _player_architecture(player: Player) -> Architecture | None:
    if player.architecture is None:
        return None
    try:
        return Architecture(player.architecture)
    except ValueError:
        return None


def effective_rocket(player: Player, mission: Mission) -> Rocket:
    """Some architectures override the rocket requirement for the manned lunar landing."""
    if mission.id == MissionId.MANNED_LUNAR_LANDING:
        if _player_architecture(player) == Architecture.EOR:
            return Rocket.MEDIUM
    return mission.rocket


def effective_launch_cost(player: Player, mission: Mission) -> int:
    if mission.id == MissionId.MANNED_LUNAR_LANDING:
        arch = _player_architecture(player)
        if arch is not None:
            return mission.launch_cost + ARCHITECTURE_COST_DELTA[arch]
    return mission.launch_cost


def effective_base_success(player: Player, mission: Mission) -> float:
    if mission.id == MissionId.MANNED_LUNAR_LANDING:
        arch = _player_architecture(player)
        if arch is not None:
            return mission.base_success + ARCHITECTURE_SUCCESS_DELTA[arch]
    return mission.base_success


def applicable_components(mission: Mission) -> tuple[Module, ...]:
    """Phase Q — non-rocket components that contribute reliability
    bonuses to this mission. Manned flights pull in CAPSULE; unmanned
    flights pull in PROBE (sub-orbital is a ballistic test and skips
    the probe track). Any lunar-landing variant additionally pulls in
    LM. Mission-declared `requires_modules` are NOT pulled in here
    because their reliability is already a hard gate at submit time."""
    components: list[Module] = []
    if mission.manned:
        components.append(Module.CAPSULE)
    elif mission.id != MissionId.SUBORBITAL:
        components.append(Module.PROBE)
    if mission.id in (
        MissionId.LUNAR_LANDING,
        MissionId.MANNED_LUNAR_LANDING,
        MissionId.LM_EARTH_TEST,
        MissionId.LM_LUNAR_TEST,
    ):
        components.append(Module.LM)
    return tuple(components)


def component_reliability_bonus(player: Player, mission: Mission) -> float:
    """Average per-component reliability swing for this mission's
    applicable components. Centred on 50 (neutral) so unresearched
    components drag effective success down and well-tested ones lift
    it up. Returns 0.0 if nothing applies (e.g. a sub-orbital test)."""
    components = applicable_components(mission)
    if not components:
        return 0.0
    deltas = [
        (player.module_reliability(m) - 50) * RELIABILITY_SWING_PER_POINT
        for m in components
    ]
    return sum(deltas) / len(deltas)


def effective_lunar_modifier(player: Player, mission: Mission) -> tuple[float, float]:
    """Returns (recon_bonus, lm_penalty) for the manned lunar landing.
    Both are 0.0 for any other mission. Used by the resolver when rolling
    the mission and by the UI for pre-flight briefings so the numbers
    the player sees match what actually gets rolled."""
    if mission.id != MissionId.MANNED_LUNAR_LANDING:
        return (0.0, 0.0)
    recon_bonus = max(0, player.lunar_recon - LUNAR_RECON_BASE) * LUNAR_RECON_PER_POINT
    missing = max(0, LM_POINTS_REQUIRED - player.lm_points)
    lm_penalty = missing * LM_POINTS_PENALTY_PER_MISSING
    return (recon_bonus, lm_penalty)


def missing_modules(player: Player, mission: Mission) -> list[Module]:
    """Hardware modules the mission lists in `requires_modules` that the
    player hasn't built yet. Empty list means every prereq module is
    launch-ready. Used by the server to reject queueing and by UIs to
    surface a 'need: X' status on each mission row."""
    return [m for m in mission.requires_modules if not player.module_built(m)]


def meets_architecture_prereqs(player: Player, mission: Mission) -> bool:
    """Architecture-specific extra prereqs."""
    if mission.id != MissionId.MANNED_LUNAR_LANDING:
        return True
    arch = _player_architecture(player)
    if arch is None:
        return False  # must pick an architecture first
    if arch == Architecture.LSR:
        return player.mission_successes.get(MissionId.LUNAR_LANDING.value, 0) > 0
    return True


def choose_architecture(player: Player, choice: Architecture) -> bool:
    """One-way architecture commitment. Returns True if applied."""
    if not player.is_tier_unlocked(ProgramTier.THREE):
        return False
    if player.architecture is not None:
        return False
    player.architecture = choice.value
    return True


def can_start(state: GameState) -> bool:
    if state.phase != Phase.LOBBY:
        return False
    if len(state.players) != 2:
        return False
    sides = {p.side for p in state.players}
    if None in sides or sides != {Side.USA, Side.USSR}:
        return False
    return all(p.ready for p in state.players)


def start_game(
    state: GameState,
    rng: random.Random | None = None,
    debug: bool = False,
) -> None:
    rng = rng or random.Random()
    state.phase = Phase.PLAYING
    for player in state.players:
        if not player.astronauts:
            player.astronauts = _generate_starting_roster(player, rng)
        if debug:
            _apply_debug_preseed(player)
    state.log.append(
        f"Game started — {state.season.value} {state.year}"
        + (" [DEBUG MODE]" if debug else "")
        + "."
    )
    # Phase L — seed the timeline at turn 0 with the starting prestige
    # (zero for both sides) so the museum line chart has its first point.
    _snapshot_prestige(state)


def _apply_debug_preseed(player: Player) -> None:
    """Give the player a fat starting kit so testing skips the grind: big
    budget, all rockets launch-ready at 70% reliability, Apollo/Soyuz
    unlocked, and the roster's skills floored at 70."""
    player.budget = 500
    for r in Rocket:
        player.reliability[r.value] = 70
    for m in Module:
        player.reliability[m.value] = 70
    player.mission_successes[MissionId.SUBORBITAL.value] = 1
    player.mission_successes[MissionId.MULTI_CREW_ORBITAL.value] = 1
    for a in player.astronauts:
        a.capsule = max(a.capsule, 70)
        a.lm_pilot = max(a.lm_pilot, 70)
        a.eva = max(a.eva, 70)
        a.docking = max(a.docking, 70)
        a.endurance = max(a.endurance, 70)


def _generate_starting_roster(player: Player, rng: random.Random) -> list[Astronaut]:
    """Build Group 1 — the starting roster — at game start. Uses the
    group-1 name pool and slightly higher skill ranges than later
    recruits (20-50 vs 15-40) to reflect that the first intake is
    drawn from elite test-pilot candidates."""
    group = RECRUITMENT_GROUPS[0]
    side_code = player.side.value if player.side else "ROS"
    names = _group_names_for(group, side_code)
    roster: list[Astronaut] = []
    for i in range(group.size):
        default = f"{side_code}-{i + 1:02d}"
        name = names[i] if i < len(names) else default
        roster.append(Astronaut(
            id=uuid.uuid4().hex[:6],
            name=name,
            capsule=rng.randint(20, 50),
            lm_pilot=rng.randint(20, 50),
            eva=rng.randint(20, 50),
            docking=rng.randint(20, 50),
            endurance=rng.randint(20, 50),
            compatibility=rng.choice([c.value for c in Compatibility]),
        ))
    return roster


def _group_names_for(group: RecruitmentGroup, side_code: str) -> tuple[str, ...]:
    if side_code == Side.USA.value:
        return group.us_names
    if side_code == Side.USSR.value:
        return group.ussr_names
    return ()


def next_recruitment_preview(
    player: Player, state: GameState,
) -> tuple[RecruitmentGroup | None, bool, str]:
    """Describe the next recruitable group: (group, can_hire_now, reason).
    group is None when all groups have been exhausted."""
    idx = player.next_recruitment_group
    if idx < 1 or idx > len(RECRUITMENT_GROUPS):
        return None, False, "all groups hired"
    group = RECRUITMENT_GROUPS[idx - 1]
    if state.year < group.earliest_year:
        return group, False, f"available in {group.earliest_year}"
    if player.budget < group.cost:
        return group, False, f"need {group.cost} MB"
    return group, True, ""


def recruit_next_group(
    player: Player, state: GameState, rng: random.Random | None = None,
) -> bool:
    """Hire the next recruitment group if conditions are met. Deducts
    budget, adds astronauts (each entering basic training), and advances
    the player's group pointer. Returns True on success, False if the
    hire was rejected (unavailable year, insufficient budget, all groups
    already hired)."""
    group, can_hire, _reason = next_recruitment_preview(player, state)
    if group is None or not can_hire:
        return False
    rng = rng or random.Random()
    side_code = player.side.value if player.side else ""
    names = _group_names_for(group, side_code)
    existing = {a.name for a in player.astronauts}
    added = 0
    for i in range(group.size):
        # Prefer historical names, skip any duplicates, then fall back to
        # a side-coded placeholder ("USA-12") so the group always hits
        # its declared size.
        name = ""
        if i < len(names) and names[i] not in existing:
            name = names[i]
        else:
            slot = len(player.astronauts) + added + 1
            name = f"{side_code}-{slot:02d}"
            while name in existing:
                slot += 1
                name = f"{side_code}-{slot:02d}"
        existing.add(name)
        player.astronauts.append(Astronaut(
            id=uuid.uuid4().hex[:6],
            name=name,
            capsule=rng.randint(RECRUIT_SKILL_MIN, RECRUIT_SKILL_MAX),
            lm_pilot=rng.randint(RECRUIT_SKILL_MIN, RECRUIT_SKILL_MAX),
            eva=rng.randint(RECRUIT_SKILL_MIN, RECRUIT_SKILL_MAX),
            docking=rng.randint(RECRUIT_SKILL_MIN, RECRUIT_SKILL_MAX),
            endurance=rng.randint(RECRUIT_SKILL_MIN, RECRUIT_SKILL_MAX),
            compatibility=rng.choice([c.value for c in Compatibility]),
            basic_training_remaining=BASIC_TRAINING_TURNS,
        ))
        added += 1
    player.budget -= group.cost
    player.next_recruitment_group += 1
    chatter_react(
        state.log, "recruit_group", rng,
        character=_chatter_character(player, rng),
    )
    return True


# ----------------------------------------------------------------------
# Phase H — intelligence
# ----------------------------------------------------------------------


def _intel_season_stamp(state: GameState) -> str:
    """Season-unique key used to gate one-intel-per-season."""
    return f"{state.year}-{state.season.value}"


def intel_available(player: Player, state: GameState) -> tuple[bool, str]:
    """Return (can_request, reason). reason is empty on success."""
    if player.budget < INTEL_COST:
        return False, f"need {INTEL_COST} MB"
    if player.intel_requested_on == _intel_season_stamp(state):
        return False, "already requested this season"
    opponent = state.other_player(player.player_id) if state.other_player(player.player_id) else None
    if opponent is None or opponent.side is None:
        return False, "no opponent"
    return True, ""


def request_intel(
    player: Player, state: GameState, rng: random.Random | None = None,
) -> bool:
    """Spend INTEL_COST MB and snapshot a noisy report on the opponent.
    Returns True on success. Enforces one report per (year, season) via
    Player.intel_requested_on. The report stored on the player is a
    best-guess view — reliability bands are ±INTEL_RELIABILITY_NOISE,
    and the rumored-mission field is the opponent's actual scheduled
    launch with probability INTEL_RUMOR_ACCURATE, otherwise empty."""
    ok, _reason = intel_available(player, state)
    if not ok:
        return False
    rng = rng or random.Random()
    opponent = state.other_player(player.player_id)
    assert opponent is not None  # guarded by intel_available
    # Reliability bands per rocket + module. Noise is symmetric around
    # the true value, then clamped to [0, RELIABILITY_CAP].
    estimates: dict[str, tuple[int, int]] = {}
    for rocket in Rocket:
        true = opponent.rocket_reliability(rocket)
        low = max(0, true - INTEL_RELIABILITY_NOISE)
        high = min(RELIABILITY_CAP, true + INTEL_RELIABILITY_NOISE)
        estimates[rocket.value] = (low, high)
    for module in Module:
        true = opponent.module_reliability(module)
        low = max(0, true - INTEL_RELIABILITY_NOISE)
        high = min(RELIABILITY_CAP, true + INTEL_RELIABILITY_NOISE)
        estimates[module.value] = (low, high)
    # Rumored scheduled mission — pull from whatever's on the opponent's
    # pads. Multiple pads are possible; pick the first scheduled, which
    # is the one most likely to fly next.
    rumored_id = ""
    rumored_name = ""
    scheduled = next(
        (pad.scheduled_launch for pad in opponent.pads if pad.scheduled_launch),
        None,
    )
    if scheduled is not None and rng.random() <= INTEL_RUMOR_ACCURATE:
        rumored_id = scheduled.mission_id
        mission = MISSIONS_BY_ID.get(MissionId(rumored_id)) if rumored_id else None
        rumored_name = mission.name if mission else rumored_id

    report = IntelReport(
        taken_year=state.year,
        taken_season=state.season.value,
        opponent_side=opponent.side.value if opponent.side else "",
        rocket_estimates=estimates,
        rumored_mission=rumored_id,
        rumored_mission_name=rumored_name,
        active_crew_count=len(opponent.active_astronauts()),
    )
    player.latest_intel = report
    player.intel_requested_on = _intel_season_stamp(state)
    player.budget -= INTEL_COST
    state.log.append(
        f"INTEL: {player.username} requested a report on "
        f"{opponent.side.value if opponent.side else '?'}."
    )
    return True


def submit_turn(
    player: Player,
    rd_rocket: Rocket | None = None,
    rd_module: Module | None = None,
    rd_spend: int = 0,
    launch: MissionId | None = None,
    objectives: list[ObjectiveId] | None = None,
    crew: list[str] | None = None,
) -> None:
    # pick at most one R&D target; rocket wins if both provided.
    if rd_rocket is not None:
        player.pending_rd_target = rd_rocket.value
    elif rd_module is not None:
        player.pending_rd_target = rd_module.value
    else:
        player.pending_rd_target = None
    player.pending_rd_spend = max(0, min(rd_spend, player.budget))

    player.pending_launch = None
    player.pending_objectives = []
    player.pending_crew = []
    # With VAB scheduling, only one mission can be on the manifest at a
    # time. Attempting to queue a new launch while one is already
    # scheduled is silently dropped — the player must resolve or scrub
    # the existing commitment first.
    # Accept a new launch if any pad is free — the actual pad assignment
    # happens during resolve in _promote_pending_to_scheduled.
    if launch is not None and player.any_pad_available():
        mission = MISSIONS_BY_ID[launch]
        eff_rocket = effective_rocket(player, mission)
        eff_cost = effective_launch_cost(player, mission)
        assembly_due = int(eff_cost * ASSEMBLY_COST_FRACTION)
        # Only need the assembly slice up front; the remainder is due at
        # actual launch (next turn). If the player's budget can't cover
        # even assembly + R&D this turn, reject the schedule.
        can_afford = player.budget >= assembly_due + player.pending_rd_spend
        crew_ok = not mission.manned or _select_crew(player, mission) is not None
        tier_ok = player.is_tier_unlocked(mission.tier)
        arch_ok = meets_architecture_prereqs(player, mission)
        modules_ok = all(player.module_built(m) for m in mission.requires_modules)
        if (
            player.rocket_built(eff_rocket) and can_afford and crew_ok
            and tier_ok and arch_ok and modules_ok
        ):
            player.pending_launch = launch.value
            # filter objectives to the mission's catalog; drop any with unmet
            # hardware prereqs.
            allowed = {o.id: o for o in objectives_for(mission.id)}
            for obj_id in objectives or ():
                obj = allowed.get(obj_id)
                if obj is None:
                    continue
                if obj.requires_module and not player.module_built(obj.requires_module):
                    continue
                player.pending_objectives.append(obj.id.value)
            # Phase O — manual crew assignment. We accept the picked
            # list iff every member is on the roster, flight-ready, and
            # the count exactly matches the mission's crew_size; an
            # invalid pick falls back to auto top-skilled selection so
            # the launch isn't outright dropped.
            if crew and mission.manned and len(crew) == mission.crew_size:
                ok_ids: list[str] = []
                for astro_id in crew:
                    astro = next(
                        (a for a in player.astronauts if a.id == astro_id),
                        None,
                    )
                    if astro is None or not astro.flight_ready:
                        ok_ids = []
                        break
                    ok_ids.append(astro_id)
                player.pending_crew = ok_ids
    player.turn_submitted = True


def scrub_scheduled(player: Player, pad_id: str | None = None) -> bool:
    """Cancel a scheduled launch. Refunds SCRUB_REFUND_FRACTION of the
    assembly cost already paid; the rest is sunk. Returns True if a
    scheduled launch was cleared.

    When pad_id is provided, only that pad's slot is scrubbed. When
    None, scrubs the first pad that has a ScheduledLaunch — useful from
    UIs that don't care which pad. The pad stays otherwise untouched
    (no damage applied), so it's immediately reusable next turn."""
    candidates = (
        [p for p in player.pads if p.pad_id == pad_id]
        if pad_id is not None else player.pads
    )
    for pad in candidates:
        if pad.scheduled_launch is None:
            continue
        refund = int(pad.scheduled_launch.assembly_cost_paid * SCRUB_REFUND_FRACTION)
        player.budget += refund
        pad.scheduled_launch = None
        return True
    return False


def start_training(
    player: Player,
    astronaut_id: str,
    skill: Skill,
) -> bool:
    """Send an astronaut into advanced training on `skill`. Costs
    ADVANCED_TRAINING_COST MB up-front, takes ADVANCED_TRAINING_TURNS
    seasons. Returns True if the block started.

    Rejected if:
      - the astronaut isn't found or is KIA
      - they're already in basic/advanced training or hospital (must
        finish or cancel first)
      - the player can't afford the cost
    """
    astro = next((a for a in player.astronauts if a.id == astronaut_id), None)
    if astro is None or not astro.active:
        return False
    if (
        astro.basic_training_remaining > 0
        or astro.advanced_training_remaining > 0
        or astro.hospital_remaining > 0
    ):
        return False
    if player.budget < ADVANCED_TRAINING_COST:
        return False
    player.budget -= ADVANCED_TRAINING_COST
    astro.advanced_training_skill = skill.value
    astro.advanced_training_remaining = ADVANCED_TRAINING_TURNS
    return True


def cancel_training(player: Player, astronaut_id: str) -> bool:
    """Pull an astronaut out of advanced training early. Refunds
    TRAINING_CANCEL_REFUND_FRACTION of the cost; no skill gain.
    Returns True if anything was cancelled."""
    astro = next((a for a in player.astronauts if a.id == astronaut_id), None)
    if astro is None or astro.advanced_training_remaining <= 0:
        return False
    refund = int(ADVANCED_TRAINING_COST * TRAINING_CANCEL_REFUND_FRACTION)
    player.budget += refund
    astro.advanced_training_skill = ""
    astro.advanced_training_remaining = 0
    return True


def all_turns_in(state: GameState) -> bool:
    return state.phase == Phase.PLAYING and all(p.turn_submitted for p in state.players)


def resolve_turn(state: GameState, rng: random.Random | None = None) -> None:
    """Apply each player's pending actions, advance season, emit log lines."""
    rng = rng or random.Random()
    state.log.clear()
    state.last_launches.clear()

    for player in state.players:
        _apply_rd(player, state, rng)
        # Fire any launch that was committed last turn first — it's the
        # one players are expecting results on — then promote a newly-
        # submitted launch into the VAB for NEXT turn's resolve.
        # Tick training / hospital counters BEFORE this turn's launch
        # resolves. That way (a) existing trainees / patients count down
        # from last turn, and (b) fresh admits from a just-failed mission
        # start with their full counter — the tick later would otherwise
        # immediately decrement them.
        _tick_training_and_recovery(player, state)
        _tick_pad_repairs(player, state)
        _tick_mood_and_retirements(player, state)
        _resolve_scheduled_launch(player, state, rng)
        _promote_pending_to_scheduled(player, state)
        _apply_passive_training(player, rng)
        player.pending_rd_target = None
        player.pending_rd_spend = 0
        player.pending_launch = None
        player.pending_objectives = []
        player.pending_crew = []
        player.turn_submitted = False
        player.budget += SEASON_REFILL

    _check_victory(state)

    if state.phase == Phase.PLAYING:
        prev_year = state.year
        state.season, state.year = next_season(state.season, state.year)
        state.log.append(f"Advancing to {state.season.value} {state.year}.")
        if state.year > prev_year:
            # We just rolled Winter→Spring of a new year. Run the
            # Government Review on the year just ended.
            _run_government_review(state, ended_year=prev_year, rng=rng)
        _check_historical_milestones(state)
        _check_calendar_deadline(state)
        if state.phase == Phase.PLAYING:
            _roll_season_news(state, rng)
            _snapshot_prestige(state)


# ----------------------------------------------------------------------
# R&D
# ----------------------------------------------------------------------


def _apply_rd(player: Player, state: GameState, rng: random.Random) -> None:
    target = player.pending_rd_target
    if player.pending_rd_spend <= 0 or not target:
        return
    if target not in RD_SPEED:
        return
    current = player.hardware_reliability(target)
    if current >= RELIABILITY_CAP:
        return  # already perfect; refuse to burn budget
    spend = player.pending_rd_spend
    batches = spend // RD_BATCH_COST
    actually_spent = batches * RD_BATCH_COST  # refund unused remainder
    player.budget -= actually_spent

    crossed_threshold = current < MIN_RELIABILITY_TO_LAUNCH
    gain = 0
    for _ in range(batches):
        if current + gain >= RELIABILITY_CAP:
            break
        gain += _roll_rd_batch(target, current + gain, rng)
    new_reliability = min(RELIABILITY_CAP, current + gain)
    player.reliability[target] = new_reliability

    state.log.append(
        f"{player.username} invests {actually_spent} MB into {target} R&D "
        f"→ reliability {current}% → {new_reliability}%."
    )
    if crossed_threshold and new_reliability >= MIN_RELIABILITY_TO_LAUNCH:
        state.log.append(
            f"{player.username}'s {target} is now ready for use."
        )


def _roll_rd_batch(target: str, current: int, rng: random.Random) -> int:
    """One R&D batch roll: returns a non-negative integer gain in reliability.
    Outcome distribution shaped to mimic BARIS-style variance — most batches
    produce small or no movement; occasional breakthroughs jump the target
    forward. Diminishing returns scale gains as reliability approaches the cap.
    """
    speed = RD_SPEED.get(target, 1.0)
    factor = speed * max(0.25, 1 - current / 100)
    r = rng.random()
    if r < 0.50:
        raw = 0  # stall
    elif r < 0.80:
        raw = 1
    elif r < 0.95:
        raw = 2
    else:
        raw = 4  # breakthrough
    if raw == 0:
        return 0
    scaled = raw * factor
    # Even heavily scaled rolls still produce at least 1 point when the
    # underlying raw roll was non-zero, so the player never feels completely
    # stuck on a bad streak combined with a bad rocket.
    return max(1, int(round(scaled)))


# ----------------------------------------------------------------------
# Launches
# ----------------------------------------------------------------------


def _promote_pending_to_scheduled(player: Player, state: GameState) -> None:
    """Take a freshly-submitted launch (player.pending_launch) and land it
    into the first available pad for NEXT turn's resolve. Deducts the
    assembly portion of the cost now (simulating VAB integration work).

    No-op if the player isn't trying to schedule, no pad is available,
    or the mission is unresolvable."""
    if not player.pending_launch:
        return
    pad = player.available_pad()
    if pad is None:
        state.log.append(
            f"{player.username}: all launch pads occupied or in repair — "
            "queued launch dropped."
        )
        return
    try:
        mission = MISSIONS_BY_ID[MissionId(player.pending_launch)]
    except (ValueError, KeyError):
        return
    eff_rocket = effective_rocket(player, mission)
    eff_cost = effective_launch_cost(player, mission)
    assembly = int(eff_cost * ASSEMBLY_COST_FRACTION)
    remaining = eff_cost - assembly
    if player.budget < assembly:
        state.log.append(
            f"{player.username} — {mission.name}: assembly cancelled "
            f"({assembly} MB needed, budget short)."
        )
        return
    player.budget -= assembly
    pad.scheduled_launch = ScheduledLaunch(
        mission_id=mission.id.value,
        rocket_class=eff_rocket.value,
        launch_cost_total=eff_cost,
        assembly_cost_paid=assembly,
        launch_cost_remaining=remaining,
        objectives=list(player.pending_objectives),
        architecture=player.architecture,
        scheduled_year=state.year,
        scheduled_season=state.season.value,
        crew=list(player.pending_crew),
    )
    state.log.append(
        f"{player.username} — {mission.name}: assembled on Pad {pad.pad_id} "
        f"(assembly paid: {assembly} MB, launch due: {remaining} MB)."
    )


def _resolve_scheduled_launch(
    player: Player, state: GameState, rng: random.Random,
) -> None:
    """Fire every pad that has a ScheduledLaunch on the manifest. Each
    pad fires independently and produces its own LaunchReport. Pads are
    processed in pad_id order (A → B → C) so the client sees a stable
    animation sequence."""
    for pad in player.pads:
        if pad.scheduled_launch is not None:
            _resolve_pad_launch(player, pad, state, rng)


def _resolve_pad_launch(
    player: Player,
    pad: LaunchPad,
    state: GameState,
    rng: random.Random,
) -> None:
    """Fire the single ScheduledLaunch sitting on `pad`. Clears the slot
    on every exit path. On catastrophic failure (crew KIA, docking ship
    loss) the pad is damaged and scheduled for repair."""
    sl = pad.scheduled_launch
    assert sl is not None  # _resolve_scheduled_launch guards this
    # Consume the slot up-front; every exit path leaves it cleared.
    pad.scheduled_launch = None
    try:
        mission = MISSIONS_BY_ID[MissionId(sl.mission_id)]
        eff_rocket = Rocket(sl.rocket_class)
    except (ValueError, KeyError):
        return
    eff_cost = sl.launch_cost_total

    report = LaunchReport(
        side=player.side.value if player.side else "",
        username=player.username,
        mission_id=mission.id.value,
        mission_name=mission.name,
        rocket=rocket_display_name(eff_rocket, player.side),
        rocket_class=eff_rocket.value,
        manned=mission.manned,
        launch_cost=eff_cost,
        reliability_before=player.rocket_reliability(eff_rocket),
        reliability_after=player.rocket_reliability(eff_rocket),
    )
    state.last_launches.append(report)

    def _abort(reason_log: str, reason_report: str) -> None:
        report.aborted = True
        report.abort_reason = reason_report
        state.log.append(reason_log)

    if not player.rocket_built(eff_rocket):
        _abort(
            f"{player.username} aborts {mission.name} — rocket not launch-ready.",
            "rocket not launch-ready",
        )
        return
    if player.budget < sl.launch_cost_remaining:
        _abort(
            f"{player.username} aborts {mission.name} — budget short "
            f"({sl.launch_cost_remaining} MB needed for launch).",
            "budget short at launch",
        )
        return
    if not player.is_tier_unlocked(mission.tier):
        _abort(
            f"{player.username} aborts {mission.name} — program not unlocked.",
            "program not unlocked",
        )
        return
    if not meets_architecture_prereqs(player, mission):
        _abort(
            f"{player.username} aborts {mission.name} — architecture prereqs not met.",
            "architecture prereqs not met",
        )
        return

    crew: list[Astronaut] = []
    if mission.manned:
        # Phase O — honour the manually-picked crew if every member is
        # still flight-ready when the launch fires (catch e.g. an
        # astronaut who got hospitalised between schedule and resolve).
        # Fall back to auto top-skilled selection otherwise.
        crew = _resolve_scheduled_crew(player, mission, sl) or []
        if not crew:
            _abort(
                f"{player.username} aborts {mission.name} — no available crew.",
                "no available crew",
            )
            return
        report.crew = [a.name for a in crew]

    player.budget -= sl.launch_cost_remaining
    crew_bonus = _crew_bonus(crew, mission)
    reliability_bonus = (
        (player.rocket_reliability(eff_rocket) - 50) * RELIABILITY_SWING_PER_POINT
    )
    compat_bonus = crew_compatibility_bonus(crew)
    component_bonus = component_reliability_bonus(player, mission)
    base = effective_base_success(player, mission)
    recon_bonus, lm_penalty = effective_lunar_modifier(player, mission)
    success_chance = (
        base + crew_bonus + reliability_bonus + compat_bonus
        + component_bonus + recon_bonus - lm_penalty
    )
    report.base_success = base
    report.crew_bonus = crew_bonus
    report.reliability_bonus = reliability_bonus
    report.compat_bonus = compat_bonus
    report.component_bonus = component_bonus
    report.lunar_recon_bonus = recon_bonus
    report.lm_points_penalty = lm_penalty
    report.effective_success = success_chance

    prestige_start = player.prestige
    roll = rng.random()
    if roll < success_chance:
        report.success = True
        _bump_reliability(player, eff_rocket, RELIABILITY_GAIN_ON_SUCCESS)
        _handle_mission_success(player, mission, crew, state, report)
        _grant_lunar_progress(player, mission, success=True, state=state)
        _resolve_objectives(
            player, mission, crew, state, rng, eff_rocket, report,
            objectives_raw=sl.objectives,
        )
        if mission.manned and crew:
            _bump_crew_mood(crew, MOOD_SUCCESS_BUMP)
            # Phase T — successful crew earn a normal post-flight rest.
            for a in crew:
                a.rest_remaining = max(a.rest_remaining, REST_AFTER_FLIGHT)
        chatter_react(
            state.log, "launch_success", rng,
            character=_chatter_character(player, rng),
            rocket=report.rocket,
        )
    else:
        _handle_mission_failure(player, mission, crew, state, rng, eff_rocket, report)
        _grant_lunar_progress(player, mission, success=False, state=state)
        if mission.manned and crew:
            # Survivors take a morale hit plus an extra hit per crewmate KIA.
            _bump_crew_mood(crew, -MOOD_FAILURE_DROP)
            if report.deaths:
                _bump_crew_mood(crew, -MOOD_KIA_CREW_DROP * len(report.deaths))
            # Phase T — failed-flight survivors rest longer than a clean
            # mission. KIA crew already have status=KIA so no rest needed.
            for a in crew:
                if a.active:
                    a.rest_remaining = max(a.rest_remaining, REST_AFTER_FAILURE)
        chatter_react(
            state.log, "launch_failure", rng,
            character=_chatter_character(player, rng),
            rocket=report.rocket,
            phase=report.failed_phase or "stage I",
        )
        if report.deaths:
            chatter_react(
                state.log, "kia", rng,
                character=_chatter_character(player, rng),
                names=", ".join(report.deaths),
            )
    report.reliability_after = player.rocket_reliability(eff_rocket)
    report.prestige_delta = player.prestige - prestige_start
    # Pad damage: if the flight killed crew or any objective triggered a
    # catastrophic ship loss, this pad is offline for PAD_REPAIR_TURNS.
    if _launch_damaged_pad(report):
        pad.repair_turns_remaining = PAD_REPAIR_TURNS
        state.log.append(
            f"{player.username}: Pad {pad.pad_id} damaged in the incident — "
            f"{PAD_REPAIR_TURNS} seasons of repair needed."
        )
    # Phase L — permanent museum record of this launch.
    if not report.aborted:
        state.mission_history.append(MissionHistoryEntry(
            year=state.year,
            season=state.season.value,
            side=report.side,
            mission_id=report.mission_id,
            mission_name=report.mission_name,
            rocket=report.rocket,
            manned=report.manned,
            crew=list(report.crew),
            success=report.success,
            prestige_delta=report.prestige_delta,
            first_claimed=report.first_claimed,
            deaths=list(report.deaths),
        ))


def _launch_damaged_pad(report: LaunchReport) -> bool:
    """A pad is damaged if the flight killed crew or any objective caused
    a catastrophic ship loss. Aborted launches never damage the pad
    (they didn't leave the ground)."""
    if report.aborted:
        return False
    if report.deaths:
        return True
    return any(obj.ship_lost for obj in report.objectives)


def _resolve_objectives(
    player: Player,
    mission: Mission,
    crew: list[Astronaut],
    state: GameState,
    rng: random.Random,
    eff_rocket: Rocket,
    report: LaunchReport,
    objectives_raw: list[str] | None = None,
) -> None:
    """Attempt each opt-in objective the player queued. Each objective rolls
    independently using a crew member's relevant skill. Successes grant extra
    prestige and a skill bump; failures can kill the astronaut performing it
    (EVA) or destroy the ship entirely (docking), depending on the objective.

    If `objectives_raw` is None (the default), read from `player.pending_objectives`.
    The VAB path passes the list snapshotted at schedule time so mid-turn
    objective toggles don't retroactively affect an in-flight launch."""
    raw_list = (
        objectives_raw if objectives_raw is not None else player.pending_objectives
    )
    if not mission.manned or not raw_list:
        return
    catalog = {o.id: o for o in objectives_for(mission.id)}
    for raw in raw_list:
        try:
            obj_id = ObjectiveId(raw)
        except ValueError:
            continue
        obj = catalog.get(obj_id)
        if obj is None:
            continue
        obj_report = ObjectiveReport(objective_id=obj.id.value, name=obj.name)
        report.objectives.append(obj_report)

        # Docking requires the module to still be available at launch time.
        if obj.requires_module and not player.module_built(obj.requires_module):
            obj_report.skipped = True
            obj_report.skip_reason = f"missing {obj.requires_module.value}"
            state.log.append(
                f"  - {obj.name}: skipped (missing {obj.requires_module.value})."
            )
            continue

        # Crew member performing the objective — the one with the highest
        # relevant skill still alive after the main mission.
        performers = [a for a in crew if a.active]
        if not performers:
            obj_report.skipped = True
            obj_report.skip_reason = "no crew available"
            return  # whole crew already gone, can't do anything
        performers.sort(key=lambda a: a.skill(obj.required_skill), reverse=True)
        performer = performers[0]
        obj_report.performer = performer.name

        # Effective success: base + performer's skill contribution (same
        # CREW_MAX_BONUS scaling as the main mission's primary_skill).
        skill_factor = performer.skill(obj.required_skill) / 100.0
        effective = obj.base_success + skill_factor * CREW_MAX_BONUS
        obj_report.effective_success = effective
        prestige_before_obj = player.prestige
        if rng.random() < effective:
            player.prestige += obj.prestige_bonus
            performer.bump_skill(obj.required_skill, 5)
            obj_report.success = True
            obj_report.prestige_delta = player.prestige - prestige_before_obj
            state.log.append(
                f"  - {obj.name}: {performer.name} succeeded (+{obj.prestige_bonus} prestige)."
            )
            continue

        # Failure — decide the consequence.
        if obj.fail_ship_loss_chance > 0 and rng.random() < obj.fail_ship_loss_chance:
            # Catastrophic ship loss. All remaining active crew die; the
            # rocket reliability takes a heavy hit on top of the standard
            # mission-success bump that already happened.
            dead: list[str] = []
            for astro in crew:
                if astro.active:
                    astro.status = AstronautStatus.KIA.value
                    dead.append(astro.name)
            _bump_reliability(player, eff_rocket, -15)
            player.prestige = max(0, player.prestige - 10)
            obj_report.ship_lost = True
            obj_report.deaths = list(dead)
            obj_report.prestige_delta = player.prestige - prestige_before_obj
            state.log.append(
                f"  - {obj.name}: CATASTROPHIC FAILURE. Ship lost. "
                f"KIA: {', '.join(dead) or 'crew'}. -15 reliability, -10 prestige."
            )
            return  # no further objectives — everyone's dead
        if obj.fail_crew_death_chance > 0 and rng.random() < obj.fail_crew_death_chance:
            performer.status = AstronautStatus.KIA.value
            player.prestige = max(0, player.prestige - DEATH_PRESTIGE_PENALTY)
            obj_report.deaths = [performer.name]
            obj_report.prestige_delta = player.prestige - prestige_before_obj
            state.log.append(
                f"  - {obj.name}: {performer.name} did not return. "
                f"-{DEATH_PRESTIGE_PENALTY} prestige."
            )
            continue
        obj_report.prestige_delta = player.prestige - prestige_before_obj
        state.log.append(f"  - {obj.name}: failed (no casualties).")


def _bump_reliability(player: Player, rocket: Rocket, delta: int) -> None:
    """Adjust reliability after a flight. Failures can't drop a launch-ready
    rocket below RELIABILITY_FLOOR (so one bad flight doesn't unlaunch you)."""
    current = player.rocket_reliability(rocket)
    new_value = current + delta
    if current >= MIN_RELIABILITY_TO_LAUNCH:
        new_value = max(RELIABILITY_FLOOR, new_value)
    new_value = min(RELIABILITY_CAP, max(0, new_value))
    player.reliability[rocket.value] = new_value


def _bump_recon(player: Player, delta: int, state: GameState) -> None:
    """Clamp-and-log helper for lunar reconnaissance bumps."""
    if delta <= 0:
        return
    new_recon = min(LUNAR_RECON_CAP, player.lunar_recon + delta)
    if new_recon == player.lunar_recon:
        return
    player.lunar_recon = new_recon
    state.log.append(f"{player.username}: lunar recon → {new_recon}%.")


def _grant_lunar_progress(
    player: Player,
    mission: Mission,
    success: bool,
    state: GameState,
) -> None:
    """Apply recon and LM-point rewards based on which mission just
    resolved. Only a handful of missions are relevant; everything else
    is a no-op."""
    mid = mission.id
    if success:
        lm_gain = 0
        if mid == MissionId.LUNAR_PASS:
            _bump_recon(player, RECON_FROM_LUNAR_PASS, state)
        elif mid == MissionId.LUNAR_ORBIT:
            _bump_recon(player, RECON_FROM_LUNAR_ORBIT, state)
        elif mid == MissionId.LUNAR_LANDING:
            _bump_recon(player, RECON_FROM_UNMANNED_LANDING_OK, state)
            lm_gain = LM_POINTS_FROM_UNMANNED_LANDING
        elif mid == MissionId.MANNED_LUNAR_ORBIT:
            _bump_recon(player, RECON_FROM_MANNED_LUNAR_ORBIT, state)
            lm_gain = LM_POINTS_FROM_MANNED_LUNAR_ORBIT
        elif mid == MissionId.MANNED_ORBITAL:
            lm_gain = LM_POINTS_FROM_MANNED_ORBITAL
        elif mid == MissionId.MULTI_CREW_ORBITAL:
            lm_gain = LM_POINTS_FROM_MULTI_CREW
        elif mid == MissionId.ORBITAL_EVA:
            lm_gain = LM_POINTS_FROM_ORBITAL_EVA
        elif mid == MissionId.ORBITAL_DOCKING:
            lm_gain = LM_POINTS_FROM_ORBITAL_DOCKING
        elif mid == MissionId.LM_EARTH_TEST:
            lm_gain = LM_POINTS_FROM_LM_EARTH_TEST
        elif mid == MissionId.LM_LUNAR_TEST:
            # Lunar LM test also feeds reconnaissance since the stage
            # orbits the Moon alongside its hardware checkout.
            _bump_recon(player, RECON_FROM_MANNED_LUNAR_ORBIT, state)
            lm_gain = LM_POINTS_FROM_LM_LUNAR_TEST
        if lm_gain > 0:
            player.lm_points += lm_gain
            state.log.append(
                f"{player.username}: LM programme +{lm_gain} (now "
                f"{player.lm_points}/{LM_POINTS_REQUIRED})."
            )
    else:
        # Only the unmanned lunar landing failure feeds recon back — a
        # crashed Surveyor still beams photos home before impact.
        if mid == MissionId.LUNAR_LANDING:
            _bump_recon(player, RECON_FROM_UNMANNED_LANDING_FAIL, state)


def _next_tier(tier: ProgramTier) -> ProgramTier:
    order = [ProgramTier.ONE, ProgramTier.TWO, ProgramTier.THREE]
    idx = order.index(tier)
    return order[min(idx + 1, len(order) - 1)]


def _chatter_character(player: Player, rng: random.Random) -> str:
    """Pick a random alive astronaut name on the player's roster for
    chatter `{character}` substitution. Falls back to the player's
    username if the roster is empty (e.g. before start_game seeds it)."""
    pool = [a.name for a in player.astronauts if a.active]
    if not pool:
        return player.username
    return rng.choice(pool)


def _select_crew(player: Player, mission: Mission) -> list[Astronaut] | None:
    """Pick the top-skilled FLIGHT-READY astronauts for this mission, or
    None if the flight-ready roster can't fill it. Astronauts currently
    in basic training, advanced training, or the hospital are excluded."""
    if not mission.manned or mission.crew_size == 0:
        return []
    pool = player.flight_ready_astronauts()
    if len(pool) < mission.crew_size:
        return None
    skill_key = mission.primary_skill or Skill.CAPSULE
    ranked = sorted(pool, key=lambda a: a.skill(skill_key), reverse=True)
    return ranked[:mission.crew_size]


def _resolve_scheduled_crew(
    player: Player, mission: Mission, sl: ScheduledLaunch,
) -> list[Astronaut] | None:
    """Phase O — pick the crew at launch time. Honours the player's
    manual selection from sl.crew when every member is still on the
    roster and flight-ready; otherwise falls back to _select_crew's
    auto top-skilled pick. Empty sl.crew (legacy or auto-pick path) is
    indistinguishable from "no manual choice"."""
    if not mission.manned:
        return []
    if sl.crew and len(sl.crew) == mission.crew_size:
        manual: list[Astronaut] = []
        valid = True
        for astro_id in sl.crew:
            astro = next(
                (a for a in player.astronauts if a.id == astro_id), None,
            )
            if astro is None or not astro.flight_ready:
                valid = False
                break
            manual.append(astro)
        if valid:
            return manual
    return _select_crew(player, mission)


def _crew_bonus(crew: list[Astronaut], mission: Mission) -> float:
    if not mission.manned or mission.primary_skill is None or not crew:
        return 0.0
    avg = sum(a.skill(mission.primary_skill) for a in crew) / len(crew)
    return (avg / 100.0) * CREW_MAX_BONUS


# ----------------------------------------------------------------------
# Phase K — crew compatibility + mood
# ----------------------------------------------------------------------

_OPPOSITE_COMPAT: set[frozenset[str]] = {
    frozenset({Compatibility.A.value, Compatibility.C.value}),
    frozenset({Compatibility.B.value, Compatibility.D.value}),
}


def crew_compatibility_bonus(crew: list[Astronaut]) -> float:
    """Average pairwise compatibility of the crew, scaled to at most
    ±CREW_COMPAT_MAX_BONUS. Same/adjacent tags mesh (+1 each pair);
    opposites (A-C, B-D) clash (-1). Returns 0.0 for solo crews."""
    if len(crew) < 2:
        return 0.0
    total = 0
    pairs = 0
    for i in range(len(crew)):
        for j in range(i + 1, len(crew)):
            pair = frozenset({crew[i].compatibility, crew[j].compatibility})
            total += -1 if pair in _OPPOSITE_COMPAT else 1
            pairs += 1
    return (total / pairs) * CREW_COMPAT_MAX_BONUS


def _clamp_mood(value: int) -> int:
    return max(0, min(MOOD_MAX, value))


def _bump_crew_mood(crew: list[Astronaut], delta: int) -> None:
    """Adjust every active crew member's mood by `delta`, clamped to
    [0, MOOD_MAX]. Skips KIA / retired members."""
    for astro in crew:
        if astro.status != AstronautStatus.ACTIVE.value:
            continue
        astro.mood = _clamp_mood(astro.mood + delta)


def _handle_mission_success(
    player: Player,
    mission: Mission,
    crew: list[Astronaut],
    state: GameState,
    report: LaunchReport,
) -> None:
    gain = mission.prestige_success
    bonus = 0
    if mission.id.value not in state.first_completed and player.side is not None:
        state.first_completed[mission.id.value] = player.side.value
        bonus = mission.first_bonus
        report.first_claimed = True
    player.prestige += gain + bonus
    previously_locked_next_tier = not player.is_tier_unlocked(_next_tier(mission.tier))
    player.mission_successes[mission.id.value] = (
        player.mission_successes.get(mission.id.value, 0) + 1
    )
    crew_note = ""
    if crew:
        crew_note = f" [crew: {', '.join(a.name for a in crew)}]"
        # successful mission gives crew a small experience bump in the mission's primary skill.
        if mission.primary_skill is not None:
            for a in crew:
                a.bump_skill(mission.primary_skill, 5)
    bonus_txt = f" +{bonus} FIRST!" if bonus else ""
    state.log.append(
        f"{player.username} — {mission.name}: SUCCESS (+{gain}{bonus_txt} prestige){crew_note}."
    )
    # If this success unlocks the next tier, announce it.
    if previously_locked_next_tier and player.is_tier_unlocked(_next_tier(mission.tier)):
        from baris.state import program_name
        next_program = program_name(_next_tier(mission.tier), player.side)
        state.log.append(f"{player.username} unlocks the {next_program} program.")
    if mission.id == MissionId.MANNED_LUNAR_LANDING:
        state.phase = Phase.ENDED
        state.winner = player.side
        report.ended_game = True
        state.log.append(f"{player.username} lands astronauts on the Moon — game over!")


def _handle_mission_failure(
    player: Player,
    mission: Mission,
    crew: list[Astronaut],
    state: GameState,
    rng: random.Random,
    eff_rocket: Rocket,
    report: LaunchReport,
) -> None:
    player.prestige = max(0, player.prestige - mission.prestige_fail)

    # Phase P — pick which phase the failure happened in. Uniformly
    # random across the mission's declared phases. Used purely for
    # cinematic labelling in the launch report + log; doesn't change
    # any of the consequence math below.
    if mission.phases:
        report.failed_phase = rng.choice(list(mission.phases)).value

    phase_note = f" at {report.failed_phase}" if report.failed_phase else ""

    if not mission.manned:
        # Unmanned failures still teach you something — crashed probes feed
        # back into R&D. Reliability creeps up; no budget hit.
        _bump_reliability(player, eff_rocket, UNMANNED_FAILURE_RD_GAIN)
        state.log.append(
            f"{player.username} — {mission.name}: FAILURE{phase_note} "
            f"(-{mission.prestige_fail} prestige, +{UNMANNED_FAILURE_RD_GAIN}% reliability "
            f"from post-flight analysis)."
        )
        return

    # Manned failure: real consequences.
    _bump_reliability(player, eff_rocket, -RELIABILITY_LOSS_ON_FAIL)
    budget_cut = min(player.budget, MANNED_FAILURE_BUDGET_CUT)
    player.budget -= budget_cut
    report.budget_cut = budget_cut

    deaths: list[str] = []
    for astro in crew:
        if rng.random() < DEATH_CHANCE_ON_FAIL:
            astro.status = AstronautStatus.KIA.value
            deaths.append(astro.name)
    report.deaths = list(deaths)
    # Surviving crew may still need hospital recovery — rough knock
    # around, radiation exposure, hypothermia on splashdown, etc.
    # Rolls only on actually-alive crew members so KIAs don't consume
    # extra RNG values that existing tests rely on.
    hospitalized: list[str] = []
    for astro in crew:
        if astro.status != AstronautStatus.ACTIVE.value:
            continue
        if rng.random() < HOSPITAL_CHANCE_ON_FAIL:
            astro.hospital_remaining = HOSPITAL_STAY_TURNS
            hospitalized.append(astro.name)
    kia_note = ""
    if deaths:
        player.prestige = max(0, player.prestige - DEATH_PRESTIGE_PENALTY * len(deaths))
        kia_note = (
            f", KIA: {', '.join(deaths)} -{DEATH_PRESTIGE_PENALTY * len(deaths)} prestige"
        )
    hosp_note = (
        f", hospitalised: {', '.join(hospitalized)}" if hospitalized else ""
    )
    state.log.append(
        f"{player.username} — {mission.name}: FAILURE{phase_note} "
        f"(-{mission.prestige_fail} prestige{kia_note}{hosp_note}). "
        f"Program funding cut by {budget_cut} MB."
    )


# ----------------------------------------------------------------------
# Training
# ----------------------------------------------------------------------


def _apply_passive_training(player: Player, rng: random.Random) -> None:
    """Every season, each active astronaut trains slightly.
    +1 to each skill, plus +3 focused on one random skill."""
    skills = list(Skill)
    for astro in player.active_astronauts():
        for s in skills:
            astro.bump_skill(s, 1)
        focus = rng.choice(skills)
        astro.bump_skill(focus, 3)


def _tick_training_and_recovery(player: Player, state: GameState) -> None:
    """Decrement each astronaut's training / hospital counters and apply
    skill gains when an advanced-training block completes."""
    for astro in player.astronauts:
        if not astro.active:
            continue
        if astro.basic_training_remaining > 0:
            astro.basic_training_remaining -= 1
            if astro.basic_training_remaining == 0:
                state.log.append(
                    f"{player.username}: {astro.name} completes basic training."
                )
        if astro.hospital_remaining > 0:
            astro.hospital_remaining -= 1
            if astro.hospital_remaining == 0:
                state.log.append(
                    f"{player.username}: {astro.name} is released from the hospital."
                )
        # Phase T — post-flight rest tick. Silent on completion to keep
        # the log uncluttered; routine recovery doesn't need a headline.
        if astro.rest_remaining > 0:
            astro.rest_remaining -= 1
        if astro.advanced_training_remaining > 0:
            astro.advanced_training_remaining -= 1
            if astro.advanced_training_remaining == 0:
                skill_val = astro.advanced_training_skill
                if skill_val:
                    try:
                        skill = Skill(skill_val)
                    except ValueError:
                        skill = None
                    if skill is not None:
                        astro.bump_skill(skill, ADVANCED_TRAINING_SKILL_GAIN)
                        state.log.append(
                            f"{player.username}: {astro.name} finishes {skill_val} "
                            f"training (+{ADVANCED_TRAINING_SKILL_GAIN} {skill_val})."
                        )
                astro.advanced_training_skill = ""


def _tick_pad_repairs(player: Player, state: GameState) -> None:
    """Tick each damaged pad's repair countdown. Idle + already-repaired
    pads are no-ops."""
    for pad in player.pads:
        if pad.repair_turns_remaining <= 0:
            continue
        pad.repair_turns_remaining -= 1
        if pad.repair_turns_remaining == 0:
            state.log.append(
                f"{player.username}: Pad {pad.pad_id} back online."
            )


def _tick_mood_and_retirements(player: Player, state: GameState) -> None:
    """Each season, active astronauts' moods drift toward MOOD_DRIFT_TARGET
    by MOOD_DRIFT_PER_TURN; anyone already above the target sheds morale
    back down at the same rate. Astronauts at or below
    MOOD_RETIREMENT_THRESHOLD retire (becoming unflyable)."""
    for astro in player.astronauts:
        if astro.status != AstronautStatus.ACTIVE.value:
            continue
        if astro.mood < MOOD_DRIFT_TARGET:
            astro.mood = _clamp_mood(astro.mood + MOOD_DRIFT_PER_TURN)
        elif astro.mood > MOOD_DRIFT_TARGET:
            astro.mood = _clamp_mood(astro.mood - MOOD_DRIFT_PER_TURN)
        if astro.mood <= MOOD_RETIREMENT_THRESHOLD:
            astro.status = AstronautStatus.RETIRED.value
            state.log.append(
                f"{player.username}: {astro.name} retires (morale bottomed out)."
            )


# ----------------------------------------------------------------------
# Victory
# ----------------------------------------------------------------------


def _check_victory(state: GameState) -> None:
    if state.phase == Phase.ENDED:
        return  # already decided by manned lunar landing
    leaders = [p for p in state.players if p.prestige >= PRESTIGE_TO_WIN]
    if not leaders:
        return
    leaders.sort(key=lambda p: p.prestige, reverse=True)
    winner = leaders[0]
    state.phase = Phase.ENDED
    state.winner = winner.side
    side_label = winner.side.value if winner.side else "?"
    state.log.append(f"{winner.username} ({side_label}) wins on prestige!")


def available_missions(player: Player) -> list[Mission]:
    """Missions the player could launch right now (rocket built, can afford, crew, tier unlocked)."""
    result: list[Mission] = []
    for m in MISSIONS_BY_ID.values():
        if not player.is_tier_unlocked(m.tier):
            continue
        if not player.rocket_built(m.rocket):
            continue
        if player.budget < m.launch_cost:
            continue
        if m.manned and _select_crew(player, m) is None:
            continue
        result.append(m)
    return result


def visible_to(player: Player, mission: Mission) -> bool:
    """True if `mission` should be shown to `player` in the mission list now.

    Hides missions categorically unavailable pending more R&D or program
    progression (tier locked, rocket unresearched). Unlike available_missions(),
    this does *not* filter on budget, crew, or architecture prereqs — those are
    actionable this turn or next and worth seeing so the player can plan.
    """
    from baris.state import MISSIONS  # avoid circular at module-import time

    if not player.is_tier_unlocked(mission.tier):
        return False
    # Manned lunar landing's effective rocket depends on the architecture the
    # player will commit to, so keep it visible once Tier 3 unlocks even if
    # neither candidate rocket is built yet. The status column explains the
    # remaining gap.
    if mission.id == MissionId.MANNED_LUNAR_LANDING:
        return True
    return player.rocket_built(mission.rocket)


def visible_missions(player: Player) -> list[Mission]:
    """Mission catalog filtered to what the player should currently see,
    preserving the canonical MISSIONS order."""
    from baris.state import MISSIONS
    return [m for m in MISSIONS if visible_to(player, m)]


# ----------------------------------------------------------------------
# Phase I — seasonal news system
# ----------------------------------------------------------------------
# Each entry in _NEWS_POOL is (event_id, weight, apply_fn). apply_fn takes
# (state, rng) and returns the headline to record. apply_fn may return "" to
# decline (e.g., defector event with no trailing player); the roller will
# try again with a different event.

NEWS_BUDGET_WINDFALL_DELTA    = 5
NEWS_BUDGET_CUT_DELTA         = 3
NEWS_PRESS_TOUR_PRESTIGE      = 2
NEWS_DEFECTOR_PRESTIGE        = 3
NEWS_RELIABILITY_DELTA        = 5
NEWS_MOOD_BOOST               = 10
NEWS_SCANDAL_PRESTIGE_PENALTY = 2


def _leader(state: GameState) -> Player | None:
    """Player with the highest prestige; ties broken by most successes."""
    if not state.players:
        return None
    return max(
        state.players,
        key=lambda p: (p.prestige, sum(p.mission_successes.values())),
    )


def _trailing(state: GameState) -> Player | None:
    """Player with the lowest prestige; ties broken by fewest successes.
    Returns None if both players are tied exactly (nothing to boost)."""
    if len(state.players) < 2:
        return None
    ranked = sorted(
        state.players,
        key=lambda p: (p.prestige, sum(p.mission_successes.values())),
    )
    if (ranked[0].prestige == ranked[-1].prestige
            and sum(ranked[0].mission_successes.values())
            == sum(ranked[-1].mission_successes.values())):
        return None
    return ranked[0]


def _side_label(player: Player | None) -> str:
    if player is None or player.side is None:
        return "?"
    return player.side.value


def _news_budget_windfall(state: GameState, _rng: random.Random) -> str:
    for p in state.players:
        p.budget += NEWS_BUDGET_WINDFALL_DELTA
    return f"Space-budget appropriation: both sides +{NEWS_BUDGET_WINDFALL_DELTA} MB."


def _news_budget_cut(state: GameState, _rng: random.Random) -> str:
    for p in state.players:
        p.budget = max(0, p.budget - NEWS_BUDGET_CUT_DELTA)
    return f"Congressional review trims spending: both sides -{NEWS_BUDGET_CUT_DELTA} MB."


def _news_press_tour(state: GameState, _rng: random.Random) -> str:
    leader = _leader(state)
    if leader is None:
        return ""
    leader.prestige += NEWS_PRESS_TOUR_PRESTIGE
    return (
        f"{_side_label(leader)} press tour captures the world's imagination "
        f"— +{NEWS_PRESS_TOUR_PRESTIGE} prestige."
    )


def _news_defector(state: GameState, _rng: random.Random) -> str:
    target = _trailing(state)
    if target is None:
        return ""
    target.prestige += NEWS_DEFECTOR_PRESTIGE
    return (
        f"High-profile defector arrives in {_side_label(target)} "
        f"— +{NEWS_DEFECTOR_PRESTIGE} prestige."
    )


def _news_reliability_breakthrough(state: GameState, rng: random.Random) -> str:
    """Pick a random side and a random built rocket on their side; bump it.
    Skips if nobody has a rocket at MIN_RELIABILITY_TO_LAUNCH."""
    candidates: list[tuple[Player, Rocket]] = []
    for p in state.players:
        for rocket in Rocket:
            if p.rocket_reliability(rocket) >= MIN_RELIABILITY_TO_LAUNCH:
                candidates.append((p, rocket))
    if not candidates:
        return ""
    player, rocket = rng.choice(candidates)
    _bump_reliability(player, rocket, NEWS_RELIABILITY_DELTA)
    name = rocket_display_name(rocket, player.side)
    return (
        f"{_side_label(player)} engineers crack a thrust-stability issue "
        f"— +{NEWS_RELIABILITY_DELTA} reliability on {name}."
    )


def _news_hardware_recall(state: GameState, rng: random.Random) -> str:
    candidates: list[tuple[Player, Rocket]] = []
    for p in state.players:
        for rocket in Rocket:
            if p.rocket_reliability(rocket) >= MIN_RELIABILITY_TO_LAUNCH:
                candidates.append((p, rocket))
    if not candidates:
        return ""
    player, rocket = rng.choice(candidates)
    _bump_reliability(player, rocket, -NEWS_RELIABILITY_DELTA)
    name = rocket_display_name(rocket, player.side)
    return (
        f"{_side_label(player)} {name} grounded for mandatory inspection "
        f"— -{NEWS_RELIABILITY_DELTA} reliability."
    )


def _news_crew_morale_boost(state: GameState, rng: random.Random) -> str:
    sides_with_active = [p for p in state.players if p.active_astronauts()]
    if not sides_with_active:
        return ""
    player = rng.choice(sides_with_active)
    bumped = 0
    for a in player.active_astronauts():
        a.mood = _clamp_mood(a.mood + NEWS_MOOD_BOOST)
        bumped += 1
    return (
        f"{_side_label(player)} astronauts featured in LIFE magazine — "
        f"+{NEWS_MOOD_BOOST} mood for {bumped} crew."
    )


def _news_scandal(state: GameState, _rng: random.Random) -> str:
    target = _leader(state)
    if target is None:
        return ""
    target.prestige = max(0, target.prestige - NEWS_SCANDAL_PRESTIGE_PENALTY)
    return (
        f"{_side_label(target)} program rocked by scandal "
        f"— -{NEWS_SCANDAL_PRESTIGE_PENALTY} prestige."
    )


def _news_quiet_season(_state: GameState, _rng: random.Random) -> str:
    return "Quiet news cycle — no major headlines this season."


_NEWS_POOL: tuple[tuple[str, int, Any], ...] = (
    ("budget_windfall",          2, _news_budget_windfall),
    ("budget_cut",                2, _news_budget_cut),
    ("press_tour",                2, _news_press_tour),
    ("defector",                  2, _news_defector),
    ("reliability_breakthrough",  2, _news_reliability_breakthrough),
    ("hardware_recall",           2, _news_hardware_recall),
    ("crew_morale_boost",         2, _news_crew_morale_boost),
    ("scandal",                   2, _news_scandal),
    ("quiet_season",              1, _news_quiet_season),
)


# Module-level test hook: when set to False, _roll_season_news becomes a
# no-op. Lets targeted tests (e.g. mood-drop assertions) isolate the
# mechanic they're exercising from random news-card side effects.
_news_enabled: bool = True


# ----------------------------------------------------------------------
# DIRTY TRICKS — sabotage cards (divergence)
# ----------------------------------------------------------------------


def _sabotage_season_stamp(state: GameState) -> str:
    return f"{state.year}-{state.season.value}"


def sabotage_available(
    player: Player, state: GameState, card_id: str,
) -> tuple[bool, str]:
    """Return (can_fire, reason). reason is empty on success."""
    card = get_sabotage_card(card_id)
    if card is None:
        return False, "unknown card"
    if state.phase != Phase.PLAYING:
        return False, "game not in progress"
    if player.budget < card.cost:
        return False, f"need {card.cost} MB"
    if player.sabotage_used_on == _sabotage_season_stamp(state):
        return False, "already used a sabotage this season"
    opponent = state.other_player(player.player_id)
    if opponent is None or opponent.side is None:
        return False, "no opponent"
    return True, ""


def execute_sabotage(
    player: Player, state: GameState, card_id: str,
    rng: random.Random | None = None,
) -> bool:
    """Fire one sabotage card at the opponent. Charges card.cost up
    front; if the per-card effect can't apply (e.g. catapult with no
    scheduled pads), refunds the cost and the season slot stays free
    so the player can try a different card. Always logs a comedic
    headline so the news ticker reflects what happened (or didn't)."""
    ok, _reason = sabotage_available(player, state, card_id)
    if not ok:
        return False
    card = get_sabotage_card(card_id)
    assert card is not None  # validated above
    rng = rng or random.Random()
    opponent = state.other_player(player.player_id)
    assert opponent is not None and opponent.side is not None

    handler = _SABOTAGE_HANDLERS.get(card.card_id)
    if handler is None:
        return False
    player.budget -= card.cost
    player.sabotage_used_on = _sabotage_season_stamp(state)
    fired_headline = handler(player, opponent, state, rng)
    if not fired_headline:
        # Refund + free up the season slot — the card had nothing to
        # bite into, so the player gets a do-over.
        player.budget += card.cost
        player.sabotage_used_on = ""
        state.log.append(
            f"DIRTY TRICKS: {player.username} prepped {card.name} "
            f"but found no target — cost refunded."
        )
        return False
    state.log.append(f"DIRTY TRICKS: {fired_headline}")
    chatter_react(
        state.log, "sabotage_outgoing", rng,
        character=_chatter_character(player, rng),
    )
    chatter_react(
        state.log, "sabotage_incoming", rng,
        character=_chatter_character(opponent, rng),
    )
    return True


# Per-card handlers. Each takes (acting_player, opponent_player, state,
# rng) and returns a comedic headline string on success or "" if the
# card couldn't apply.

def _sab_catapult(
    me: Player, opp: Player, state: GameState, rng: random.Random,
) -> str:
    targets = [p for p in opp.pads
               if p.scheduled_launch is not None and not p.damaged]
    if not targets:
        return ""
    pad = rng.choice(targets)
    pad.repair_turns_remaining = PAD_REPAIR_TURNS
    return (
        f"a flaming goat lands on {opp.side.value if opp.side else '?'}'s "
        f"Pad {pad.pad_id}. Pad damaged, {PAD_REPAIR_TURNS} seasons of "
        "repair needed. The goat is fine."
    )


def _sab_weatherman(
    me: Player, opp: Player, state: GameState, rng: random.Random,
) -> str:
    targets = [p for p in opp.pads if p.scheduled_launch is not None]
    if not targets:
        return ""
    pad = rng.choice(targets)
    sched = pad.scheduled_launch
    assert sched is not None
    new_season, new_year = next_season(
        Season(sched.scheduled_season) if sched.scheduled_season else state.season,
        sched.scheduled_year or state.year,
    )
    sched.scheduled_year = new_year
    sched.scheduled_season = new_season.value
    return (
        f"the {opp.side.value if opp.side else '?'} weatherman invents a "
        f"hurricane. Pad {pad.pad_id} launch slips to "
        f"{new_season.value} {new_year}."
    )


def _sab_mole(
    me: Player, opp: Player, state: GameState, rng: random.Random,
) -> str:
    targets = [r for r in Rocket
               if opp.rocket_reliability(r) >= MIN_RELIABILITY_TO_LAUNCH]
    if not targets:
        return ""
    rocket = rng.choice(targets)
    _bump_reliability(opp, rocket, -SABOTAGE_RELIABILITY_HIT)
    name = rocket_display_name(rocket, opp.side)
    return (
        f"a mole inside {opp.side.value if opp.side else '?'} mission "
        f"control swaps a manual page. {name} loses "
        f"{SABOTAGE_RELIABILITY_HIT} reliability."
    )


def _sab_blueprints(
    me: Player, opp: Player, state: GameState, rng: random.Random,
) -> str:
    targets = [r for r in Rocket
               if opp.rocket_reliability(r) >= MIN_RELIABILITY_TO_LAUNCH]
    if not targets:
        return ""
    rocket = rng.choice(targets)
    _bump_reliability(opp, rocket, -SABOTAGE_RELIABILITY_STEAL_GAIN)
    _bump_reliability(me, rocket, SABOTAGE_RELIABILITY_STEAL_GAIN)
    opp_name = rocket_display_name(rocket, opp.side)
    my_name = rocket_display_name(rocket, me.side)
    return (
        f"{me.side.value if me.side else '?'} engineers 'borrow' "
        f"{opp_name} blueprints. -{SABOTAGE_RELIABILITY_STEAL_GAIN} for "
        f"the opponent, +{SABOTAGE_RELIABILITY_STEAL_GAIN} for {my_name}."
    )


_SABOTAGE_HANDLERS: dict[str, Any] = {
    "catapult":   _sab_catapult,
    "weatherman": _sab_weatherman,
    "mole":       _sab_mole,
    "blueprints": _sab_blueprints,
}


# ----------------------------------------------------------------------
# Phase R — stand tests
# ----------------------------------------------------------------------


def _stand_test_season_stamp(state: GameState) -> str:
    return f"{state.year}-{state.season.value}"


def _is_valid_stand_test_target(target_id: str) -> bool:
    if any(target_id == r.value for r in Rocket):
        return True
    if any(target_id == m.value for m in Module):
        return True
    return False


def stand_test_available(
    player: Player, state: GameState, target_id: str,
) -> tuple[bool, str]:
    """Return (can_test, reason). reason is empty on success."""
    if not _is_valid_stand_test_target(target_id):
        return False, "unknown target"
    if state.phase != Phase.PLAYING:
        return False, "game not in progress"
    if player.budget < STAND_TEST_COST:
        return False, f"need {STAND_TEST_COST} MB"
    last = player.stand_tests_used.get(target_id, "")
    if last == _stand_test_season_stamp(state):
        return False, "already tested this season"
    return True, ""


def request_stand_test(
    player: Player, state: GameState, target_id: str,
) -> bool:
    """Phase R — pay STAND_TEST_COST MB to bump `target_id`'s reliability
    by STAND_TEST_GAIN (clamped at RELIABILITY_CAP). One test per
    (target, season). Returns True on success."""
    ok, _reason = stand_test_available(player, state, target_id)
    if not ok:
        return False
    player.budget -= STAND_TEST_COST
    player.stand_tests_used[target_id] = _stand_test_season_stamp(state)
    current = player.reliability.get(target_id, 0)
    new = min(RELIABILITY_CAP, current + STAND_TEST_GAIN)
    player.reliability[target_id] = new
    state.log.append(
        f"STAND TEST: {player.username} ran a {target_id} stand test "
        f"({current} → {new})."
    )
    return True


def memorial_roll(state: GameState) -> list[tuple[str, str, int, str, str]]:
    """Phase N — flatten mission_history into a per-astronaut memorial
    roster for the Memorial Wall. Returns a list of
    (astronaut_name, mission_name, year, season, side) tuples ordered
    by when each death happened (oldest first). Pure derivation; no
    state mutation. Both clients render directly off this."""
    roll: list[tuple[str, str, int, str, str]] = []
    for entry in state.mission_history:
        for name in entry.deaths:
            roll.append((
                name, entry.mission_name, entry.year,
                entry.season, entry.side,
            ))
    return roll


# Phase S — historical milestone events. Each fires at most once per
# game when (year, season) hits and prerequisites are met. Tone is
# flavour-only; no balance shifts. The id strings are stored in
# state.milestones_fired so each milestone plays exactly once.
_HISTORICAL_MILESTONES: tuple[
    tuple[str, int, str, str], ...
] = (
    ("sputnik_1957", 1957, "Fall",
     "📅 1957: A satellite-shaped object beeps over the rooftops. Nobody is sure whose."),
    ("yuri_1961",    1961, "Spring",
     "📅 1961: A first man in space, and somewhere a barber loses business."),
    ("kennedy_1962", 1962, "Fall",
     "📅 1962: A speech is given. The decade is now on the clock."),
    ("apollo_1_1967", 1967, "Winter",
     "📅 1967: Sombre headlines about a fire on the pad. Both sides go quiet."),
    ("decade_1970",  1970, "Spring",
     "📅 1970: The decade ended without a landing. Pundits revise their forecasts."),
)


def _check_historical_milestones(state: GameState) -> None:
    """Phase S — fire any (year, season)-matching headline that hasn't
    already played. Pure flavour; appends to state.log only."""
    season = state.season.value
    for mid, m_year, m_season, headline in _HISTORICAL_MILESTONES:
        if mid in state.milestones_fired:
            continue
        if state.year == m_year and season == m_season:
            state.milestones_fired.append(mid)
            state.log.append(headline)


def _check_calendar_deadline(state: GameState) -> None:
    """Phase S — when state.year exceeds end_year, end the game with a
    prestige tiebreaker. The current year is still in-bounds; the game
    ends as soon as we'd be advancing PAST it."""
    if state.phase != Phase.PLAYING:
        return
    if state.year <= state.end_year:
        return
    # Past the deadline. Pick the highest-prestige player; tie goes
    # to the side with more total mission successes; then to USA by
    # default if everything is identical.
    if not state.players:
        state.phase = Phase.ENDED
        return
    ranked = sorted(
        state.players,
        key=lambda p: (
            p.prestige,
            sum(p.mission_successes.values()),
            -1 if p.side == Side.USA else 0,
        ),
        reverse=True,
    )
    winner = ranked[0]
    state.phase = Phase.ENDED
    state.winner = winner.side
    side_label = winner.side.value if winner.side else "?"
    state.log.append(
        f"📅 {state.end_year} closes — {winner.username} ({side_label}) "
        f"wins on prestige ({winner.prestige})."
    )


def _run_government_review(
    state: GameState, ended_year: int,
    rng: random.Random | None = None,
) -> None:
    """Phase M — once per game-year, score each player on the year just
    ended. Below REVIEW_PASS_THRESHOLD adds a warning; reach
    REVIEW_FIRE_AT_WARNINGS warnings and the player is dismissed,
    ending the game with the opponent declared winner. Idempotent: a
    player is only reviewed for a given year once, even if the function
    is called twice in a row by accident."""
    if state.phase != Phase.PLAYING:
        return
    rng = rng or random.Random()
    fired_player: Player | None = None
    for player in state.players:
        if fired_player is not None:
            # First dismissal ends the game; don't review anyone else
            # this year. Their next review picks up from the new year.
            break
        if player.last_review_year >= ended_year:
            continue
        player.last_review_year = ended_year
        # Year-start prestige came from the Spring snapshot of `ended_year`.
        year_start_prestige = 0
        for snap in state.prestige_timeline:
            if snap.year == ended_year and snap.season == "Spring":
                if player.side == Side.USA:
                    year_start_prestige = snap.usa_prestige
                elif player.side == Side.USSR:
                    year_start_prestige = snap.ussr_prestige
                break
        prestige_delta = player.prestige - year_start_prestige
        my_side = player.side.value if player.side else ""
        flights = [
            m for m in state.mission_history
            if m.year == ended_year and m.side == my_side
        ]
        successes = sum(1 for m in flights if m.success)
        kia = sum(len(m.deaths) for m in flights)
        score = (
            prestige_delta
            + REVIEW_SUCCESS_BONUS * successes
            - REVIEW_KIA_PENALTY * kia
        )
        side_label = my_side or "?"
        if score < REVIEW_PASS_THRESHOLD:
            player.warnings += 1
            if player.warnings >= REVIEW_FIRE_AT_WARNINGS:
                state.log.append(
                    f"REVIEW {ended_year}: {player.username} ({side_label}) "
                    f"score {score} — DISMISSED. Opponent wins."
                )
                fired_player = player
            else:
                state.log.append(
                    f"REVIEW {ended_year}: {player.username} ({side_label}) "
                    f"score {score} — WARNING "
                    f"({player.warnings}/{REVIEW_FIRE_AT_WARNINGS})."
                )
                chatter_react(
                    state.log, "review_warn", rng,
                    character=_chatter_character(player, rng),
                )
        else:
            state.log.append(
                f"REVIEW {ended_year}: {player.username} ({side_label}) "
                f"score {score} — passed."
            )
            chatter_react(
                state.log, "review_pass", rng,
                character=_chatter_character(player, rng),
            )
    if fired_player is not None:
        opponent = next(
            (p for p in state.players if p.player_id != fired_player.player_id),
            None,
        )
        state.phase = Phase.ENDED
        state.winner = opponent.side if opponent and opponent.side else None


def _snapshot_prestige(state: GameState) -> None:
    """Phase L — record both players' current prestige at the active
    (year, season). Called right after season advance in resolve_turn
    and once at game start to anchor the timeline at t=0."""
    usa = next((p for p in state.players if p.side == Side.USA), None)
    ussr = next((p for p in state.players if p.side == Side.USSR), None)
    state.prestige_timeline.append(PrestigeSnapshot(
        year=state.year,
        season=state.season.value,
        usa_prestige=usa.prestige if usa is not None else 0,
        ussr_prestige=ussr.prestige if ussr is not None else 0,
    ))


def _roll_season_news(state: GameState, rng: random.Random) -> None:
    """Pick a weighted-random event from _NEWS_POOL and apply it. If the
    chosen event's apply_fn declines (returns ""), draw again from the
    remaining pool; fall back to quiet_season if nothing can fire.
    Uses rng.choice on a weight-expanded list so test stubs don't need
    rng.choices()."""
    if not _news_enabled:
        return
    pool = list(_NEWS_POOL)
    while pool:
        weighted = [e for e in pool for _ in range(e[1])]
        picked = rng.choice(weighted)
        headline = picked[2](state, rng)
        if headline:
            state.current_news = headline
            state.current_news_id = picked[0]
            state.log.append(f"NEWS: {headline}")
            return
        pool = [e for e in pool if e[0] != picked[0]]
    # Everything declined — fall back to a quiet-season headline.
    state.current_news = _news_quiet_season(state, rng)
    state.current_news_id = "quiet_season"
    state.log.append(f"NEWS: {state.current_news}")
