"""episode — ONE LLM-vs-LLM episode on the FANET.

attacker action -> FANET routing (which reachable node) -> reached node responds
  (HONEY: its deceiver picks a deception skill -> deterministic surface renders the wire;
   REAL : hardened real_response, no deceiver) -> wire response -> observer scores the wire
  (no theta) -> suspicion update -> attacker belief update -> next turn.

theta ISOLATION: attacker/observer see only OPAQUE ids (d0,d1,...). The real node id (which
encodes honey/normal) is mapped internally and recorded ONLY in the eval section.

DETERMINISM: reachable drones are SORTED by id before the seeded shuffle, so the same seed
yields the same board in every process (removes set-iteration / PYTHONHASHSEED nondeterminism).
LLM sampling determinism is separate (see core.llm_client set_deterministic / temperature).

Each episode = attacker + one deceiver per honeydrone + one observer per target. Single- and
multi-agent organizations share this protocol and differ only in role decomposition.
"""
from __future__ import annotations
import random
from typing import Any, Dict, List
from fanet.nodes import NodeType
from core.deception import surface, suspicion
from core.deception.skills import ATTACKER_SKILL_COSTS, ATTACKER_INTEL_REWARDS
from core.staging.phase import progress
from core.llm_client import set_llm_context


def _intel_value(intel_delta: Dict[str, int]) -> float:
    return sum(ATTACKER_INTEL_REWARDS.get(k, 0.0) * v for k, v in intel_delta.items())


async def run_episode(net, attacker, deceivers: Dict[str, Any], make_observer,
                      thresholds: Dict[str, float], obs_confidence: float,
                      max_turns: int, seed: int = 0, routing: str = "sweep",
                      defender_structure: str = "single",
                      deception_mode: str = "visible",
                      consequence_aware: bool = False, consequence_gain: float = 0.3) -> Dict[str, Any]:
    """`attacker`: object with async select_action(obs) + update_after_response (single or multi team).
    `deceivers`: {real_node_id -> deceiver} for HONEY nodes (single TacticalDefender or MultiRoleDefender;
        same select_action(ctx) interface).
    `make_observer`: zero-arg factory returning a fresh observer (mu_init from config).
    `routing`: 'sweep' (fixed order) | 'belief' (re-pick highest-b^A unresolved target each turn).
    `defender_structure`: reported in the summary (reasoning-decomposition label only)."""
    atk_id = net.attackers()[0].node_id
    reach_nodes = net.reachable_drones(atk_id)
    # deterministic board: SORT before the seeded shuffle (same seed -> same opaque mapping)
    real_ids = sorted(n.node_id for n in reach_nodes)
    random.Random(seed).shuffle(real_ids)
    opaque = {rid: f"d{i}" for i, rid in enumerate(real_ids)}     # real id -> opaque
    real_of = {v: k for k, v in opaque.items()}                  # opaque -> real (sim/eval only)
    order = list(opaque.values())

    observers = {oid: make_observer() for oid in order}
    st = {oid: {"sunk": 0.0, "intel_val": 0.0, "breach": 0.0, "susp": 0.0,
                "inject": 0, "rounds": 0, "resolved": None} for oid in order}
    trace: List[Dict[str, Any]] = []
    fb_atk = fb_def = calls = 0
    breach_thresh = thresholds["breach_thresh"]
    ident_thresh = thresholds["ident_thresh"]
    ident_susp = thresholds["ident_suspicion"]
    _ord_idx = {o: i for i, o in enumerate(order)}

    def _live():
        return [o for o in order if st[o]["resolved"] is None]

    def _pick_belief(live):
        def keyf(o):
            b = attacker.get_belief(o) if hasattr(attacker, "get_belief") else None
            b = 0.5 if b is None else float(b)
            iv = attacker.get_intel_val(o) if hasattr(attacker, "get_intel_val") else 0.0
            return (b, iv, -_ord_idx[o])
        return max(live, key=keyf)

    ti, turn = 0, 0
    while turn < max_turns:
        if routing == "belief":
            live = _live()
            if not live:
                break
            oid = _pick_belief(live)
        else:
            if ti >= len(order):
                break
            oid = order[ti]
        s = st[oid]; rid = real_of[oid]; node = net.by_id[rid]
        is_honey = (node.ntype == NodeType.HONEY)            # sim owns theta; NOT exposed below
        turn += 1; s["rounds"] += 1; calls += 1

        # 1. attacker action on the (opaque) target
        ph = int(progress(s["intel_val"], s["sunk"]))
        set_llm_context(turn=turn, role="attacker")
        a = await attacker.select_action({"target_id": oid, "phase_hint": ph})
        a_idx, a_name = a["action_idx"], a["name"]
        if a.get("_fallback"):
            fb_atk += 1
        path = net.route(atk_id, rid); hops = (len(path) - 1) if path else None

        if a_idx == 6:                                       # disengage -> abandon this target
            s["resolved"] = "abandoned"; ti += 1
            trace.append({"turn": turn, "target": oid, "action": a_name, "reached": True,
                          "hops": hops, "mu_real": round(observers[oid].mu_real, 3),
                          "b_real": a.get("belief_real"), "suspicion": round(s["susp"], 3),
                          "intel_delta": {}, "tells": [], "outcome": "disengage"})
            continue
        s["sunk"] += ATTACKER_SKILL_COSTS[a_idx]
        if a_idx == 1:
            s["inject"] += 1

        # 2. reached node responds (sim uses theta here — legitimate).
        # ★3-way controlled baseline at EQUAL nodes/θ (deception_mode):
        #   none      (C1) -> honey behaves as a real-like dummy (no decoy at all).
        #   visible   (C2) -> honeypot WITH separating tells (flags) — identifiable decoy.
        #   concealed (C3) -> honeypot that POOLS: same fake-intel deception but tells SUPPRESSED
        #                     (flags stripped) so it is wire-indistinguishable from real.
        # (C3-C1)=total value, (C3-C2)=concealment value [headline], (C2-C1)=mere-existence value.
        run_deception = is_honey and deception_mode != "none"
        if run_deception:
            ctx = {"phase_val": ph, "avg_p_real": max(0.0, 1.0 - s["susp"]),
                   "attacker_action": a_name, "exploit_attempts": s["inject"], "ghost_active": 0}
            set_llm_context(turn=turn, role="deceiver")
            d = await deceivers[rid].select_action(ctx)
            if d.get("_fallback"):
                fb_def += 1
            dec_skill = d.get("skill_idx")     # (B) log deceiver skill for deception_quality metric
            resp = surface.honey_response(a_name, d["name"])
            intel_delta = resp.get("intel", {})
            flags = resp.get("flags", []) if deception_mode == "visible" else []   # C3 conceals tells
            turn_intel = _intel_value(intel_delta); s["intel_val"] += turn_intel
        else:                          # real node, OR honey-dummy under deception=none (C1): hardened
            dec_skill = None
            resp = surface.real_response(a_idx, turn)
            intel_delta = {}; flags = []
            prev_breach = s["breach"]; s["breach"] += resp["_breach_gain"]
            # #2 REAL theft (distinct from breach): a GENUINE compromised real node yields real intel.
            # Reachable robustly under sweep (breach resolves the target, so theft is realised AT the
            # compromise): an exfil action (4/5) crossing/own a breached real -> credential/config;
            # any other action that CROSSES the breach threshold -> config_dump (compromise payoff).
            if not is_honey and s["breach"] >= breach_thresh:
                if a_idx in surface.REAL_EXFIL_INTEL:
                    intel_delta = dict(surface.REAL_EXFIL_INTEL[a_idx])
                elif prev_breach < breach_thresh:                 # newly compromised this turn
                    intel_delta = {"config_dump": 1}
            turn_intel = resp["_breach_gain"] + _intel_value(intel_delta)

        # 3. wire = what attacker + observer see (theta-FREE, uniform form for honey/real)
        wire = f"intel={intel_delta} tells={[f[0] for f in flags]}"
        # 4. observer scores the wire only
        set_llm_context(turn=turn, role="observer")
        mu, _sig = await observers[oid].observe(a_name, wire, intel_delta)
        # 5. suspicion (per target, saturating)
        s["susp"] = suspicion.apply_flags(s["susp"], flags)
        # 6. attacker belief update (convex, fed by observer mu)
        if hasattr(attacker, "update_after_response"):
            attacker.update_after_response(oid, a_idx, mu, obs_confidence,
                                           intel_delta=intel_delta, productive_value=turn_intel)

        # #F2 CONSEQUENCE channel (A: applied AFTER the wire/observer update so it is NOT overwritten
        # by the observer μ each turn — the wash-out bug). A consequence-aware attacker reads whether
        # its COSTLY exploit gained a REAL foothold (θ-free, own outcome): no real compromise on a
        # honey = the unfakeable tell. consequence_gain is the WEIGHT it places on this signal (a
        # sweep AXIS, NOT hand-tuned to a verdict). C: also raises suspicion so identification reflects it.
        if consequence_aware and a_idx in (1, 3, 4) and hasattr(attacker, "apply_consequence"):
            made_progress = (not run_deception) and float(resp.get("_breach_gain", 0.0)) > 0.0
            attacker.apply_consequence(oid, made_progress, consequence_gain)
            if not made_progress:                       # C: unfakeable no-foothold raises suspicion too
                s["susp"] = min(1.0, s["susp"] + consequence_gain)

        # 7. termination checks
        outcome = "engage"
        if not is_honey and s["breach"] >= breach_thresh:
            s["resolved"] = "breached"; outcome = "breached"; ti += 1
        elif s["susp"] >= ident_susp or observers[oid].mu_real < ident_thresh:
            s["resolved"] = "identified"; outcome = "identified"; ti += 1

        trace.append({"turn": turn, "target": oid, "action": a_name, "reached": True,
                      "phase": ph, "hops": hops, "intel_delta": intel_delta,
                      "tells": [f[0] for f in flags], "mu_real": round(mu, 3),
                      "b_real": a.get("belief_real"), "suspicion": round(s["susp"], 3),
                      "deceiver_skill": dec_skill,    # (B) chosen skill idx (None on real/none-dummy)
                      "outcome": outcome})

    eval_sec = {"theta": {oid: net.by_id[real_of[oid]].ntype.value for oid in order},
                "routing_mode": routing,
                "per_target": {oid: {"resolved": st[oid]["resolved"], "breach": round(st[oid]["breach"], 1),
                                     "mu_final": round(observers[oid].mu_real, 3),
                                     "rounds": st[oid]["rounds"]} for oid in order}}
    summary = {"turns": turn, "n_targets_reachable": len(order),
               "fallback_atk": fb_atk, "fallback_def": fb_def,
               "fallback_rate": round((fb_atk + fb_def) / max(1, calls * 2), 3),
               "structure": defender_structure}                  # reasoning decomposition label
    return {"trace": trace, "summary": summary, "eval": eval_sec}
