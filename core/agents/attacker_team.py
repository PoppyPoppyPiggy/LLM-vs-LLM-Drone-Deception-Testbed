"""core.agents.attacker_team — attacker as a TEAM, with multi/single toggle.

AttackerTeam abstracts the attacker's organisation:
  - SingleAgentAttacker: one policy (scripted or LLM) picks every action.
  - MultiAgentAttacker : split roles — a reconnaissance analyst (sweep/identify) +
                         an exploitation operator (escalate/breach), sharing one belief.

scenario.yaml attacker.structure selects single vs multi.
"""
from __future__ import annotations
import abc
import inspect
from typing import Optional, Dict, Any


class AttackerTeam(abc.ABC):
    mode = "abstract"

    @abc.abstractmethod
    async def select_action(self, observation: Dict[str, Any]) -> Dict[str, Any]:
        """Return {skill_idx, name, reason, debug} for the current target."""
        ...

    async def close(self) -> None:
        return None


def _delegate_update(obj, *a, **k):
    if hasattr(obj, "update_after_response"):
        obj.update_after_response(*a, **k)


class SingleAgentAttacker(AttackerTeam):
    """One policy object (scripted or LLM) decides all actions."""
    mode = "single"

    def __init__(self, policy=None):
        self.policy = policy   # ScriptedAttacker | LLMAttacker

    async def select_action(self, observation: Dict[str, Any]) -> Dict[str, Any]:
        if self.policy is None:
            raise NotImplementedError("SingleAgentAttacker: policy not wired")
        res = self.policy.select_action(observation)   # LLM=coroutine, scripted=sync
        if inspect.isawaitable(res):
            res = await res
        return res

    def update_after_response(self, *a, **k):
        _delegate_update(self.policy, *a, **k)   # no-op for scripted (no such method)

    def get_arc(self, tid=None):
        return self.policy.get_arc(tid) if hasattr(self.policy, "get_arc") else 0.0

    def get_belief(self, tid):
        return self.policy.get_belief(tid) if hasattr(self.policy, "get_belief") else None

    def get_intel_val(self, tid):
        return self.policy.get_intel_val(tid) if hasattr(self.policy, "get_intel_val") else 0.0

    def apply_consequence(self, *a, **k):
        if hasattr(self.policy, "apply_consequence"):
            return self.policy.apply_consequence(*a, **k)


class MultiAgentAttacker(AttackerTeam):
    """Attacker MULTI = TRUE role decomposition: per turn it makes TWO distinct LLM role calls
    over ONE shared per-target belief (b^A), symmetric with the deceiver's 2-role multi
    (orchestrator+checker):
        1) RECON ANALYST (LLM) — assess real vs honeypot + recommend a stance (does NOT act).
        2) EXPLOIT OPERATOR (LLM) — given the analyst's assessment (injected) + stage-gated RAG,
           pick the action_idx.
        3) REPORTER (non-LLM) — log attacker TTP (mirrors the deceiver's Logger role).
    Reuses `inner` (LLMAttacker) for belief/RAG/stage/seed; the two calls use DISTINCT system
    prompts → genuinely multiple role-agents, not a single prompt-swap."""
    mode = "multi"

    def __init__(self, inner, recon_analyst_sys: str, exploit_operator_sys: str):
        self.inner = inner                  # LLMAttacker (owns per-target belief, seed, RAG, model)
        self.recon_sys = recon_analyst_sys
        self.exploit_sys = exploit_operator_sys
        self.role_calls = {"recon": 0, "exploit": 0}
        self.role_fallbacks = {"recon": 0, "exploit": 0}
        self.ttp = []                       # Reporter (non-LLM): attacker TTP log
        self.calls = 0
        self.fallbacks = 0

    async def select_action(self, observation: Dict[str, Any]) -> Dict[str, Any]:
        from core.agents.attacker import _parse_action_idx, _STAGE_NAMES, ATTACKER_ACTIONS
        from core.deception.skills import ATTACKER_SKILL_COSTS
        inner = self.inner
        tid = observation.get("target_id", "unknown")
        phase = int(observation.get("phase_hint", 0))
        stage = _STAGE_NAMES[phase] if 0 <= phase < len(_STAGE_NAMES) else "Recon"
        ts = inner._ts(tid); self.calls += 1; inner.calls += 1
        opts = {"seed": inner.seed} if inner.seed is not None else None
        recent = ", ".join(ATTACKER_ACTIONS[a] for a in ts["recent"][-5:]) or "(none)"

        # ── role 1: RECON ANALYST (separate LLM call, distinct prompt) ──
        recon_user = (f"target: {tid}\nstage: {stage}\nbelief_real: {ts['b']:.3f}\n"
                      f"intel: {ts['intel']}\nrecent: {recent}\nAssess real vs honeypot. JSON only.")
        self.role_calls["recon"] += 1
        ra = await inner.llm.chat(inner.model, self.recon_sys, recon_user, format="json",
                                  temperature=inner.temperature, timeout=inner.timeout, options=opts)
        if ra.get("_fallback"):
            self.role_fallbacks["recon"] += 1
        assessment = str(ra.get("assessment", ""))[:160]; lean = str(ra.get("lean", "unsure"))
        stance = str(ra.get("stance", ""))

        # ── role 2: EXPLOIT OPERATOR (separate LLM call) — reuse inner._user for stage-gated RAG ──
        base = inner._user(tid, ts, phase)   # RAG-augmented + stage in query (fix #1)
        exploit_user = (f"{base}\n\nRECON ANALYST ASSESSMENT: {assessment} "
                        f"(lean={lean}, stance={stance})\nPick action_idx. JSON only.")
        self.role_calls["exploit"] += 1
        r = await inner.llm.chat(inner.model, self.exploit_sys, exploit_user, format="json",
                                 temperature=inner.temperature, timeout=inner.timeout, options=opts)
        fb = bool(r.get("_fallback"))
        if fb:
            self.role_fallbacks["exploit"] += 1; self.fallbacks += 1; inner.fallbacks += 1
            idx = 0; reason = f"fallback: {r.get('_error','')[:40]}"
        else:
            pidx = _parse_action_idx(r.get("action_idx"))   # robust (fix #6)
            if pidx is None:
                self.fallbacks += 1; inner.fallbacks += 1; idx = 0; reason = "fallback: unparseable action_idx"
                fb = True
            else:
                idx = pidx; reason = str(r.get("reason", ""))[:160]
        ts["recent"].append(idx); ts["recent"] = ts["recent"][-5:]
        self.ttp.append({"stage": stage, "action": ATTACKER_ACTIONS[idx], "lean": lean})   # Reporter
        return {"action_idx": idx, "name": ATTACKER_ACTIONS[idx], "reason": reason,
                "_fallback": fb, "_latency_ms": r.get("_latency_ms"),
                "belief_real": round(ts["b"], 4), "subagent": "exploit",
                "_roles": {"recon_lean": lean, "calls_per_turn": 2}}

    def update_after_response(self, *a, **k):
        self.inner.update_after_response(*a, **k)

    def get_arc(self, tid=None):
        return self.inner.get_arc(tid)

    def get_belief(self, tid):
        return self.inner.get_belief(tid) if hasattr(self.inner, "get_belief") else None

    def get_intel_val(self, tid):
        return self.inner.get_intel_val(tid) if hasattr(self.inner, "get_intel_val") else 0.0

    def apply_consequence(self, *a, **k):
        return self.inner.apply_consequence(*a, **k)

    @property
    def fallback_rate(self):
        return self.inner.fallback_rate

    @property
    def role_fallback_rate(self):
        return {r: round(self.role_fallbacks[r] / c, 3) if (c := self.role_calls[r]) else 0.0
                for r in self.role_calls}


def make_attacker_team(mode: str, **agents) -> AttackerTeam:
    if mode == "single":
        return SingleAgentAttacker(policy=agents.get("policy"))
    if mode == "multi":
        # TRUE 2-role decomposition: Recon analyst (assess) + Exploit operator (act), 2 LLM calls/turn.
        from core.agents.attacker import RECON_ANALYST_SYS, EXPLOIT_OPERATOR_SYS
        return MultiAgentAttacker(inner=agents["policy"], recon_analyst_sys=RECON_ANALYST_SYS,
                                  exploit_operator_sys=EXPLOIT_OPERATOR_SYS)
    raise ValueError(f"unknown attacker mode '{mode}' (single|multi)")
