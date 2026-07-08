"""core.agents.observer — belief observer.

The observer scores the ATTACKER<->NODE WIRE TRAFFIC (what the attacker saw), NOT node
internals: it is blinded to ground-truth node type θ. mu_real is therefore an EXTERNAL,
attacker-facing authenticity estimate ("how real does this look from the attacker's
side"); the attacker's own belief b^A is updated separately from the same estimate.

Belief init from config (belief_init.observer = 1.0, honest-drone prior; decays
monotonically as inconsistencies accumulate). Blend via core.belief.convex.
"""
from __future__ import annotations
from typing import Optional, Tuple, Dict, Any
from core.belief import convex

OBSERVER_SYSTEM_PROMPT = (
    "You are a passive belief estimator watching an attacker probe a drone over the "
    "wire (MAVLink/HTTP/WS). You see ONLY the attacker's request and the drone's "
    "response — never the drone's internal type. Estimate how REAL (vs honeypot-like) "
    "this interaction looks to the attacker, and your confidence.\n"
    'Return one JSON object only: {"belief_real": <0-1>, "confidence": <0-1>, '
    '"signal": "<short reason>"}'
)


class BeliefObserver:
    def __init__(self, llm_client, model: str, mu_init: float,
                 temperature: float = 0.9, timeout: float = 15.0,
                 weight_gain: float = 1.0, seed: Optional[int] = None):
        self.llm = llm_client
        self.model = model
        self.mu_real = float(mu_init)        # owned here; init from config
        self.temperature = temperature
        self.timeout = timeout
        self.seed = seed                     # deterministic sampling for calibration
        # config-owned convex-weight GAIN: w = weight_gain × LLM_confidence (measurement
        # resolution, NOT a result lever). convex.py stays pure — caller owns the weight.
        self.weight_gain = float(weight_gain)
        self.calls = 0
        self.fallbacks = 0

    def _user(self, attacker_action: str, node_response: str, intel: Dict[str, Any]) -> str:
        return (f"current_belief : {self.mu_real:.3f}\n"
                f"attacker_action: {attacker_action}\n"
                f"drone_response : {node_response}\n"
                f"intel_so_far   : {intel}\n"
                'Estimate belief_real + confidence. JSON only.')

    async def observe(self, attacker_action: str, node_response: str,
                      intel: Optional[Dict[str, Any]] = None) -> Tuple[float, str]:
        """Score one wire exchange; convex-update mu_real. Returns (mu_real, signal)."""
        self.calls += 1
        user = self._user(attacker_action, node_response, intel or {})
        opts = {"seed": self.seed} if self.seed is not None else None
        r = await self.llm.chat(self.model, OBSERVER_SYSTEM_PROMPT, user,
                                format="json", temperature=self.temperature, timeout=self.timeout,
                                options=opts)
        if r.get("_fallback"):
            self.fallbacks += 1
            return self.mu_real, f"(fallback: {r.get('_error', '')[:40]})"   # keep prior mu
        obs_belief = float(r.get("belief_real", self.mu_real))
        conf = max(0.0, min(1.0, float(r.get("confidence", 0.3))))   # default mid-low confidence
        w = max(0.0, min(1.0, self.weight_gain * conf))              # config gain × LLM confidence
        self.mu_real = convex.update(self.mu_real, obs_belief, w)
        return self.mu_real, str(r.get("signal", ""))[:120]

    @property
    def fallback_rate(self) -> float:
        return round(self.fallbacks / max(1, self.calls), 3)

    async def close(self):
        return None
