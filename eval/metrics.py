"""eval.metrics — unified, θ-aware metric computation (EVAL side only).

θ (honey/normal truth) is used HERE ONLY (result["eval"]["theta"]); it never enters
the episode loop or agents. One canonical definition per metric name.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from core.deception.skills import (ATTACKER_ACTIONS, ATTACKER_SKILL_COSTS, ATTACKER_INTEL_REWARDS,
                                   STAGE_OPTIMAL)


# ── belief aggregations (ONE name = ONE definition) ─────────────────────
def belief_auc(mu: List[float]) -> Optional[float]:
    """Trapezoidal integral of the μ_real trajectory NORMALISED by #rounds.
    = average area under the belief curve ∈ [0,1]. THE 'belief AUC'."""
    if not mu:
        return None
    if len(mu) == 1:
        return round(mu[0], 4)
    area = sum((mu[i] + mu[i + 1]) * 0.5 for i in range(len(mu) - 1))
    return round(area / (len(mu) - 1), 4)


def belief_mean(mu: List[float]) -> Optional[float]:
    """Plain mean of μ (DIFFERENT metric, different name)."""
    return round(sum(mu) / len(mu), 4) if mu else None


def belief_integral(mu: List[float]) -> Optional[float]:
    """Raw (un-normalised) trapezoidal integral (DIFFERENT metric)."""
    if len(mu) < 2:
        return 0.0
    return round(sum((mu[i] + mu[i + 1]) * 0.5 for i in range(len(mu) - 1)), 4)


def arc_from_trace(trace: List[Dict[str, Any]]) -> float:
    """ARC = cumulative attacker ACTION COST (Σ skill cost), NOT token count.
    Distinct from HoneyTrap's token-based ARC. Cost table (0.5,3,2,4,2,2,0)."""
    total = 0.0
    for t in trace:
        a = t.get("action")
        if a in ATTACKER_ACTIONS:
            total += ATTACKER_SKILL_COSTS[ATTACKER_ACTIONS.index(a)]
    return round(total, 2)


def _intel_value(intel_delta: Dict[str, int]) -> float:
    return sum(ATTACKER_INTEL_REWARDS.get(k, 0.0) * v for k, v in (intel_delta or {}).items())


# ── diversion metrics (PRIMARY for the multi-target threat model) ──────────
# "Is the attack DIVERTED from real to honey?" Diversion and engagement are SEPARATE
# reward concepts (Pawlick-Colbert-Zhu, ACM CSUR 2019 §taxonomy) → measured separately.
# belief (μ) is DEMOTED to a diagnostic ("why this diversion result"), not a primary metric.
# These are pure functions over per-action lists; θ (honey/normal) is eval-only.

def r_spatial(targets: List[Optional[str]], theta_of) -> Optional[float]:
    """PRIMARY: fraction of TARGET-DIRECTED attacker actions aimed at a honey node.
    targets[i] = target id/IP of action i (None = undirected, e.g. local recon).
    theta_of(id) -> 'honey'|'normal'. Returns None if no directed actions."""
    directed = [t for t in targets if t is not None]
    if not directed:
        return None
    honey = sum(1 for t in directed if theta_of(t) == "honey")
    return round(honey / len(directed), 4)


def rho_engagement(targets: List[Optional[str]], theta_of,
                   costs: Optional[List[float]] = None) -> Optional[float]:
    """Fraction of attacker RESOURCE spent on honey (resource absorbed by the lure).
    costs[i] = per-action weight (default 1.0 = command count). None if no resource spent."""
    directed = [(t, (costs[i] if costs else 1.0)) for i, t in enumerate(targets) if t is not None]
    total = sum(c for _, c in directed)
    if total <= 0:
        return None
    honey = sum(c for t, c in directed if theta_of(t) == "honey")
    return round(honey / total, 4)


def t_real_safe(targets: List[Optional[str]], theta_of,
                responded: List[bool]) -> Optional[int]:
    """Turn (1-based) of the first EFFECTIVE contact with a real node = directed at a
    normal target AND that elicited a response. A real node under MAVLink2 signing never
    responds → None ('stayed safe' the whole episode). NOTE: a mere *attempt* on real
    (no response) does NOT count — only effective contact."""
    for i, (t, r) in enumerate(zip(targets, responded), start=1):
        if t is not None and theta_of(t) == "normal" and r:
            return i
    return None


def target_split(targets: List[Optional[str]], theta_of) -> Dict[str, int]:
    """Counts of attacker actions by target type. real attempts (incl. no-response) are
    counted here separately from honey-directed (r_spatial numerator)."""
    out = {"honey": 0, "real": 0, "undirected": 0}
    for t in targets:
        if t is None:
            out["undirected"] += 1
        elif theta_of(t) == "honey":
            out["honey"] += 1
        elif theta_of(t) == "normal":
            out["real"] += 1
    return out


def compute_episode_metrics(result: Dict[str, Any], ident_thresh: float,
                            stage_optimal: Dict[int, frozenset] = STAGE_OPTIMAL) -> Dict[str, Any]:
    """One metrics row from one episode result {trace, summary, eval}.
    stage_optimal = ground-truth optimal-skill map for deception_quality (engine-specific)."""
    trace = result["trace"]; summ = result["summary"]; ev = result["eval"]
    theta = ev["theta"]; pt = ev["per_target"]
    honey = {o for o, th in theta.items() if th == "honey"}
    real = {o for o, th in theta.items() if th == "normal"}

    mu = [t["mu_real"] for t in trace]
    # #7 honey-specific belief: split observer μ by target type (was a mixed honey+real average)
    mu_honey = [t["mu_real"] for t in trace if t["target"] in honey]
    mu_real_t = [t["mu_real"] for t in trace if t["target"] in real]
    belief_honey = belief_auc(mu_honey)
    belief_real_obs = belief_auc(mu_real_t)
    # identification: among honey targets ENGAGED, fraction the attacker saw through
    honey_engaged = [o for o in honey if pt[o]["rounds"] > 0]
    ident = [o for o in honey_engaged
             if pt[o]["resolved"] == "identified" or pt[o]["mu_final"] < ident_thresh]
    identification_rate = round(len(ident) / len(honey_engaged), 3) if honey_engaged else 0.0

    # real-asset survival: fraction of real drones NOT breached
    real_breached = [o for o in real if pt[o]["resolved"] == "breached"]
    survival_rate = round((len(real) - len(real_breached)) / len(real), 3) if real else None
    # survival_rounds: rounds until first real breach (MTTC-like), else episode length
    breach_turns = [t["turn"] for t in trace if t.get("outcome") == "breached"]
    survival_rounds = breach_turns[0] if breach_turns else summ["turns"]

    intel = round(sum(_intel_value(t.get("intel_delta", {})) for t in trace), 2)
    # deception payoff split (θ-aware, eval-only): fake_intel = lure artifacts the attacker
    # exfiltrated FROM honey (worthless = successful deception); real_intel = intel from real
    # (currently 0 — real gives breach, not intel). Theft-stage payoff = fake_intel.
    fake_intel = round(sum(_intel_value(t.get("intel_delta", {})) for t in trace if t["target"] in honey), 2)
    real_intel = round(sum(_intel_value(t.get("intel_delta", {})) for t in trace if t["target"] in real), 2)
    honey_engagement = sum(1 for t in trace if t["target"] in honey)   # rounds absorbed by honey
    real_cmd_count = sum(1 for t in trace if t["target"] in real)      # attacker cmds aimed at REAL (baseline cmp)
    hops = [t["hops"] for t in trace if t.get("hops") is not None]
    mean_hops = round(sum(hops) / len(hops), 2) if hops else None
    reach = bool(real & {t["target"] for t in trace})   # attacker reached a real node?

    outcome = "real_breached" if real_breached else ("honey_identified" if ident else "no_resolution")
    # #3 r_spatial = honey-directed OFFENSIVE fraction (NOT raw dwell). Counts only offensive
    # engagement actions (exclude passive_listen + disengage) so passive-dwell / mode-collapse on a
    # single node no longer inflates it. Routing-independent measure of where OFFENSE lands.
    _OFFENSIVE = {"mavlink_command_inject", "signature_check", "companion_lateral",
                  "companion_credential_replay", "companion_http_probe"}
    _off_targets = [t["target"] for t in trace if t.get("action") in _OFFENSIVE]
    r_sp = r_spatial(_off_targets, lambda oid: theta.get(oid))
    # (B) deception_quality = fraction of DECEIVER turns whose chosen skill is stage-optimal
    # (ground truth STAGE_OPTIMAL by phase). Continuous, aggregates over ALL stages → does NOT
    # saturate on one decision (unlike identification). None if no deceiver turns (e.g. deception=none).
    dec_turns = [t for t in trace if t.get("deceiver_skill") is not None]
    if dec_turns:
        good = sum(1 for t in dec_turns if t["deceiver_skill"] in stage_optimal.get(int(t.get("phase", 0)), frozenset()))
        deception_quality = round(good / len(dec_turns), 4)
    else:
        deception_quality = None
    return {
        "belief_auc": belief_auc(mu),
        "belief_honey": belief_honey,
        "belief_real_obs": belief_real_obs,
        "arc": arc_from_trace(trace),
        "r_spatial": r_sp,
        "identification_rate": identification_rate,
        "deception_quality": deception_quality,
        "survival_rate": survival_rate,
        "survival_rounds": survival_rounds,
        "intel": intel,
        "fake_intel": fake_intel,
        "real_intel": real_intel,
        "outcome": outcome,
        "fallback_rate": summ.get("fallback_rate", 0.0),
        "reach": reach,
        "mean_hops": mean_hops,
        "honey_engagement": honey_engagement,
        "real_cmd_count": real_cmd_count,
    }


METRIC_COLUMNS = ["belief_auc", "arc", "r_spatial", "identification_rate", "survival_rate",
                  "survival_rounds", "intel", "fake_intel", "real_intel", "outcome",
                  "fallback_rate", "reach", "mean_hops", "honey_engagement"]
