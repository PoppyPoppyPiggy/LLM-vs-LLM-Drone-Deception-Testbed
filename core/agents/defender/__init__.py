"""core.agents.defender — defender structure factory (single | multi).

The structure flag selects ONLY the internal reasoning decomposition of a honey node:
  - single : one LLM does tactic judgment + skill selection  (core.agents.tactical.TacticalDefender)
  - multi  : Orchestrator + ConsistencyChecker + Logger + Persona (core.agents.defender.multi)
Both expose the same `select_action(ctx)` contract, so the episode loop and metrics are
agnostic. GCS coordinate-directive is handled separately (core.gcs) — NOT here.
"""
from __future__ import annotations
from typing import Any, Optional
from core.agents.tactical import TacticalDefender
from core.agents.defender.multi import MultiRoleDefender


def make_defender(structure: str, node_id: str, llm_client, knowledge, model: str,
                  strategy_variant: str = "default", timeout: float = 6.0,
                  seed: Optional[int] = None, checker_model: Optional[str] = None,
                  extended: bool = False, stage_hint: bool = True) -> Any:
    """structure='single' -> TacticalDefender; 'multi' -> MultiRoleDefender. Same select_action.
    extended/stage_hint select the deceiver engine profile (5-skill+hint main vs 10-skill ladder)."""
    if structure == "multi":
        return MultiRoleDefender(node_id, llm_client, knowledge, model,
                                 strategy_variant=strategy_variant, timeout=timeout,
                                 seed=seed, checker_model=checker_model,
                                 extended=extended, stage_hint=stage_hint)
    if structure == "single":
        return TacticalDefender(node_id, llm_client, knowledge, model,
                                strategy_variant=strategy_variant, timeout=timeout, seed=seed,
                                extended=extended, stage_hint=stage_hint)
    raise ValueError(f"unknown defender structure '{structure}' (single|multi)")
