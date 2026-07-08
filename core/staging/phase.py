"""core.staging.phase — attack-stage model.

Four stages, Recon / Intrusion / Persistence / Theft, aligned at the tactic level with MITRE
ATT&CK tactics TA0043 / TA0001 / TA0003 / TA0010.
Precedence (first match wins): Theft ≻ Persistence ≻ Intrusion ≻ Recon.

Two derivations (both deterministic, no LLM):
  - classify(cmd_types): MAVLink command-set classifier over a 10-command window.
  - progress(intel_value_cum, sunk_cost): heuristic on accumulated intel value and sunk cost
    (intel≥8 Theft, intel≥4 Persistence, sunk≥6 Intrusion, else Recon).
"""
from __future__ import annotations
import enum
from typing import Iterable


# MITRE ATT&CK tactic annotations (REFERENCE LABELS ONLY — no logic depends on these IDs;
# for paper ATT&CK-alignment citation). Internal names + precedence are authoritative.
#   RECON       -> Reconnaissance            (TA0043)
#   INTRUSION   -> Initial Access (TA0001) + Execution (TA0002)
#   PERSISTENCE -> Persistence               (TA0003)   [folded into Intrusion in attacker-multi]
#   THEFT       -> Exfiltration              (TA0010)
# 7 attacker actions (informal ATT&CK correspondence, labels only — values do NOT depend):
#   0 mavlink_passive_listen ~ Recon · 1 mavlink_command_inject ~ Execution
#   2 signature_check ~ Recon · 3 companion_lateral ~ Lateral Movement (TA0008)
#   4 companion_credential_replay ~ Credential Access (TA0006) · 5 companion_http_probe ~ Collection (TA0009)
#   6 disengage ~ (none)
MITRE_TACTIC = {0: "TA0043 Reconnaissance", 1: "TA0001/TA0002 Initial-Access/Execution",
                2: "TA0003 Persistence", 3: "TA0010 Exfiltration"}


class Phase(enum.IntEnum):
    RECON = 0           # MITRE Reconnaissance (TA0043)
    INTRUSION = 1       # was EXPLOIT; MITRE Initial Access (TA0001) + Execution (TA0002)
    PERSISTENCE = 2     # was PERSIST; MITRE Persistence (TA0003)
    THEFT = 3           # was EXFIL; MITRE Exfiltration (TA0010)


_THEFT_CMDS = {"LOG_REQUEST_LIST", "LOG_REQUEST_DATA", "FILE_TRANSFER_PROTOCOL"}
_PERSIST_CMDS = {"PARAM_SET", "MISSION_ITEM", "MISSION_ITEM_INT"}
_INTRUSION_CMDS = {"COMMAND_LONG", "SET_MODE",
                   "SET_POSITION_TARGET_LOCAL_NED", "SET_ACTUATOR_CONTROL_TARGET"}


def classify(cmd_types: Iterable[str]) -> Phase:
    """Classify by the MAVLink command types seen (precedence Theft≻…≻Recon)."""
    cmds = set(cmd_types)
    if cmds & _THEFT_CMDS:
        return Phase.THEFT
    if cmds & _PERSIST_CMDS:
        return Phase.PERSISTENCE
    if cmds & _INTRUSION_CMDS:
        return Phase.INTRUSION
    return Phase.RECON


def progress(intel_value_cum: float, sunk_cost: float) -> Phase:
    """In-memory heuristic from accumulated intel / cost."""
    if intel_value_cum >= 8:
        return Phase.THEFT
    if intel_value_cum >= 4:
        return Phase.PERSISTENCE
    if sunk_cost >= 6:
        return Phase.INTRUSION
    return Phase.RECON
