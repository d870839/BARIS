from __future__ import annotations

import random
import uuid

from baris.state import (
    ADVANCED_TRAINING_COST,
    ADVANCED_TRAINING_SKILL_GAIN,
    ADVANCED_TRAINING_TURNS,
    ARCHITECTURE_COST_DELTA,
    ARCHITECTURE_SUCCESS_DELTA,
    ASSEMBLY_COST_FRACTION,
    LM_POINTS_FROM_MANNED_LUNAR_ORBIT,
    LM_POINTS_FROM_MANNED_ORBITAL,
    LM_POINTS_FROM_MULTI_CREW,
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
    CREW_MAX_BONUS,
    DEATH_CHANCE_ON_FAIL,
    DEATH_PRESTIGE_PENALTY,
    GameState,
    HOSPITAL_CHANCE_ON_FAIL,
    HOSPITAL_STAY_TURNS,
    LaunchReport,
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
    Rocket,
    SEASON_REFILL,
    STARTING_ASTRONAUTS,
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
    from baris.state import HISTORICAL_ROSTERS
    side_code = player.side.value if player.side else "ROS"
    names = HISTORICAL_ROSTERS.get(side_code, ())
    roster: list[Astronaut] = []
    for i in range(STARTING_ASTRONAUTS):
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
        ))
    return roster


def submit_turn(
    player: Player,
    rd_rocket: Rocket | None = None,
    rd_module: Module | None = None,
    rd_spend: int = 0,
    launch: MissionId | None = None,
    objectives: list[ObjectiveId] | None = None,
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
        if player.rocket_built(eff_rocket) and can_afford and crew_ok and tier_ok and arch_ok:
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
        _resolve_scheduled_launch(player, state, rng)
        _promote_pending_to_scheduled(player, state)
        _apply_passive_training(player, rng)
        player.pending_rd_target = None
        player.pending_rd_spend = 0
        player.pending_launch = None
        player.pending_objectives = []
        player.turn_submitted = False
        player.budget += SEASON_REFILL

    _check_victory(state)

    if state.phase == Phase.PLAYING:
        state.season, state.year = next_season(state.season, state.year)
        state.log.append(f"Advancing to {state.season.value} {state.year}.")


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
        crew = _select_crew(player, mission) or []
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
    base = effective_base_success(player, mission)
    recon_bonus, lm_penalty = effective_lunar_modifier(player, mission)
    success_chance = base + crew_bonus + reliability_bonus + recon_bonus - lm_penalty
    report.base_success = base
    report.crew_bonus = crew_bonus
    report.reliability_bonus = reliability_bonus
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
    else:
        _handle_mission_failure(player, mission, crew, state, rng, eff_rocket, report)
        _grant_lunar_progress(player, mission, success=False, state=state)
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


def _crew_bonus(crew: list[Astronaut], mission: Mission) -> float:
    if not mission.manned or mission.primary_skill is None or not crew:
        return 0.0
    avg = sum(a.skill(mission.primary_skill) for a in crew) / len(crew)
    return (avg / 100.0) * CREW_MAX_BONUS


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

    if not mission.manned:
        # Unmanned failures still teach you something — crashed probes feed
        # back into R&D. Reliability creeps up; no budget hit.
        _bump_reliability(player, eff_rocket, UNMANNED_FAILURE_RD_GAIN)
        state.log.append(
            f"{player.username} — {mission.name}: FAILURE "
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
        f"{player.username} — {mission.name}: FAILURE "
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
