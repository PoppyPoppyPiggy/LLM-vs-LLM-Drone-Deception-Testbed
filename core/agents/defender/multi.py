"""core.agents.defender.multi — defender MULTI structure (role decomposition).

The defender structure flag changes ONLY the internal reasoning decomposition of a honey
node's per-turn decision; it does NOT change the wire surface, the GCS coordinate-directive,
or the metric interface. MultiRoleDefender exposes the SAME `select_action(ctx)` contract as
the single-path TacticalDefender, so the episode loop is agnostic.

Roles:
  - Orchestrator      : tactic judgment + deception skill selection  → reuses TacticalDefender
                        (so SINGLE and the multi-orchestrator share identical decision logic).
  - ConsistencyChecker: LLM that validates the chosen skill against recent skills / node state
                        (anti-repetition / no-contradiction tell); may REVISE the skill_idx.
  - Logger            : non-LLM — accumulates attacker TTP (action sequence) for later analysis.
  - Persona           : deterministic seat that styles the rationale text. NOTE: the wire
                        response itself stays the deterministic surface (core.deception.surface)
                        to preserve metric comparability — full generative persona is out of
                        Phase-1 scope (documented seat, not a silent no-op).
"""
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional
from core.deception.skills import DEFENDER_SKILLS
from core.agents.tactical import TacticalDefender, _parse_skill_idx, _STAGE

log = logging.getLogger("defender.multi")

CONSISTENCY_SYSTEM = (
    "You are the CONSISTENCY CHECKER for a honeydrone deception swarm. The tactical agent "
    "chose a deception skill. Verify it is CONSISTENT — no contradiction with recent responses, "
    "no rigid repetition (a repeated canned skill is a decoy tell), and physically plausible for "
    "the stage. Skills by INDEX: 0=statustext 1=flight_sim 2=ghost_port 3=reboot_sim 4=credential_leak.\n"
    "If the choice is fine, return it unchanged. If it is a repetition/contradiction tell, pick a "
    "better skill index 0-4.\n"
    'Reply ONLY one JSON object: {"consistent": <true|false>, "skill_idx": <0-4 INTEGER>, '
    '"reason": "<one short sentence>"}'
)


class TTPLogger:
    """Non-LLM role: record attacker TTP (action) per turn for the honey node."""
    def __init__(self) -> None:
        self.ttp: List[str] = []

    def record(self, attacker_action: str) -> None:
        if attacker_action:
            self.ttp.append(attacker_action)


class Persona:
    """Deterministic rationale-styling seat (documented; wire stays the deterministic surface)."""
    @staticmethod
    def style(orchestrator_reason: str, checker_note: str) -> str:
        r = orchestrator_reason or ""
        if checker_note:
            r = f"{r} | check: {checker_note}"
        return r[:200]


class ConsistencyChecker:
    """LLM role: validate / revise the orchestrator's skill. Conservative — defaults to ACCEPT
    on any failure or invalid revision (never destabilises the orchestrator's choice)."""
    def __init__(self, llm_client, model: str, temperature: float = 0.6,
                 timeout: float = 6.0, seed: Optional[int] = None,
                 skills=DEFENDER_SKILLS, aliases=None):
        self.llm = llm_client
        self.model = model
        self.temperature = temperature
        self.timeout = timeout
        self.seed = seed
        self.skills = skills                       # match orchestrator engine (5/10-skill)
        self.aliases = aliases or {}
        self.calls = 0
        self.revisions = 0
        self.fallbacks = 0

    def _user(self, skill_idx: int, ctx: Dict[str, Any], recent: List[int]) -> str:
        pv = int(ctx.get("phase_val", 0))
        stage = _STAGE[pv] if 0 <= pv < 4 else f"?{pv}"
        recent_names = ", ".join(DEFENDER_SKILLS[i] for i in recent[-5:]) or "(none)"
        return (f"stage          : {stage} ({pv})\n"
                f"chosen_skill   : {skill_idx} ({DEFENDER_SKILLS[skill_idx]})\n"
                f"recent_skills  : {recent_names}\n"
                f"attacker_action: {ctx.get('attacker_action', 'unknown')}\n"
                f"exploit_attempts: {int(ctx.get('exploit_attempts', 0))}\n"
                "Is the chosen skill consistent? JSON only.")

    async def check(self, skill_idx: int, ctx: Dict[str, Any], recent: List[int]) -> tuple[int, str]:
        self.calls += 1
        opts = {"seed": self.seed} if self.seed is not None else None
        r = await self.llm.chat(self.model, CONSISTENCY_SYSTEM, self._user(skill_idx, ctx, recent),
                                format="json", temperature=self.temperature, timeout=self.timeout,
                                options=opts)
        if r.get("_fallback"):
            self.fallbacks += 1
            return skill_idx, ""                      # accept orchestrator on failure
        if bool(r.get("consistent", True)):
            return skill_idx, ""                      # checker agrees
        revised = _parse_skill_idx(r.get("skill_idx"), self.skills, self.aliases)
        if revised is None or revised == skill_idx:
            return skill_idx, ""                      # no valid alternative -> accept
        self.revisions += 1
        return revised, f"revised {skill_idx}->{revised}: {str(r.get('reason',''))[:80]}"


class MultiRoleDefender:
    """Defender MULTI: Orchestrator -> ConsistencyChecker -> Logger/Persona. Same select_action
    contract + output keys as TacticalDefender (metric interface preserved)."""
    def __init__(self, node_id: str, llm_client, knowledge, model: str,
                 strategy_variant: str = "default", temperature: float = 0.9,
                 timeout: float = 6.0, seed: Optional[int] = None,
                 checker_model: Optional[str] = None,
                 extended: bool = False, stage_hint: bool = True):
        self.node_id = node_id
        # Orchestrator = the exact single-path tactical agent (shared decision logic).
        self.orchestrator = TacticalDefender(node_id, llm_client, knowledge, model,
                                             strategy_variant=strategy_variant,
                                             temperature=temperature, timeout=timeout, seed=seed,
                                             extended=extended, stage_hint=stage_hint)
        self.checker = ConsistencyChecker(llm_client, checker_model or model,
                                          timeout=timeout, seed=seed,
                                          skills=self.orchestrator.skills, aliases=self.orchestrator._aliases)
        self.logger = TTPLogger()
        self.persona = Persona()
        self._recent: List[int] = []
        self.calls = 0
        self.fallbacks = 0

    async def select_action(self, context: Dict[str, Any]) -> Dict[str, Any]:
        self.calls += 1
        self.logger.record(str(context.get("attacker_action", "")))
        od = await self.orchestrator.select_action(context)
        if od.get("_fallback"):
            self.fallbacks += 1
            self._recent.append(od["skill_idx"]); self._recent = self._recent[-5:]
            return od                                     # skip checker on orchestrator fallback
        idx, note = await self.checker.check(od["skill_idx"], context, self._recent)
        self._recent.append(idx); self._recent = self._recent[-5:]
        return {"skill_idx": idx, "name": DEFENDER_SKILLS[idx],
                "reason": self.persona.style(od.get("reason", ""), note),
                "_fallback": bool(od.get("_fallback")), "_latency_ms": od.get("_latency_ms"),
                "_roles": {"orchestrator_skill": od["skill_idx"], "checker_revised": note != "",
                           "ttp_len": len(self.logger.ttp)}}

    @property
    def fallback_rate(self) -> float:
        return round(self.fallbacks / max(1, self.calls), 3)

    async def close(self):
        return None
