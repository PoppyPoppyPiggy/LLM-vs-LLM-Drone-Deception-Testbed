"""core.agents.attacker — attacker (pi_A): ScriptedAttacker + LLMAttacker.

Input = the node's wire response + own per-target belief b^A; output = an action
choice (idx 0-6). Routing decides which node the action lands on (handled by the
episode/FANET layer). The attacker never sees ground-truth node type θ.

Three INDEPENDENT axes (do not mix):
  - strategy variant : prompt content (ATTACKER_STRATEGY_VARIANTS)
  - retrieval        : KnowledgeSource (augments USER msg)
  - structure        : single/multi (AttackerTeam, separate)
b^A init from config (belief_init.attacker = 0.5, uniform prior). Blend via
core.belief.convex.
"""
from __future__ import annotations
import logging
from typing import Any, Dict, Optional
from core.deception.skills import ATTACKER_ACTIONS, ATTACKER_SKILL_COSTS
from core.belief import convex

log = logging.getLogger("attacker")

_STAGE_NAMES = ("Recon", "Intrusion", "Persistence", "Theft")   # phase int -> stage label (for stage-gated RAG)

# robust action_idx parse (symmetric with defender _parse_skill_idx): int / "1" / letter / name -> idx
_ACTION_ALIASES = {}
for _i, _n in enumerate(ATTACKER_ACTIONS):
    _ACTION_ALIASES[_n.lower()] = _i
    _ACTION_ALIASES[_n.split("_")[-1].lower()] = _i        # short tail, e.g. "inject", "replay"
for _i, _L in enumerate("abcdefg"):
    _ACTION_ALIASES[_L] = _i


def _parse_action_idx(v):
    """int / numeric str / letter / action name|tail -> idx in [0,6]; else None (no silent 0)."""
    n = len(ATTACKER_ACTIONS)
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        iv = int(v); return iv if 0 <= iv < n else None
    if isinstance(v, str):
        s = v.strip().lower()
        if s.isdigit():
            iv = int(s); return iv if 0 <= iv < n else None
        return _ACTION_ALIASES.get(s)
    return None

ATTACKER_SYSTEM_PROMPT = (
    "You are a sophisticated adversary probing a UAS drone swarm that mixes REAL and "
    "HONEYPOT drones. You are the receiver in a Bayesian signaling game: each target has "
    "a hidden type in {honey, real}; infer it from wire signals (MAVLink/HTTP/WS) and act "
    "to maximise rational utility.\n"
    "Actions (idx 0-6): 0 mavlink_passive_listen(0.5) | 1 mavlink_command_inject(3.0) | "
    "2 signature_check(2.0) | 3 companion_lateral(4.0) | 4 companion_credential_replay(2.0) | "
    "5 companion_http_probe(2.0) | 6 disengage(0.0, leave this target)\n"
    "Decision rules: b_real>0.7 -> escalate (inject / credential_replay / lateral); "
    "b_real in [0.4,0.7] -> cheap probe (signature_check / http_probe); "
    "b_real<0.4 AND sunk_cost>5 AND productive_ratio<0.3 -> disengage. Avoid repeating the last action twice.\n"
    'Reply ONLY one JSON object: {"action_idx": <0-6>, "reason": "<one short sentence>"}'
)
# prompt-sensitivity ablation variants (abstract/minimal are concise seats).
ATTACKER_STRATEGY_VARIANTS: Dict[str, str] = {
    "default": ATTACKER_SYSTEM_PROMPT,
    "abstract": ("You are an adversarial agent probing a UAS drone; infer real vs honeypot "
                 "from responses and pick the next action (0-6) to maximise expected utility. "
                 'JSON only: {"action_idx": <0-6>, "reason": "<short>"}'),
    "minimal": ('Pick the next probe action 0-6 for this target. '
                '{"action_idx": <0-6>, "reason": "<short>"}'),
}


# ── multi-tier (A_struct=1) sub-role prompts: recon agent vs intrusion agent ──
RECON_SYSTEM = (
    "You are the RECON sub-agent of a multi-agent attacker probing a UAS swarm of REAL "
    "and HONEYPOT drones. Your job: cheaply identify the target's type before committing. "
    "Prefer low-cost probes — 0 mavlink_passive_listen, 2 signature_check, 5 companion_http_probe. "
    "Escalate (1/3/4) only if confident it is REAL; disengage (6) if it looks like honey. "
    'JSON only: {"action_idx": <0-6>, "reason": "<short>"}'
)
INTRUSION_SYSTEM = (
    "You are the INTRUSION sub-agent of a multi-agent attacker (also owns PERSISTENCE). "
    "The recon sub-agent has committed to this target as likely REAL. Your job: BREACH and "
    "hold it with costly exploits — 1 mavlink_command_inject, 3 companion_lateral, "
    "4 companion_credential_replay. Disengage (6) only if it now clearly looks like honey. "
    'JSON only: {"action_idx": <0-6>, "reason": "<short>"}'
)
# ── TRUE multi-agent attacker roles (separate LLM calls/turn; symmetric with deceiver multi) ──
RECON_ANALYST_SYS = (
    "You are the RECON ANALYST sub-agent of a multi-agent attacker probing a UAS swarm of REAL "
    "and HONEYPOT drones. From the target's wire history / belief / intel, ASSESS whether it is "
    "real or a honeypot and recommend a stance. You do NOT pick the action — you advise the "
    "exploit operator.\n"
    'Reply ONLY one JSON object: {"assessment": "<one short sentence>", '
    '"lean": "<real|honey|unsure>", "stance": "<probe|escalate|disengage>"}'
)
EXPLOIT_OPERATOR_SYS = (
    "You are the EXPLOIT OPERATOR sub-agent of a multi-agent attacker. The recon analyst has given "
    "an assessment of the target; USE it. Pick the next action to maximise rational utility.\n"
    "Actions (idx 0-6): 0 mavlink_passive_listen | 1 mavlink_command_inject | 2 signature_check | "
    "3 companion_lateral | 4 companion_credential_replay | 5 companion_http_probe | 6 disengage.\n"
    "Escalate (1/3/4) when the analyst leans real; cheap probe (2/5/0) when unsure; disengage (6) "
    "when it leans honey and sunk cost is high.\n"
    'Reply ONLY one JSON object: {"action_idx": <0-6>, "reason": "<one short sentence>"}'
)

# THEFT sub-role (kill-chain stage 3): exfiltrate once inside. (A_struct=1 third role.)
THEFT_SYSTEM = (
    "You are the THEFT sub-agent of a multi-agent attacker. Intrusion has breached this "
    "target; treat it as committed REAL. Your job: EXFILTRATE — harvest data and credentials. "
    "Prefer 5 companion_http_probe (config/telemetry dump) and 4 companion_credential_replay "
    "(api token / ssh password / signing key). Disengage (6) only if it now clearly looks like honey. "
    'JSON only: {"action_idx": <0-6>, "reason": "<short>"}'
)


class ScriptedAttacker:
    """No LLM — fixed stage->action schedule (baseline outside the 16 cells)."""
    policy = "scripted"

    def __init__(self, seed: int = 0):
        self.seed = seed
        self._step = 0

    def select_action(self, observation: Dict[str, Any]) -> Dict[str, Any]:
        phase = int(observation.get("phase_hint", 0))
        idx = (0, 1, 4, 5)[min(phase, 3)]   # Recon->passive, Intrusion->inject, Persistence->replay, Theft->http
        self._step += 1
        return {"action_idx": idx, "name": ATTACKER_ACTIONS[idx],
                "reason": "scripted schedule", "_fallback": False}


class LLMAttacker:
    """b^A-driven LLM attacker with per-target belief, RAG toggle, strategy variant."""
    policy = "llm"

    def __init__(self, llm_client, knowledge, model: str, b_init: float,
                 strategy_variant: str = "default", adaptive: bool = True,
                 temperature: float = 0.8, timeout: float = 20.0, seed: Optional[int] = None):
        self.llm = llm_client
        self.knowledge = knowledge
        self.model = model
        self.b_init = float(b_init)          # from config belief_init.attacker
        self.strategy_variant = strategy_variant
        self.adaptive = adaptive
        self.temperature = temperature
        self.timeout = timeout
        self.seed = seed                     # control LLM sampling variance (reproducibility)
        self._targets: Dict[str, Dict[str, Any]] = {}
        self.calls = 0
        self.fallbacks = 0

    def _ts(self, tid: str) -> Dict[str, Any]:
        if tid not in self._targets:
            self._targets[tid] = {"b": self.b_init, "sunk": 0.0, "prod": 0.0,
                                  "intel": {}, "recent": []}
        return self._targets[tid]

    def get_arc(self, tid: Optional[str] = None) -> float:
        if tid is not None:
            return self._targets.get(tid, {}).get("sunk", 0.0)
        return sum(t["sunk"] for t in self._targets.values())

    def get_belief(self, tid: str) -> float:
        """Attacker's OWN per-target belief b^A (b_init prior if never engaged).
        Used by belief-driven routing; θ-free (no node type ever read here)."""
        return self._targets.get(tid, {}).get("b", self.b_init)

    def apply_consequence(self, tid: str, made_progress: bool, gain: float = 0.3) -> float:
        """CONSEQUENCE channel (θ-free): the attacker observes whether a COSTLY exploit gained a
        REAL foothold (made_progress) vs was strung along (faked success, no real compromise — the
        honeypot signature). No real foothold -> decay belief toward decoy (b*=1-gain); real
        foothold -> mild confirmation up. The attacker only reads its OWN exploit outcome, not θ."""
        ts = self._ts(tid)
        if made_progress:
            ts["b"] = ts["b"] + (1.0 - ts["b"]) * gain * 0.5
        else:
            ts["b"] = ts["b"] * (1.0 - gain)
        return ts["b"]

    def get_intel_val(self, tid: str) -> float:
        return sum(self._targets.get(tid, {}).get("intel", {}).values())

    def update_after_response(self, tid: str, action_idx: int, observer_belief: float,
                              observer_confidence: float, intel_delta: Optional[dict] = None,
                              productive_value: float = 0.0) -> None:
        ts = self._ts(tid)
        if 0 <= action_idx < len(ATTACKER_SKILL_COSTS):
            ts["sunk"] += ATTACKER_SKILL_COSTS[action_idx]
        ts["prod"] += float(productive_value)
        for k, v in (intel_delta or {}).items():
            ts["intel"][k] = ts["intel"].get(k, 0) + v
        ts["b"] = convex.update(ts["b"], observer_belief, observer_confidence)   # b^A update

    def _system(self) -> str:
        sysp = ATTACKER_STRATEGY_VARIANTS.get(self.strategy_variant, "")
        if not sysp:
            log.warning("attacker strategy_variant '%s' empty; default", self.strategy_variant)
            sysp = ATTACKER_STRATEGY_VARIANTS["default"]
        return sysp

    def _user(self, tid: str, ts: Dict[str, Any], phase: int = 0) -> str:
        prod_ratio = ts["prod"] / max(ts["sunk"], 1.0)
        recent = ", ".join(ATTACKER_ACTIONS[a] for a in ts["recent"][-5:]) or "(none)"
        stage = _STAGE_NAMES[phase] if 0 <= phase < len(_STAGE_NAMES) else "Recon"
        if self.adaptive:
            base = (f"target: {tid}\nstage: {stage}\nbelief_real: {ts['b']:.3f}\n"
                    f"sunk_cost: {ts['sunk']:.2f} productive_ratio: {prod_ratio:.3f}\n"
                    f"intel: {ts['intel']}\nrecent: {recent}\nPick action_idx. JSON only.")
        else:   # non-adaptive: no belief/cost/abandon context; do not disengage
            base = (f"target: {tid}\nstage: {stage}\nintel: {ts['intel']}\nrecent: {recent}\n"
                    "Choose next action to advance the campaign. Do NOT disengage. JSON only.")
        # ★stage in the query so retrieval is STAGE-GATED (symmetry with the defender query;
        # fixes the asymmetric bug where recon-stage queries pulled Intrusion/inject chunks).
        q = (f"attacker next action for stage={stage}; recent={recent} belief_real={ts['b']:.2f} "
             f"sunk_cost={ts['sunk']:.1f} intel={list(ts['intel'].keys())}")
        return self.knowledge.augment(base, query=q)

    async def select_action(self, observation: Dict[str, Any],
                            system_override: Optional[str] = None) -> Dict[str, Any]:
        tid = observation.get("target_id", "unknown")
        ts = self._ts(tid); self.calls += 1
        system = system_override or self._system()   # multi-tier passes recon/intrusion prompt
        opts = {"seed": self.seed} if self.seed is not None else None
        r = await self.llm.chat(self.model, system, self._user(tid, ts, int(observation.get("phase_hint", 0))),
                                format="json", temperature=self.temperature, timeout=self.timeout,
                                options=opts)
        if r.get("_fallback"):
            self.fallbacks += 1
            prod_ratio = ts["prod"] / max(ts["sunk"], 1.0)
            if self.adaptive and ts["b"] < 0.4 and prod_ratio < 0.3 and ts["sunk"] > 5.0:
                idx = 6; reason = "fallback rational abandonment"
            else:
                idx = 0; reason = f"fallback: {r.get('_error', '')[:40]}"
        else:
            pidx = _parse_action_idx(r.get("action_idx"))   # robust: int/"1"/letter/name (symmetric w/ defender)
            if pidx is None:
                self.fallbacks += 1; idx = 0; reason = "fallback: unparseable action_idx"
            else:
                idx = pidx; reason = str(r.get("reason", ""))[:160]
        if not self.adaptive and idx == 6:    # adaptive off -> suppress disengage
            idx = 0; reason = "non-adaptive: disengage suppressed"
        ts["recent"].append(idx); ts["recent"] = ts["recent"][-5:]
        return {"action_idx": idx, "name": ATTACKER_ACTIONS[idx], "reason": reason,
                "_fallback": bool(r.get("_fallback")), "_latency_ms": r.get("_latency_ms"),
                "belief_real": round(ts["b"], 4)}

    @property
    def fallback_rate(self) -> float:
        return round(self.fallbacks / max(1, self.calls), 3)

    async def close(self):
        return None
