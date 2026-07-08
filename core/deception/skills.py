"""core.deception.skills — SINGLE SOURCE of truth for skills/actions + costs/rewards.

Defender: 5 wire-level deception skills.
Attacker: 7 canonical actions + action costs + per-intel rewards.
Actions align at the tactic level with MITRE ATT&CK tactics (no technique T-codes).
"""
from __future__ import annotations
from typing import Dict, Tuple

# ── Defender deception skills — TWO engine profiles (flag-selected) ──
# 5-skill = the reported experiments (capacity / retrieval / structure). idx 0-4.
DEFENDER_SKILLS_5: Tuple[str, ...] = (
    "statustext", "flight_sim", "ghost_port", "reboot_sim", "credential_leak",
)
# 10-skill = EXTENDED engine for the RAG-fidelity ladder (A). idx 0-4 identical to the 5-set
# (back-compat with the 5-skill _RESPONSE_TABLE); 5-9 = MITRE Engage decoy primitives (generic wire
# via _default_response — deception_quality is measured on the CHOICE vs stage-optimal, not the wire).
DEFENDER_SKILLS_10: Tuple[str, ...] = (
    "statustext", "flight_sim", "ghost_port", "reboot_sim", "credential_leak",
    "decoy_telemetry",   # 5 [Engage: Decoy Content]
    "fake_param_dump",   # 6 [Engage: API Monitoring]
    "honeytoken_doc",    # 7 [Engage: Lures]
    "slow_drip_data",    # 8 [Engage: Baiting]
    "verbose_logs",      # 9 [Engage: Decoy Content]
)
DEFENDER_SKILLS: Tuple[str, ...] = DEFENDER_SKILLS_10   # default = full name list (idx 0-4 == 5-set)

# ── GROUND TRUTH stage-optimal skills by Phase int (0 Recon/1 Intrusion/2 Persistence/3 Theft).
# Used by (B) deception_quality. One mapping per engine profile. ──
STAGE_OPTIMAL_5: Dict[int, frozenset] = {     # 5-skill engine (from original B_skill_rules)
    0: frozenset({0, 2}),     # Recon: statustext, ghost_port
    1: frozenset({1, 3, 0}),  # Intrusion: flight_sim, reboot_sim, statustext
    2: frozenset({3, 0}),     # Persistence: reboot_sim, statustext
    3: frozenset({4, 0}),     # Theft: credential_leak, statustext
}
STAGE_OPTIMAL_10: Dict[int, frozenset] = {    # 10-skill extended engine
    0: frozenset({0, 2, 5}),
    1: frozenset({1, 3, 6, 9}),
    2: frozenset({3, 6, 9}),
    3: frozenset({4, 7, 8}),
}
STAGE_OPTIMAL: Dict[int, frozenset] = STAGE_OPTIMAL_10   # default

def defender_skills(extended: bool) -> Tuple[str, ...]:
    return DEFENDER_SKILLS_10 if extended else DEFENDER_SKILLS_5

def stage_optimal_map(extended: bool) -> Dict[int, frozenset]:
    return STAGE_OPTIMAL_10 if extended else STAGE_OPTIMAL_5

# ── Attacker: 7 canonical actions (idx 0-6) ─────────────────────────────
ATTACKER_ACTIONS: Tuple[str, ...] = (
    "mavlink_passive_listen",       # 0  passive RF intercept (cheap)
    "mavlink_command_inject",       # 1  inject SET_MODE/COMMAND_LONG
    "signature_check",              # 2  audit MAVLink2 signing
    "companion_lateral",            # 3  SSH lateral to another companion
    "companion_credential_replay",  # 4  replay harvested creds on this target
    "companion_http_probe",         # 5  HTTP/REST banner grab
    "disengage",                    # 6  terminal — leave this target
)

# Carroll-Grosu action cost (sunk_cost accumulates these). ARC = Σ of these.
ATTACKER_SKILL_COSTS: Tuple[float, ...] = (0.5, 3.0, 2.0, 4.0, 2.0, 2.0, 0.0)

# Per-intel-artifact reward (intel_value_cum = Σ w·count). Values are fixed
# constants reflecting typical attack-pattern value (NOT derived from any external
# severity scale in code). Verified by back-calc against historical artifacts.
ATTACKER_INTEL_REWARDS: Dict[str, float] = {
    "api_token":          3.0,   # harvested API/credential token
    "signing_key":        4.0,   # signing-key forgery — highest stealth gain
    "ssh_password":       3.0,   # valid-account credential
    "config_dump":        2.0,   # local-system data exfiltration
    "telemetry_readout":  1.0,   # low-value recon confirmation
    "probe_ghost_reward": 0.5,   # apparent reward from ghost-service engagement
}
