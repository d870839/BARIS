"""Radio chatter — event-driven one-liners that get pumped into the
shared event log so the players have something to read between turns.
Tone is deliberately stupid. Each line is a Python format string with
named placeholders (`{character}`, `{rocket}`, `{phase}`, `{names}`)
that the trigger callsite fills in via kwargs.

Lines are drawn uniformly at random from the per-event pool. A
configurable per-call probability gate (RADIO_CHATTER_CHANCE) keeps
the log from being dominated by chatter when many events fire close
together."""
from __future__ import annotations

import random
from typing import Any

# Probability that a triggered chatter event actually fires a line.
# Low enough that not every launch / KIA / sabotage spawns chatter.
RADIO_CHATTER_CHANCE = 0.65

# Module-level test hook: when False, chatter_react becomes a no-op
# so tests with _SeqRng-style fixed-sequence rngs aren't drained by
# extra rolls. Same pattern as resolver._news_enabled.
_chatter_enabled: bool = True


CHATTER_BANK: dict[str, tuple[str, ...]] = {
    "launch_success": (
        "{character} on comms: 'TRALALA TRALALA SUCCESSO!'",
        "Mission complete. Bombardiro is preparing the next bomb run.",
        "{character} radios: 'cappuccino assassino approves'",
        "Capsule chatter: 'rocket go up, vibe go up'",
        "Glorbo Fruttodrillo high-fives the flight director with a fruit.",
        "{character} releases two confetti goats over the apron.",
        "Trippi Troppi attempts a victory lap. It is mostly sideways.",
    ),
    "launch_failure": (
        "{character}: 'NOOO MIO {rocket}!'",
        "Goat catapult engineers laugh in the background.",
        "Bombardiro Crocodilo bites a clipboard in half.",
        "{character} flips three tables in the canteen.",
        "Lost during {phase}. The crocodile will be missed.",
        "Cappuccino Assassino spills, swears, refills.",
        "Lirili Larila prickles in solidarity.",
    ),
    "kia": (
        "Moment of silence for {names}. They have joined the great pasta in the sky.",
        "{character} placed the helmet on the desk gently.",
        "Trippi Troppi swims a slow lap of respect.",
        "Boneca Ambalabu rattles a single quiet rattle.",
        "Pesto Pestilenziale releases a small basil-cloud in tribute.",
    ),
    "sabotage_outgoing": (
        "{character}: 'an industrial accident, comrade, totally unrelated'",
        "Cappuccino Assassino dusts off his hands.",
        "Bobrito Bandito whistles innocently.",
        "{character} radios: 'we did not do that, however nice job team'",
    ),
    "sabotage_incoming": (
        "'WHO PUT THE GOAT ON THE PAD?' — facility manager, screaming.",
        "Suspicious meteorologist last seen leaving the cafeteria.",
        "{character} smells coffee. Then more coffee. Then ash.",
        "Boneca Ambalabu rattles ominously and points at no one in particular.",
    ),
    "recruit_group": (
        "New cohort reports for duty. They brought snacks.",
        "Recruitment drive successful. The barracks now smell of espresso.",
        "{character} introduces the freshmen with a single dignified honk.",
        "The new recruits are issued helmets, name tags, and one (1) goat.",
    ),
    "review_pass": (
        "'Tutto bene, comrades!' — the committee, audibly tired.",
        "The auditor stamps the form upside down. Approved anyway.",
        "{character}: 'pasta on the table tonight'",
    ),
    "review_warn": (
        "The ministry's eyebrow is raised.",
        "Spaghettino Spaghettoni unspools nervously.",
        "{character} adjusts their tie. They do not own a tie.",
    ),
}


def chatter_react(
    log: list[str],
    event_id: str,
    rng: random.Random,
    *,
    chance: float | None = None,
    **fmt: Any,
) -> None:
    """Maybe append a one-liner to `log`. The line is drawn uniformly
    at random from the pool keyed by `event_id`, formatted with the
    provided kwargs, prefixed with a 📻 so it stands out from regular
    log entries. Returns silently when the event_id is unknown, the
    pool is empty, or the probability roll fails — chatter is
    decoration, never load-bearing."""
    if not _chatter_enabled:
        return
    pool = CHATTER_BANK.get(event_id, ())
    if not pool:
        return
    threshold = chance if chance is not None else RADIO_CHATTER_CHANCE
    if rng.random() > threshold:
        return
    template = rng.choice(pool)
    safe_fmt = {k: v for k, v in fmt.items() if v is not None and v != ""}
    try:
        line = template.format(**safe_fmt)
    except (KeyError, IndexError):
        # Missing kwarg — fall back to a fixed, no-placeholder pick
        # so the log doesn't get a raw "{character}" leak.
        no_placeholder = [t for t in pool if "{" not in t]
        if not no_placeholder:
            return
        line = rng.choice(no_placeholder)
    log.append(f"📻 {line}")
