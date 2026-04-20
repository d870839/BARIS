from __future__ import annotations

import random
import uuid

from baris.state import (
    ARCHITECTURE_COST_DELTA,
    ARCHITECTURE_SUCCESS_DELTA,
    Architecture,
    Astronaut,
    AstronautStatus,
    CREW_MAX_BONUS,
    DEATH_CHANCE_ON_FAIL,
    DEATH_PRESTIGE_PENALTY,
    GameState,
    MIN_RELIABILITY_TO_LAUNCH,
    MISSIONS_BY_ID,
    Mission,
    MissionId,
    Phase,
    PRESTIGE_TO_WIN,
    Player,
    ProgramTier,
    RD_BATCH_COST,
    RD_SPEED,
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
    player.mission_successes[MissionId.SUBORBITAL.value] = 1
    player.mission_successes[MissionId.MULTI_CREW_ORBITAL.value] = 1
    for a in player.astronauts:
        a.capsule = max(a.capsule, 70)
        a.eva = max(a.eva, 70)
        a.endurance = max(a.endurance, 70)
        a.command = max(a.command, 70)


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
            eva=rng.randint(20, 50),
            endurance=rng.randint(20, 50),
            command=rng.randint(20, 50),
        ))
    return roster


def submit_turn(
    player: Player,
    rd_rocket: Rocket | None,
    rd_spend: int,
    launch: MissionId | None,
) -> None:
    player.pending_rd_rocket = rd_rocket.value if rd_rocket else None
    player.pending_rd_spend = max(0, min(rd_spend, player.budget))
    player.pending_launch = None
    if launch is not None:
        mission = MISSIONS_BY_ID[launch]
        eff_rocket = effective_rocket(player, mission)
        eff_cost = effective_launch_cost(player, mission)
        can_afford = player.budget >= eff_cost + player.pending_rd_spend
        crew_ok = not mission.manned or _select_crew(player, mission) is not None
        tier_ok = player.is_tier_unlocked(mission.tier)
        arch_ok = meets_architecture_prereqs(player, mission)
        if player.rocket_built(eff_rocket) and can_afford and crew_ok and tier_ok and arch_ok:
            player.pending_launch = launch.value
    player.turn_submitted = True


def all_turns_in(state: GameState) -> bool:
    return state.phase == Phase.PLAYING and all(p.turn_submitted for p in state.players)


def resolve_turn(state: GameState, rng: random.Random | None = None) -> None:
    """Apply each player's pending actions, advance season, emit log lines."""
    rng = rng or random.Random()
    state.log.clear()

    for player in state.players:
        _apply_rd(player, state, rng)
        _resolve_launch(player, state, rng)
        _apply_passive_training(player, rng)
        player.pending_rd_rocket = None
        player.pending_rd_spend = 0
        player.pending_launch = None
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
    if player.pending_rd_spend <= 0 or not player.pending_rd_rocket:
        return
    try:
        rocket = Rocket(player.pending_rd_rocket)
    except ValueError:
        return
    current = player.rocket_reliability(rocket)
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
        gain += _roll_rd_batch(rocket, current + gain, rng)
    new_reliability = min(RELIABILITY_CAP, current + gain)
    player.reliability[rocket.value] = new_reliability

    state.log.append(
        f"{player.username} invests {actually_spent} MB into {rocket.value} R&D "
        f"→ reliability {current}% → {new_reliability}%."
    )
    if crossed_threshold and new_reliability >= MIN_RELIABILITY_TO_LAUNCH:
        state.log.append(
            f"{player.username}'s {rocket.value}-class rocket is now launch-ready."
        )


def _roll_rd_batch(rocket: Rocket, current: int, rng: random.Random) -> int:
    """One R&D batch roll: returns a non-negative integer gain in reliability.
    Outcome distribution shaped to mimic BARIS-style variance — most batches
    produce small or no movement; occasional breakthroughs jump the rocket
    forward. Diminishing returns scale gains as reliability approaches the cap.
    """
    speed = RD_SPEED.get(rocket, 1.0)
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


def _resolve_launch(player: Player, state: GameState, rng: random.Random) -> None:
    if not player.pending_launch:
        return
    try:
        mission = MISSIONS_BY_ID[MissionId(player.pending_launch)]
    except (ValueError, KeyError):
        return
    eff_rocket = effective_rocket(player, mission)
    eff_cost = effective_launch_cost(player, mission)
    if not player.rocket_built(eff_rocket) or player.budget < eff_cost:
        state.log.append(
            f"{player.username} aborts {mission.name} — prereqs no longer met."
        )
        return
    if not player.is_tier_unlocked(mission.tier):
        state.log.append(
            f"{player.username} aborts {mission.name} — program not unlocked."
        )
        return
    if not meets_architecture_prereqs(player, mission):
        state.log.append(
            f"{player.username} aborts {mission.name} — architecture prereqs not met."
        )
        return

    crew: list[Astronaut] = []
    if mission.manned:
        crew = _select_crew(player, mission) or []
        if not crew:
            state.log.append(
                f"{player.username} aborts {mission.name} — no available crew."
            )
            return

    player.budget -= eff_cost
    reliability_bonus = (player.rocket_reliability(eff_rocket) - 50) * RELIABILITY_SWING_PER_POINT
    success_chance = (
        effective_base_success(player, mission)
        + _crew_bonus(crew, mission)
        + reliability_bonus
    )
    roll = rng.random()
    if roll < success_chance:
        _bump_reliability(player, eff_rocket, RELIABILITY_GAIN_ON_SUCCESS)
        _handle_mission_success(player, mission, crew, state)
    else:
        _handle_mission_failure(player, mission, crew, state, rng, eff_rocket)


def _bump_reliability(player: Player, rocket: Rocket, delta: int) -> None:
    """Adjust reliability after a flight. Failures can't drop a launch-ready
    rocket below RELIABILITY_FLOOR (so one bad flight doesn't unlaunch you)."""
    current = player.rocket_reliability(rocket)
    new_value = current + delta
    if current >= MIN_RELIABILITY_TO_LAUNCH:
        new_value = max(RELIABILITY_FLOOR, new_value)
    new_value = min(RELIABILITY_CAP, max(0, new_value))
    player.reliability[rocket.value] = new_value


def _next_tier(tier: ProgramTier) -> ProgramTier:
    order = [ProgramTier.ONE, ProgramTier.TWO, ProgramTier.THREE]
    idx = order.index(tier)
    return order[min(idx + 1, len(order) - 1)]


def _select_crew(player: Player, mission: Mission) -> list[Astronaut] | None:
    """Pick the top-skilled active astronauts for this mission, or None if roster can't fill it."""
    if not mission.manned or mission.crew_size == 0:
        return []
    active = player.active_astronauts()
    if len(active) < mission.crew_size:
        return None
    skill_key = mission.primary_skill or Skill.COMMAND
    ranked = sorted(active, key=lambda a: a.skill(skill_key), reverse=True)
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
) -> None:
    gain = mission.prestige_success
    bonus = 0
    if mission.id.value not in state.first_completed and player.side is not None:
        state.first_completed[mission.id.value] = player.side.value
        bonus = mission.first_bonus
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
        state.log.append(f"{player.username} lands astronauts on the Moon — game over!")


def _handle_mission_failure(
    player: Player,
    mission: Mission,
    crew: list[Astronaut],
    state: GameState,
    rng: random.Random,
    eff_rocket: Rocket,
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

    deaths: list[str] = []
    for astro in crew:
        if rng.random() < DEATH_CHANCE_ON_FAIL:
            astro.status = AstronautStatus.KIA.value
            deaths.append(astro.name)
    kia_note = ""
    if deaths:
        player.prestige = max(0, player.prestige - DEATH_PRESTIGE_PENALTY * len(deaths))
        kia_note = (
            f", KIA: {', '.join(deaths)} -{DEATH_PRESTIGE_PENALTY * len(deaths)} prestige"
        )
    state.log.append(
        f"{player.username} — {mission.name}: FAILURE "
        f"(-{mission.prestige_fail} prestige{kia_note}). "
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
