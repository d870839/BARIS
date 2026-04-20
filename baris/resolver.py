from __future__ import annotations

import random

from baris.state import (
    GameState,
    MISSIONS_BY_ID,
    Mission,
    MissionId,
    Phase,
    PRESTIGE_TO_WIN,
    Player,
    RD_TARGETS,
    Rocket,
    SEASON_REFILL,
    Side,
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


def start_game(state: GameState) -> None:
    state.phase = Phase.PLAYING
    state.log.append(f"Game started — {state.season.value} {state.year}.")


def submit_turn(
    player: Player,
    rd_rocket: Rocket | None,
    rd_spend: int,
    launch: MissionId | None,
) -> None:
    player.pending_rd_rocket = rd_rocket.value if rd_rocket else None
    player.pending_rd_spend = max(0, min(rd_spend, player.budget))
    # validate launch: only allow if rocket is built and player can afford launch cost.
    player.pending_launch = None
    if launch is not None:
        mission = MISSIONS_BY_ID[launch]
        if player.rocket_built(mission.rocket) and player.budget >= mission.launch_cost + player.pending_rd_spend:
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
        player.pending_rd_rocket = None
        player.pending_rd_spend = 0
        player.pending_launch = None
        player.turn_submitted = False
        player.budget += SEASON_REFILL

    _check_victory(state)

    if state.phase == Phase.PLAYING:
        state.season, state.year = next_season(state.season, state.year)
        state.log.append(f"Advancing to {state.season.value} {state.year}.")


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
    if new_progress >= target:
        state.log.append(f"{player.username} completes {rocket.value}-class rocket!")


def _resolve_launch(player: Player, state: GameState, rng: random.Random) -> None:
    if not player.pending_launch:
        return
    try:
        mission = MISSIONS_BY_ID[MissionId(player.pending_launch)]
    except (ValueError, KeyError):
        return
    # re-check prereqs — player may have just finished R&D this turn (fine).
    if not player.rocket_built(mission.rocket) or player.budget < mission.launch_cost:
        state.log.append(
            f"{player.username} aborts {mission.name} — prereqs no longer met."
        )
        return

    player.budget -= mission.launch_cost
    roll = rng.random()
    if roll < mission.base_success:
        gain = mission.prestige_success
        bonus = 0
        if mission.id.value not in state.first_completed and player.side is not None:
            state.first_completed[mission.id.value] = player.side.value
            bonus = mission.first_bonus
        player.prestige += gain + bonus
        bonus_txt = f" +{bonus} FIRST!" if bonus else ""
        state.log.append(
            f"{player.username} — {mission.name}: SUCCESS (+{gain}{bonus_txt} prestige)."
        )
        if mission.id == MissionId.LUNAR_LANDING:
            state.phase = Phase.ENDED
            state.winner = player.side
            state.log.append(f"{player.username} lands on the Moon — game over!")
    else:
        player.prestige = max(0, player.prestige - mission.prestige_fail)
        state.log.append(
            f"{player.username} — {mission.name}: FAILURE (-{mission.prestige_fail} prestige)."
        )


def _check_victory(state: GameState) -> None:
    if state.phase == Phase.ENDED:
        return  # already decided by lunar landing
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
    """Missions the player could launch right now (rocket built & can afford)."""
    return [
        m for m in MISSIONS_BY_ID.values()
        if player.rocket_built(m.rocket) and player.budget >= m.launch_cost
    ]
