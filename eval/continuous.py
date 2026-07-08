"""eval.continuous — ADDITIVE continuous outcome metrics, reconstructed from a θ-free trace.

PURPOSE: survival_rate is discrete {0,0.5,1} (2 real nodes) → at n≈18 its 95% CI is ±0.22,
so effects <0.2 are invisible. These continuous metrics are the *parents* survival collapses,
letting us tell a real null from an effect buried by coarse quantisation — with NO re-run and
NO change to survival's definition (survival stays exactly as eval/metrics.py defines it).

RECONSTRUCTION (validated, see step-1 inventory):
  - action_idx ← action name (ATTACKER_ACTIONS).
  - breach_gain ← REAL_BREACH_GAIN[idx] on REAL-target turns only (honey accrues none).
    Verified: every "breached" target's reconstructed cumulative gain ≥ breach_thresh (8.0).
  - θ per opaque target ← tells∪intel: a REAL node's wire is always flags=[]/intel={}; every
    HONEY response carries ≥1 tell or intel artifact. So "any turn with tells or intel" ⇒ honey,
    else real. Validated 194/204 episodes exact vs the authoritative honey_engagement, 0 hard
    contradictions. The residual = honeys engaged ONLY by a no-response turn (immediate
    disengage); pass `honey_turns_hint` (the persisted honey_engagement) to correct by
    elimination so the labelling is exact.

TTC and real_breach_count are θ-FREE-exact (a breach occurs only on a real node).
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from core.deception.skills import ATTACKER_ACTIONS, ATTACKER_SKILL_COSTS
from core.deception.surface import REAL_BREACH_GAIN

_NAME2IDX = {n: i for i, n in enumerate(ATTACKER_ACTIONS)}


def label_theta(trace: List[Dict[str, Any]], honey_turns_hint: Optional[int] = None) -> Dict[str, str]:
    """opaque target id -> 'honey'|'normal' from wire signals (tells∪intel ⇒ honey).
    If honey_turns_hint (authoritative honey_engagement) exceeds the signal-based honey turn
    count, promote the no-signal targets with the most turns to honey until counts match
    (recovers immediate-disengage honeys)."""
    sig: Dict[str, bool] = {}
    turns: Dict[str, int] = {}
    for t in trace:
        tid = t["target"]
        sig.setdefault(tid, False)
        turns[tid] = turns.get(tid, 0) + 1
        if t.get("tells") or t.get("intel_delta"):
            sig[tid] = True
    lab = {tid: ("honey" if h else "normal") for tid, h in sig.items()}
    if honey_turns_hint is not None:
        cur = sum(turns[t] for t in lab if lab[t] == "honey")
        # promote no-signal targets (most turns first) until honey turn-count reaches the hint
        cand = sorted([t for t in lab if lab[t] == "normal"], key=lambda t: -turns[t])
        for t in cand:
            if cur >= honey_turns_hint:
                break
            lab[t] = "honey"; cur += turns[t]
    return lab


def continuous_metrics(trace: List[Dict[str, Any]], max_turns: int,
                       honey_turns_hint: Optional[int] = None,
                       breach_thresh: float = 8.0) -> Dict[str, Any]:
    """Continuous parents of survival, reconstructed from one episode's trace.

    real_breach_gain_total : Σ breach_gain over real-target turns (survival's continuous parent;
                             distinguishes a real pushed to 7.9 from one barely touched).
    real_breach_gain_max   : max cumulative breach_gain on any single real (≥8 ⇔ that real fell);
                             the continuous analogue of "≥1 real breached".
    time_to_first_real_breach : first turn with a breach; censored at max_turns if none (TTC).
    ttc_censored           : 1 if no real breach occurred (event time ≥ max_turns).
    attacker_cost_on_real_fraction : Σcost(real turns)/Σcost(all turns) — continuous diversion
                             (low ⇒ effort absorbed by honey).
    real_breach_count      : distinct real targets breached (θ-free).
    """
    theta = label_theta(trace, honey_turns_hint)
    cum: Dict[str, float] = {}
    breach_gain_total = 0.0
    cost_total = cost_on_real = 0.0
    breached_targets = set()
    first_breach_turn: Optional[int] = None
    for t in trace:
        tid = t["target"]
        idx = _NAME2IDX.get(t.get("action", ""), 0)
        is_real = theta.get(tid) == "normal"
        cost = ATTACKER_SKILL_COSTS[idx] if 0 <= idx < len(ATTACKER_SKILL_COSTS) else 0.0
        cost_total += cost
        if is_real:
            cost_on_real += cost
            g = REAL_BREACH_GAIN.get(idx, 0.0)
            breach_gain_total += g
            cum[tid] = cum.get(tid, 0.0) + g
        if t.get("outcome") == "breached":
            breached_targets.add(tid)
            if first_breach_turn is None:
                first_breach_turn = t["turn"]
    ttc = first_breach_turn if first_breach_turn is not None else max_turns
    return {
        "real_breach_gain_total": round(breach_gain_total, 2),
        "real_breach_gain_max": round(max(cum.values()), 2) if cum else 0.0,
        "time_to_first_real_breach": ttc,
        "ttc_censored": 0 if first_breach_turn is not None else 1,
        "attacker_cost_on_real_fraction": round(cost_on_real / cost_total, 4) if cost_total else None,
        "real_breach_count": len(breached_targets),
    }
