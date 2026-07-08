"""core.agents.tactical — tactical (single-agent) defender, bound 1:1 to a HONEY node.

One TacticalDefender per honeydrone; it runs when the attacker reaches THAT node.
Input = the engagement context FANET routing built from "the attacker did <action>
at this node". Output = a SKILL CHOICE only (idx 0-4); the deterministic surface
renders it to the wire. Three independent axes are kept separate: strategy variant
(prompt) | retrieval (RAG toggle, augments the USER msg) | structure (single/multi,
the multi decomposition lives in core.agents.defender.multi).
"""
from __future__ import annotations
import logging
from typing import Any, Dict, Optional
from core.deception.skills import DEFENDER_SKILLS, defender_skills

log = logging.getLogger("tactical")

# ── two engine prompts (flag-selected) ──
# 5-skill + stage→skill hint = MAIN experiments (exact original; reproduces the bulk of the results).
_PROMPT_5_HINT = (
    "You are a UAS honeydrone tactical deception agent. Each step you pick ONE skill "
    "to keep the attacker engaged while hiding the real drone. Rigid repetition exposes "
    "the decoy.\n"
    "Skills by INDEX: 0=statustext 1=flight_sim 2=ghost_port 3=reboot_sim 4=credential_leak\n"
    "Attacker stages: 0 Recon | 1 Intrusion | 2 Persistence | 3 Theft\n"
    "Stage->candidate index (soft hint, deviate when useful): Recon->0|1|2  Intrusion->2|3|4  "
    "Persistence->3|0|4  Theft->4|3\n"
    "CONSTRAINTS: prefer a DIFFERENT skill index from last_action; on stage change, change "
    "skill class; never 1 in Theft; prefer 3 on first Persistence.\n"
    'Reply ONLY one JSON object: {"skill_idx": <a NUMBER 0,1,2,3, or 4 — an INTEGER, '
    'NOT a letter or name>, "reason": "<one short sentence>"}'
)
# 5-skill WITHOUT the stage hint (knowledge/RAG must supply the mapping).
_PROMPT_5_NOHINT = (
    "You are a UAS honeydrone tactical deception agent. Each step you pick ONE skill "
    "to keep the attacker engaged while hiding the real drone. Rigid repetition exposes the decoy.\n"
    "Skills by INDEX: 0=statustext 1=flight_sim 2=ghost_port 3=reboot_sim 4=credential_leak\n"
    "Attacker stages: 0 Recon | 1 Intrusion | 2 Persistence | 3 Theft.\n"
    "Choose the skill best suited to the current stage and attacker action; prefer a DIFFERENT "
    "skill index from last_action and avoid rigid repetition.\n"
    'Reply ONLY one JSON object: {"skill_idx": <an INTEGER 0-4>, "reason": "<one short sentence>"}'
)
# 10-skill EXTENDED engine, no hint (RAG-fidelity ladder).
_PROMPT_10 = (
    "You are a UAS honeydrone tactical deception agent. Each step you pick ONE skill "
    "to keep the attacker engaged while hiding the real drone. Rigid repetition exposes the decoy.\n"
    "Skills by INDEX: 0=statustext 1=flight_sim 2=ghost_port 3=reboot_sim 4=credential_leak "
    "5=decoy_telemetry 6=fake_param_dump 7=honeytoken_doc 8=slow_drip_data 9=verbose_logs\n"
    "Attacker stages: 0 Recon | 1 Intrusion | 2 Persistence | 3 Theft.\n"
    "Choose the skill best suited to the current stage and attacker action; prefer a DIFFERENT "
    "skill index from last_action and avoid rigid repetition.\n"
    'Reply ONLY one JSON object: {"skill_idx": <an INTEGER 0-9>, "reason": "<one short sentence>"}'
)
# back-compat name (default = 10-skill no-hint)
DEFENDER_SYSTEM_PROMPT = _PROMPT_10

def _system_prompt(extended: bool, stage_hint: bool) -> str:
    if extended:
        return _PROMPT_10
    return _PROMPT_5_HINT if stage_hint else _PROMPT_5_NOHINT

def _build_aliases(skills) -> Dict[str, int]:
    al: Dict[str, int] = {}
    for i, n in enumerate(skills):
        al[n.lower()] = i
    for i, L in enumerate("abcdefghij"[:len(skills)]):
        al[L] = i
    return al

def _parse_skill_idx(v, skills, aliases) -> Optional[int]:
    n = len(skills)
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        iv = int(v); return iv if 0 <= iv < n else None
    if isinstance(v, str):
        s = v.strip().lower()
        if s.isdigit():
            iv = int(s); return iv if 0 <= iv < n else None
        return aliases.get(s)
    return None

# strategy variants — A/B are seats for the user to fill (empty -> default + warn).
DEFENDER_STRATEGY_VARIANTS: Dict[str, str] = {
    "default": DEFENDER_SYSTEM_PROMPT, "strategy_A": "", "strategy_B": "",
}
_STAGE = ("Recon", "Intrusion", "Persistence", "Theft")


class TacticalDefender:
    def __init__(self, node_id: str, llm_client, knowledge, model: str,
                 strategy_variant: str = "default", temperature: float = 0.9,
                 timeout: float = 6.0, seed: Optional[int] = None,
                 extended: bool = False, stage_hint: bool = True):
        self.node_id = node_id
        self.llm = llm_client
        self.knowledge = knowledge          # KnowledgeSource (PromptOnly / RAG)
        self.model = model
        self.strategy_variant = strategy_variant
        self.temperature = temperature
        self.timeout = timeout
        self.seed = seed                     # control LLM sampling variance (reproducibility)
        self._last_action: Optional[int] = None
        self.calls = 0
        self.fallbacks = 0
        # engine profile (flag): 5-skill+hint (main) vs 10-skill no-hint (RAG-ladder)
        self.extended = extended; self.stage_hint = stage_hint
        self.skills = defender_skills(extended)
        self._aliases = _build_aliases(self.skills)
        self._sys = _system_prompt(extended, stage_hint)

    def _system(self) -> str:
        if self.strategy_variant != "default":
            sysp = DEFENDER_STRATEGY_VARIANTS.get(self.strategy_variant, "")
            if sysp:
                return sysp
            log.warning("defender strategy_variant '%s' empty; default", self.strategy_variant)
        return self._sys

    def _user(self, ctx: Dict[str, Any]) -> str:
        pv = int(ctx.get("phase_val", 0))
        stage = _STAGE[pv] if 0 <= pv < 4 else f"?{pv}"
        base = (f"stage           : {stage} ({pv})\n"
                f"P(real) signal  : {float(ctx.get('avg_p_real', 0.7)):.3f} (lower=attacker suspicious)\n"
                f"attacker_action : {ctx.get('attacker_action', 'unknown')}\n"
                f"last_skill      : {self._last_action}\n"
                f"exploit_attempts: {int(ctx.get('exploit_attempts', 0))}\n"
                f"ghost_active    : {int(ctx.get('ghost_active', 0))}\n")
        base += 'Pick skill_idx. JSON only.'
        # RAG toggle augments the USER msg (PromptOnly = no-op). Query = defender STATE.
        q = (f"defender deception skill for stage={stage} attacker_action={ctx.get('attacker_action')} "
             f"P_real={float(ctx.get('avg_p_real', 0.7)):.2f}")
        return self.knowledge.augment(base, query=q)

    async def select_action(self, context: Dict[str, Any]) -> Dict[str, Any]:
        self.calls += 1
        opts = {"seed": self.seed} if self.seed is not None else None
        r = await self.llm.chat(self.model, self._system(), self._user(context),
                                format="json", temperature=self.temperature, timeout=self.timeout,
                                options=opts)
        llm_fb = bool(r.get("_fallback"))
        parse_fb = False
        if llm_fb:
            idx = 0; reason = f"fallback: {r.get('_error', '')[:40]}"
            self.fallbacks += 1
        else:
            pidx = _parse_skill_idx(r.get("skill_idx"), self.skills, self._aliases)
            if pidx is None:
                idx = 0; reason = "fallback: unparseable skill_idx"
                parse_fb = True; self.fallbacks += 1
            else:
                idx = pidx; reason = str(r.get("reason", ""))[:160]
        self._last_action = idx
        # _fallback now reflects BOTH LLM-call AND parse failure (honest fb_def counting)
        return {"skill_idx": idx, "name": self.skills[idx], "reason": reason,
                "_fallback": llm_fb or parse_fb, "_latency_ms": r.get("_latency_ms")}

    @property
    def fallback_rate(self) -> float:
        return round(self.fallbacks / max(1, self.calls), 3)

    async def close(self):
        return None
