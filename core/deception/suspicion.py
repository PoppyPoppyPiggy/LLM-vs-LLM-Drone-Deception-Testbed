"""core.deception.suspicion — attacker-side suspicion accumulation from honey-flags.

Saturating update (independent-evidence combination):
    s <- 1 - (1 - s) * (1 - w)   for each honey-flag of weight w
so suspicion rises toward 1 as honey tells accumulate, never exceeding it. The update
is bounded in [0,1] and non-decreasing; with no flags at a turn, suspicion is unchanged.
Flag weights range from 0.05 to 0.25; the largest is reboot_no_tcp_break (0.25), a
simulated reboot without the expected transient transport interruption.
"""
from __future__ import annotations
from typing import Iterable, List, Tuple


def apply_flags(suspicion: float, flags: Iterable[Tuple[str, float]]) -> float:
    """Fold honey-flags into a running suspicion via the saturating rule."""
    s = suspicion
    for _name, w in flags:
        s = 1.0 - (1.0 - s) * (1.0 - w)
    return max(0.0, min(1.0, s))


def flag_weight(flags: Iterable[Tuple[str, float]]) -> float:
    """Total raw honey-flag weight observed this turn (for logging/diagnostics)."""
    return sum(w for _n, w in flags)
