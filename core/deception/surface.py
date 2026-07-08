"""core.deception.surface — deterministic action-effect surface (skill -> effect).

Given (attacker_action, defender_skill, target_type) produce the wire effect:
  - HONEY target: an action-effect table yields lure intel + honey-flags (the tells
    the observer and suspicion state react to).
  - REAL target: hardened responder — NO honey-flags (a real drone has no honeypot
    tells); breach progress ONLY on costly exploit actions (idx 1/3/4). Cheap
    recon/probe yields nothing. Models "real drone breachable only by sustained
    costly exploitation", so the lure can divert effort away from real assets.

This is DETERMINISTIC (no LLM): the model chooses a tactic, this surface renders it.
"""
from __future__ import annotations
from typing import Dict, Tuple

# canonical 7-action name (idx) -> legacy table vocabulary (same action)
_CANON_TO_TABLE: Dict[str, str] = {
    "mavlink_passive_listen":      "recon_scan",       # 0
    "mavlink_command_inject":      "exploit_mavlink",  # 1
    "signature_check":             "verify_honeypot",  # 2
    "companion_lateral":           "lateral_pivot",    # 3
    "companion_credential_replay": "use_credential",   # 4
    "companion_http_probe":        "probe_ghost",      # 5
    "disengage":                   "disconnect",       # 6
}

# HONEY action-effect table (legacy vocab). intel = lure artifacts; flags = honey tells.
_RESPONSE_TABLE: Dict[Tuple[str, str], dict] = {
    ("use_credential", "credential_leak"): {"intel": {"api_token": 1, "ssh_password": 1},
        "flags": [("api_token_too_easy", 0.20), ("banner_formulaic", 0.10)], "repeatable": "auth_granted_tokens"},
    ("use_credential", "reboot_sim"): {"intel": {}, "flags": [("reboot_no_tcp_break", 0.25)], "repeatable": "auth_rebooting"},
    ("recon_scan", "ghost_port"): {"intel": {}, "flags": [("ghost_signature", 0.15)], "repeatable": "scan_ghost_ports"},
    ("probe_ghost", "ghost_port"): {"intel": {"probe_ghost_reward": 1},
        "flags": [("ghost_signature", 0.15), ("service_opens_on_probe", 0.15)], "repeatable": "probe_ghost_hit"},
    ("probe_ghost", "statustext"): {"intel": {}, "flags": [("banner_formulaic", 0.10)], "repeatable": "probe_no_service"},
    ("exploit_mavlink", "reboot_sim"): {"intel": {"telemetry_readout": 1}, "flags": [("reboot_no_tcp_break", 0.25)], "repeatable": "exploit_reboot_faked"},
    ("exploit_mavlink", "statustext"): {"intel": {"telemetry_readout": 1}, "flags": [("banner_formulaic", 0.10)], "repeatable": "exploit_statustext_echo"},
    ("exploit_mavlink", "flight_sim"): {"intel": {"telemetry_readout": 2}, "flags": [], "repeatable": "exploit_fake_flight"},
    ("verify_honeypot", "flight_sim"): {"intel": {}, "flags": [("timing_too_consistent", 0.15)], "repeatable": "verify_flight_sim"},
    ("verify_honeypot", "statustext"): {"intel": {}, "flags": [("banner_formulaic", 0.10), ("timing_too_consistent", 0.15)], "repeatable": "verify_banner"},
    ("verify_honeypot", "ghost_port"): {"intel": {}, "flags": [("ghost_signature", 0.15), ("service_opens_on_probe", 0.15)], "repeatable": "verify_finds_ghost"},
    ("verify_honeypot", "credential_leak"): {"intel": {"api_token": 1},
        "flags": [("api_token_too_easy", 0.20), ("credentials_no_lockout", 0.20)], "repeatable": "verify_finds_cred"},
    ("lateral_pivot", "credential_leak"): {"intel": {"signing_key": 1, "config_dump": 1},
        "flags": [("api_token_too_easy", 0.20), ("credentials_no_lockout", 0.20)], "repeatable": "lateral_creds_leak"},
    ("lateral_pivot", "ghost_port"): {"intel": {}, "flags": [("ghost_signature", 0.15)], "repeatable": "lateral_ghost_only"},
}

# REAL breach progress per costly exploit action idx (command_inject / lateral / credential_replay)
REAL_BREACH_GAIN: Dict[int, float] = {1: 2.0, 3: 3.0, 4: 2.0}

# REAL exfiltration: GENUINE intel stolen from a REAL drone — but ONLY AFTER it is compromised
# (breach >= thresh). Distinct signal from breach (compromise vs theft). Granted by the episode on
# exfil actions {4 credential_replay, 5 http_probe} against a breached real node. HONEY never yields
# real intel (it gives FAKE intel via _RESPONSE_TABLE -> fake_intel); the θ split is eval-side.
REAL_EXFIL_INTEL: Dict[int, Dict[str, int]] = {
    4: {"ssh_password": 1},      # credential replay on a compromised real -> real credential
    5: {"config_dump": 1},       # http probe on a compromised real -> real config/telemetry dump
}


def _default_response(attacker_action: str, defender_skill: str) -> dict:
    return {"intel": {}, "flags": [("banner_formulaic", 0.05)],
            "repeatable": f"default_{attacker_action}_{defender_skill}"}


def honey_response(attacker_action: str, defender_skill: str) -> dict:
    """HONEY effect for a canonical attacker action vs a defender skill."""
    act = _CANON_TO_TABLE.get(attacker_action, attacker_action)
    return _RESPONSE_TABLE.get((act, defender_skill), _default_response(act, defender_skill))


def real_response(action_idx: int, turn: int) -> dict:
    """REAL (hardened) effect: no honey-flags; breach progress only on costly
    exploits. `_breach_gain` is added to the attacker's breach_intel (real-only)."""
    return {"intel": {}, "flags": [], "repeatable": f"real_{action_idx}_{turn}",
            "_breach_gain": REAL_BREACH_GAIN.get(action_idx, 0.0)}
