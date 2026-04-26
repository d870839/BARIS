"""Test-suite-wide fixtures.

Chatter (radio one-liners that get pumped into the event log) is
disabled by default for the whole test run. The chatter system uses
its own RNG calls, which would drain test-controlled fixed-sequence
RNGs (`_FixedRng` / `_SeqRng` in test_resolver) and break their
deterministic assertions on death rolls / hospital rolls / etc.

Specific tests that want to verify chatter behaviour can flip
`baris.chatter._chatter_enabled = True` for the duration of the
assertion they care about.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _disable_chatter_by_default():
    from baris import chatter
    prev = chatter._chatter_enabled
    chatter._chatter_enabled = False
    try:
        yield
    finally:
        chatter._chatter_enabled = prev
