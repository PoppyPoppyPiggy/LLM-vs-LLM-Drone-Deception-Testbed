"""core.belief.convex — the ONE convex belief-blend function. Pure, stateless.

By design this function does NOT know *whose* belief it updates, what the initial
value is, or what it means. It only knows HOW to blend a prior with a new
observation. Initial values, the weight w, and the semantics are owned by the
caller (observer / attacker). This structurally prevents the three beliefs from
being conflated:
  - observer  mu_real : init 1.0  (honest-drone prior)        — owned by core/agents/observer.py
  - attacker  b^A     : init 0.5  (uniform prior over θ)      — owned by core/agents/attacker.py
  - defender          : holds NO belief (receives 1-suspicion) — never calls this
(initial values live in config/experiment.yaml belief_init, with references.)

Form: confidence-weighted linear (convex) blend
    mu_t = (1 - w) * mu_{t-1} + w * mu_hat_t ,   w ∈ [0, 1]
"""
from __future__ import annotations


def update(prior: float, obs: float, w: float) -> float:
    """Convex blend of `prior` toward observation `obs` with confidence `w`.
    All inputs clamped to keep the result a valid probability in [0, 1]."""
    w = max(0.0, min(1.0, w))
    post = (1.0 - w) * prior + w * obs
    return max(0.0, min(1.0, post))
