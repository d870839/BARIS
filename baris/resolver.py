from __future__ import annotations

import random

from baris.state import (
    GameState,
    Phase,
    Player,
    PRESTIGE_TO_WIN,
    RD_COST_PER_POINT,
    RD_TARGET,
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


def submit_turn(player: Player, rd_spend: int, launch: bool) -> None:
    player.pending_rd_spend = max(0, min(rd_spend, player.budget))
    player.pending_launch = launch and player.rocket_built
    player.turn_submitted = True


def all_turns_in(state: GameState) -> bool:
    return state.phase == Phase.PLAYING and all(p.turn_submitted for p in state.players)


def resolve_turn(state: GameState, rng: random.Random | None = None) -> None:
    """Apply each player's pending actions, advance season, emit log lines."""
    rng = rng or random.Random()
    state.log.clear()

    for player in state.players:
        _apply_rd(player, state)
        if player.pending_launch:
            _resolve_launch(player, state, rng)
        player.pending_rd_spend = 0
        player.pending_launch = False
        player.turn_submitted = False
        # modest seasonal budget refill, keeps the MVP loop going
        player.budget += 10

    _check_victory(state)

    if state.phase == Phase.PLAYING:
        state.season, state.year = next_season(state.season, state.year)
        state.log.append(f"Advancing to {state.season.value} {state.year}.")


def _apply_rd(player: Player, state: GameState) -> None:
    if player.pending_rd_spend <= 0 or player.rocket_built:
        return
    spend = player.pending_rd_spend
    player.budget -= spend
    gained = spend // RD_COST_PER_POINT
    player.rd_progress = min(RD_TARGET, player.rd_progress + gained)
    state.log.append(f"{player.username} invests {spend} MB into R&D (+{gained}%).")
    if player.rd_progress >= RD_TARGET:
        player.rocket_built = True
        state.log.append(f"{player.username} completes rocket R&D!")


def _resolve_launch(player: Player, state: GameState, rng: random.Random) -> None:
    # Sub-orbital unmanned: 75% success, +3 prestige; failure costs 1 prestige.
    roll = rng.random()
    if roll < 0.75:
        player.prestige += 3
        state.log.append(f"{player.username} launches sub-orbital — SUCCESS (+3 prestige).")
    else:
        player.prestige = max(0, player.prestige - 1)
        state.log.append(f"{player.username} launches sub-orbital — FAILURE (-1 prestige).")


def _check_victory(state: GameState) -> None:
    leaders = [p for p in state.players if p.prestige >= PRESTIGE_TO_WIN]
    if not leaders:
        return
    # If both crossed in the same turn, highest prestige wins; ties break to USA (placeholder).
    leaders.sort(key=lambda p: p.prestige, reverse=True)
    winner = leaders[0]
    state.phase = Phase.ENDED
    state.winner = winner.side
    state.log.append(f"{winner.username} ({winner.side.value if winner.side else '?'}) wins the space race!")
