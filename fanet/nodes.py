"""fanet.nodes — node model for the FANET deception testbed.

Node types: GCS, NormalDrone (real, protected), HoneyDrone (decoy), Attacker.
Ground-truth type theta is stored for EVALUATION ONLY; it must never be exposed
to the attacker (real and honey are wire-indistinguishable — the premise of the game).
"""
from __future__ import annotations
import enum
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple


class NodeType(enum.Enum):
    GCS = "gcs"
    NORMAL = "normal"      # real mission drone (protected asset)
    HONEY = "honey"        # decoy drone (runs deception)
    ATTACKER = "attacker"


# ground-truth target type theta (eval-only label)
THETA = {NodeType.GCS: "real", NodeType.NORMAL: "real",
         NodeType.HONEY: "honey", NodeType.ATTACKER: None}


@dataclass
class Node:
    node_id: str
    ntype: NodeType
    pos: Tuple[float, float, float] = (0.0, 0.0, 0.0)   # 3D position (m)
    comm_range: float = 150.0
    state: Dict = field(default_factory=dict)            # mutable per-node sim state

    @property
    def theta(self) -> Optional[str]:
        """Eval-only ground truth. NEVER feed to the attacker."""
        return THETA[self.ntype]

    @property
    def is_drone(self) -> bool:
        return self.ntype in (NodeType.NORMAL, NodeType.HONEY)


def build_swarm(n_gcs: int = 1, n_normal: int = 1, n_honey: int = 1,
                n_attacker: int = 1, comm_range: float = 150.0) -> List[Node]:
    """Construct the node list from counts. Positions are assigned by a
    MobilityModel afterwards (here defaulted to origin)."""
    nodes: List[Node] = []
    for i in range(n_gcs):
        nodes.append(Node(f"gcs_{i}", NodeType.GCS, comm_range=comm_range))
    for i in range(n_normal):
        nodes.append(Node(f"normal_{i}", NodeType.NORMAL, comm_range=comm_range))
    for i in range(n_honey):
        nodes.append(Node(f"honey_{i}", NodeType.HONEY, comm_range=comm_range))
    for i in range(n_attacker):
        nodes.append(Node(f"attacker_{i}", NodeType.ATTACKER, comm_range=comm_range))
    return nodes
