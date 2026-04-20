from __future__ import annotations

import random
import uuid

from baris.state import (
    Astronaut,
    AstronautStatus,
    CREW_MAX_BONUS,
    DEATH_CHANCE_ON_FAIL,
    DEATH_PRESTIGE_PENALTY,
    GameState,
    MISSIONS_BY_ID,
    Mission,
    MissionId,
    Phase,
    PRESTIGE_TO_WIN,
    Player,
    RD_TARGETS,
    Rocket,
    SAFETY_CAP,
    SAFETY_FLOOR,
    SAFETY_GAIN_ON_SUCCESS,
    SAFETY_LOSS_ON_FAIL,
    SAFETY_ON_RD_COMPLETE,
    SAFETY_SWING_PER_POINT,
    SEASON_REFILL,
    STARTING_ASTRONAUTS,
    Side,
    Skill,
    next_season,
)


def can_start(state: GameState) -> bool:
    if state.phase != Phase.LOBBY:
        return False
    if len(state.players) != 2:
        return False
    sides = {p.side for p in state.players}
    if None in sides or sides != {Side.USA, Side.USSR}:
        return False
    return all(p.ready for p in state.players)


def start_game(state: GameState, rng: random.Random | None = None) -> None:
    rng = rng or random.Random()
    state.phase = Phase.PLAYING
    for player in state.players:
        if not player.astronauts:
            player.astronauts = _generate_starting_roster(player, rng)
    state.log.append(f"Game started — {state.season.value} {state.year}.")


def _generate_starting_roster(player: Player, rng: random.Random) -> list[Astronaut]:
    side_code = player.side.value if player.side else "ROS"
    roster: list[Astronaut] = []
    for i in range(STARTING_ASTRONAUTS):
        roster.append(Astronaut(
            id=uuid.uuid4().hex[:6],
            name=f"{side_code}-{i + 1:02d}",
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
        can_afford = player.budget >= mission.launch_cost + player.pending_rd_spend
        crew_ok = not mission.manned or _select_crew(player, mission) is not None
        if player.rocket_built(mission.rocket) and can_afford and crew_ok:
            player.pending_launch = launch.value
    player.turn_submitted = True


def all_turns_in(state: GameState) -> bool:
    return state.phase == Phase.PLAYING and all(p.turn_submitted for p in state.players)


def resolve_turn(state: GameState, rng: random.Random | None = None) -> None:
    """Apply each player's pending actions, advance season, emit log lines."""
    rng = rng or random.Random()
    state.log.clear()

    for player in state.players:
        _apply_rd(player, state)
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


def _apply_rd(player: Player, state: GameState) -> None:
    if player.pending_rd_spend <= 0 or not player.pending_rd_rocket:
        return
    try:
        rocket = Rocket(player.pending_rd_rocket)
    except ValueError:
        return
    if player.rocket_built(rocket):
        return  # already done, refund nothing, drop spend
    spend = player.pending_rd_spend
    player.budget -= spend
    target = RD_TARGETS[rocket]
    new_progress = min(target, player.rd_progress(rocket) + spend)
    player.rockets[rocket.value] = new_progress
    state.log.append(
        f"{player.username} invests {spend} MB into {rocket.value} R&D "
        f"({new_progress}/{target})."
    )
    if new_progress >= target and player.rocket_safety.get(rocket.value, 0) == 0:
        player.rocket_safety[rocket.value] = SAFETY_ON_RD_COMPLETE
        state.log.append(
            f"{player.username} completes {rocket.value}-class rocket! "
            f"(initial safety: {SAFETY_ON_RD_COMPLETE}%)"
        )


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
    if not player.rocket_built(mission.rocket) or player.budget < mission.launch_cost:
        state.log.append(
            f"{player.username} aborts {mission.name} — prereqs no longer met."
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

    player.budget -= mission.launch_cost
    safety_bonus = (player.safety(mission.rocket) - 50) * SAFETY_SWING_PER_POINT
    success_chance = mission.base_success + _crew_bonus(crew, mission) + safety_bonus
    roll = rng.random()
    if roll < success_chance:
        _bump_safety(player, mission.rocket, SAFETY_GAIN_ON_SUCCESS)
        _handle_mission_success(player, mission, crew, state)
    else:
        _bump_safety(player, mission.rocket, -SAFETY_LOSS_ON_FAIL)
        _handle_mission_failure(player, mission, crew, state, rng)


def _bump_safety(player: Player, rocket: Rocket, delta: int) -> None:
    current = player.safety(rocket)
    new_value = max(SAFETY_FLOOR, min(SAFETY_CAP, current + delta))
    player.rocket_safety[rocket.value] = new_value


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
) -> None:
    player.prestige = max(0, player.prestige - mission.prestige_fail)
    deaths: list[str] = []
    for astro in crew:
        if rng.random() < DEATH_CHANCE_ON_FAIL:
            astro.status = AstronautStatus.KIA.value
            deaths.append(astro.name)
    if deaths:
        player.prestige = max(0, player.prestige - DEATH_PRESTIGE_PENALTY * len(deaths))
        state.log.append(
            f"{player.username} — {mission.name}: FAILURE "
            f"(-{mission.prestige_fail} prestige, KIA: {', '.join(deaths)} "
            f"-{DEATH_PRESTIGE_PENALTY * len(deaths)} prestige)."
        )
    else:
        crew_note = f" [crew survived: {', '.join(a.name for a in crew)}]" if crew else ""
        state.log.append(
            f"{player.username} — {mission.name}: FAILURE "
            f"(-{mission.prestige_fail} prestige){crew_note}."
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
    """Missions the player could launch right now (rocket built, can afford, crew if needed)."""
    result: list[Mission] = []
    for m in MISSIONS_BY_ID.values():
        if not player.rocket_built(m.rocket):
            continue
        if player.budget < m.launch_cost:
            continue
        if m.manned and _select_crew(player, m) is None:
            continue
        result.append(m)
    return result
